import os
import json
import base64
import asyncio
import aiohttp
import websockets
import pyaudio
import wave
import collections
import logging
from src import CleanupAgent
from openai import OpenAI
import time

# Get API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Missing OpenAI API key.")

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Global to hold the most recent transcription segment
final_transcription = ""

OVERLAP_SECONDS = 5  # seconds of overlap to keep in the buffer
INTERVAL = 10  # seconds between commits
def compute_overlap_chunks(rate, chunk_size, overlap_seconds=5):
    # Calculate how many chunks correspond to the overlap duration
    return int(rate * overlap_seconds / chunk_size) + 1

class MicrophoneStreamer:
    def __init__(self, ws, chunk_size=1024, rate=16000, fmt=pyaudio.paInt16, wav_filename="outputs/output.wav"):
        self.ws = ws
        self.chunk_size = chunk_size
        self.rate = rate
        self.format = fmt
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.running = False
        # Set up wave file for local recording
        self.wav_file = wave.open(wav_filename, "wb")
        self.wav_file.setnchannels(1)
        self.wav_file.setsampwidth(self.p.get_sample_size(self.format))
        self.wav_file.setframerate(self.rate)
        # Overlap buffer to prevent missing audio at commit boundaries
        overlap_chunks = compute_overlap_chunks(self.rate, self.chunk_size, overlap_seconds=OVERLAP_SECONDS)
        self.overlap_buffer = collections.deque(maxlen=overlap_chunks)
        self.logger = logger

    async def start(self):
        loop = asyncio.get_event_loop()
        self.running = True

        def callback(in_data, frame_count, time_info, status):
            if self.running:
                # store chunk for overlap
                self.overlap_buffer.append(in_data)
                # send audio to the API
                b64 = base64.b64encode(in_data).decode("utf-8")
                asyncio.run_coroutine_threadsafe(
                    self.ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": b64
                    })), loop
                )
                # write raw PCM data to wave file
                self.wav_file.writeframes(in_data)
            return (None, pyaudio.paContinue)

        self.stream = self.p.open(
            format=self.format,
            channels=1,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=callback
        )
        self.stream.start_stream()
        logger.info("Mic streaming started.")
        # keep the coroutine alive while streaming
        while self.running:
            await asyncio.sleep(0.1)

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()
        # close wave file
        self.wav_file.close()
        logger.info("Mic streaming stopped.")
async def create_transcription_session():
    with open("./prompts/transcribe_audio.txt", "r") as f:
        prmpt = f.read()

    url = "https://api.openai.com/v1/realtime/transcription_sessions"
    payload = {
        "input_audio_format": "pcm16",
        "input_audio_transcription": {
            "model": "gpt-4o-mini-transcribe",
            #"language": "en",
            "language": "fr",
            #"prompt": "Transcribe the incoming audio. Do not summarize or translate. Include words like 'uh', 'um', and 'ah'. Be as accurate as possible.",
            "prompt": prmpt,
        },
        "turn_detection": None  # disable server VAD
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Failed to create session: {resp.status} {text}")
            data = await resp.json()
            token = data["client_secret"]["value"]
            logger.info("Got ephemeral token.")
            return token

async def auto_commit(ws, mic, interval: float, commit_event: asyncio.Event):
    """
    Periodically send commit events, resending the last audio overlap to avoid dropped words.
    """
    while not commit_event.is_set():
        await asyncio.sleep(interval)
        # resend the overlap buffer
        for pcm_chunk in list(mic.overlap_buffer):
            b64 = base64.b64encode(pcm_chunk).decode("utf-8")
            await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": b64}))
        # send commit
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        logger.info("Sent periodic commit event with overlap.")
    logger.info("Auto-commit stopped.")

async def wait_for_enter_and_commit(ws, mic, commit_event: asyncio.Event):
    # run blocking input() in executor so it doesn't block the loop
    await asyncio.get_event_loop().run_in_executor(
        None, input, "Press Enter to stop recording and send final commit...\n"
    )
    # before final commit, resend overlap one last time
    for pcm_chunk in list(mic.overlap_buffer):
        b64 = base64.b64encode(pcm_chunk).decode("utf-8")
        await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": b64}))
    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
    logger.info("Sent manual commit event with overlap.")
    # stop the mic
    mic.stop()
    # signal that final commit was requested
    commit_event.set()

async def receive_events(ws, transcript_file, commit_event: asyncio.Event, final_event: asyncio.Event):
    global final_transcription
    try:
        async for msg in ws:
            event = json.loads(msg)
            t = event.get("type")
            if t == "conversation.item.input_audio_transcription.delta":
                delta = event.get("delta", "")
                logger.debug("Δ %s", delta)
                final_transcription += delta
            elif t == "conversation.item.input_audio_transcription.completed":
                text = event.get("transcript", "")
                logger.info("✅ Completed segment: %s", text)
                # write this segment to the transcript file
                transcript_file.write(text + "\n")
                transcript_file.flush()
                if not commit_event.is_set():
                    # a periodic (partial) segment, reset buffer for the next segment
                    final_transcription = ""
                else:
                    # final segment, signal and exit
                    final_transcription = text
                    final_event.set()
                    break
            elif t == "error":
                logger.error("Error event: %s", event.get("error"))
            else:
                logger.debug("Event: %s", t)
    except Exception as e:
        logger.error("receive_events error: %s", e)
        # ensure we unblock the main flow
        final_event.set()


async def main(t):
    with open("./prompts/transcribe_audio.txt", "r") as f:
        prmpt = f.read()
    try:
        token = await create_transcription_session()

        async with websockets.connect(
            "wss://api.openai.com/v1/realtime",
            additional_headers={
                "Authorization": f"Bearer {token}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as ws:
            logger.info("WebSocket opened.")

            # disable server VAD on the live connection too
            await ws.send(json.dumps({
                "type": "transcription_session.update",
                "session": {
                    "input_audio_transcription": {
                        "model": "gpt-4o-transcribe",
                        "language": "en",
                        #"prompt": "Transcribe the incoming audio in real time."
                        "prompt": prmpt
                    },
                    "turn_detection": None
                }
            }))
            logger.info("Sent session.update (VAD off).")

            # open local transcript file
            transcript_path = "./outputs/transcript_" +str(t) + ".txt"
            #transcript_file = open("./outputs/transcript.txt", "w", encoding="utf-8")
            transcript_file = open(transcript_path, "w", encoding="utf-8")

            # events to manage flow
            commit_event = asyncio.Event()
            final_event = asyncio.Event()

            # start microphone streamer
            mic = MicrophoneStreamer(ws, wav_filename=f"./outputs/microphone_recording_{str(t)}.wav")
            mic_task = asyncio.create_task(mic.start())
            # start periodic commits every 5 seconds, resending overlap
            commit_loop_task = asyncio.create_task(auto_commit(ws, mic, interval=INTERVAL, commit_event=commit_event))
            # start listening for API events
            recv_task = asyncio.create_task(receive_events(ws, transcript_file, commit_event, final_event))
            # wait for user to press Enter to stop
            enter_task = asyncio.create_task(wait_for_enter_and_commit(ws, mic, commit_event))

            # wait until user signals stop
            await commit_event.wait()
            # wait until final transcription arrives
            await final_event.wait()

            # cleanup tasks
            commit_loop_task.cancel()
            for t in (mic_task, recv_task, enter_task):
                t.cancel()
            # slight pause for final logs
            await asyncio.sleep(0.1)
            # close transcript file
            transcript_file.close()

            # output final transcription
            print("\n=== Final transcription ===")
            print(final_transcription)

    except Exception as e:
        logger.error("Fatal error in transcription: %s", e)

def text_to_speech_openai(client, text, output_path):
    """Convert text to speech using OpenAI's TTS API"""
    with open("./prompts/tts_instructions.txt", "r") as f:
        instruction = f.read()
    try:
        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",  # or tts-1-hd for higher quality
            voice="alloy",  # options: alloy, echo, fable, onyx, nova, shimmer
            input=text,
            #instructions="Speak in a natural tone with authority", 
            instructions=instruction, 
            ) as response:
        
            response.stream_to_file(output_path)
        print(f"Speech saved to {output_path}")
        return True
    except Exception as e:
        print(f"Error generating speech: {e}")
        return False

if __name__ == "__main__":
    t = time.time()
    t = int(t)
    asyncio.run(main(t))
    client = OpenAI()
    # Cleanup agent
    start = time.time()
    transcript_path = "./outputs/transcript_"+str(t) + ".txt"
    cleanup_agent = CleanupAgent(client,
                                 transcript_path=transcript_path,
                                 cleanup_prompt_path="./prompts/cleanup_prompt.txt",
                                 response_prompt_path="./prompts/response_prompt.txt",
                                 )
    cleanup_agent.run()
    end = time.time()
    print("time to clean up: ", end-start)
    start = time.time()
    response = cleanup_agent.respond_to_transcript()
    end = time.time()
    print("time to respond: ", end-start)
    # Convert text to speech
    output_path = "./outputs/response_test_"+ str(t) + ".wav"
    text = response
    start = time.time()
    text_to_speech_openai(client, text, output_path)
    end = time.time()
    print("text to speech part", end-start)


