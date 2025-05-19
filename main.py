import os
import io
import json
import base64
import asyncio
import aiohttp
import websockets
import pyaudio
import wave
import collections
import logging
from pathlib import Path
import time
import numpy as np
import argparse

from src import CleanupAgent
from openai import OpenAI, AsyncOpenAI
from openai.helpers import LocalAudioPlayer

# --- TTS client for async generation/playback ---
a_openai = AsyncOpenAI()

# Get API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Missing OpenAI API key.")

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Global to hold transcription
final_transcription = ""

OVERLAP_SECONDS = 5
INTERVAL = 10
def compute_overlap_chunks(rate, chunk_size, overlap_seconds=5):
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
        self.wav_file = wave.open(wav_filename, "wb")
        self.wav_file.setnchannels(1)
        self.wav_file.setsampwidth(self.p.get_sample_size(self.format))
        self.wav_file.setframerate(self.rate)
        overlap_chunks = compute_overlap_chunks(self.rate, self.chunk_size, overlap_seconds=OVERLAP_SECONDS)
        self.overlap_buffer = collections.deque(maxlen=overlap_chunks)
        self.logger = logger

    async def start(self):
        loop = asyncio.get_event_loop()
        self.running = True

        def callback(in_data, frame_count, time_info, status):
            if self.running:
                self.overlap_buffer.append(in_data)
                b64 = base64.b64encode(in_data).decode("utf-8")
                asyncio.run_coroutine_threadsafe(
                    self.ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": b64
                    })), loop
                )
                self.wav_file.writeframes(in_data)
            return (None, pyaudio.paContinue)

        self.stream = self.p.open(
            format=self.format, channels=1, rate=self.rate,
            input=True, frames_per_buffer=self.chunk_size,
            stream_callback=callback
        )
        self.stream.start_stream()
        logger.info("Mic streaming started.")
        while self.running:
            await asyncio.sleep(0.1)

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()
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
            "language": "fr",
            "prompt": prmpt,
        },
        "turn_detection": None
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
            logger.info("Got ephemeral token.")
            return data["client_secret"]["value"]


async def auto_commit(ws, mic, interval: float, commit_event: asyncio.Event):
    while not commit_event.is_set():
        await asyncio.sleep(interval)
        for pcm in list(mic.overlap_buffer):
            b64 = base64.b64encode(pcm).decode("utf-8")
            await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": b64}))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        logger.info("Sent periodic commit with overlap.")
    logger.info("Auto-commit stopped.")


async def wait_for_enter_and_commit(ws, mic, commit_event: asyncio.Event):
    await asyncio.get_event_loop().run_in_executor(
        None, input, "Press Enter to stop recording and send final commit...\n"
    )
    for pcm in list(mic.overlap_buffer):
        b64 = base64.b64encode(pcm).decode("utf-8")
        await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": b64}))
    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
    logger.info("Sent manual commit with overlap.")
    mic.stop()
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
                transcript_file.write(text + "\n")
                transcript_file.flush()
                if not commit_event.is_set():
                    final_transcription = ""
                else:
                    final_transcription = text
                    final_event.set()
                    break
            elif t == "error":
                logger.error("Error event: %s", event.get("error"))
            else:
                logger.debug("Event: %s", t)
    except Exception as e:
        logger.error("receive_events error: %s", e)
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
            await ws.send(json.dumps({
                "type": "transcription_session.update",
                "session": {
                    "input_audio_transcription": {
                        "model": "gpt-4o-transcribe",
                        "language": "en",
                        "prompt": prmpt
                    },
                    "turn_detection": None
                }
            }))
            logger.info("Sent session.update (VAD off).")

            transcript_path = f"./outputs/transcript_{t}.txt"
            transcript_file = open(transcript_path, "w", encoding="utf-8")

            commit_event = asyncio.Event()
            final_event = asyncio.Event()

            mic = MicrophoneStreamer(ws,
                                     wav_filename=f"./outputs/microphone_recording_{t}.wav")
            mic_task = asyncio.create_task(mic.start())
            commit_loop_task = asyncio.create_task(auto_commit(ws, mic, INTERVAL, commit_event))
            recv_task = asyncio.create_task(receive_events(ws, transcript_file, commit_event, final_event))
            enter_task = asyncio.create_task(wait_for_enter_and_commit(ws, mic, commit_event))

            await commit_event.wait()
            await final_event.wait()

            commit_loop_task.cancel()
            for task in (mic_task, recv_task, enter_task):
                task.cancel()
            await asyncio.sleep(0.1)
            transcript_file.close()

            print("\n=== Final transcription ===")
            print(final_transcription)

    except Exception as e:
        logger.error("Fatal error in transcription: %s", e)


# --- split TTS into generate + playback ------------

async def tts_generate(instructions: str, text: str, voice: str) -> bytes:
    """Generate TTS audio and return raw WAV bytes."""
    async with a_openai.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text,
        instructions=instructions,
        response_format="wav"
    ) as resp:
        buf = bytearray()
        # stream bytes correctly
        try:
            # prefer iter_bytes() if available
            async for chunk in resp.iter_bytes():  # type: ignore
                buf.extend(chunk)
        except AttributeError:
            # fallback: stream to a temp file then read
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_path = tmp.name
            tmp.close()
            await resp.stream_to_file(tmp_path)
            buf = Path(tmp_path).read_bytes()
            os.remove(tmp_path)
            return buf
    return bytes(buf)


def play_audio(audio_bytes: bytes):
    """Play raw WAV bytes via PyAudio (runs in executor)."""
    pa = pyaudio.PyAudio()
    wf = wave.open(io.BytesIO(audio_bytes), 'rb')
    stream = pa.open(
        format=pa.get_format_from_width(wf.getsampwidth()),
        channels=wf.getnchannels(),
        rate=wf.getframerate(),
        output=True
    )
    data = wf.readframes(1024)
    while data:
        stream.write(data)
        data = wf.readframes(1024)
    stream.stop_stream()
    stream.close()
    pa.terminate()


async def pipeline(t0, args):
    # ─── Setup CleanupAgent ───────────────────────────────────────────────
    client = OpenAI()
    transcript_path = f"./outputs/transcript_{t0}.txt"
    #transcript_path = f"./outputs/Alex.txt"
    cleanup_agent = CleanupAgent(
        client,
        transcript_path=transcript_path,
        cleanup_prompt_path=args.cleanup,
        response_prompt_path=args.response,
    )

    instruction = Path(args.tts).read_text()
    voice_model = np.random.choice(["echo", "alloy", "onyx"])

    # ─── Queues for text & audio ─────────────────────────────────────────
    text_queue  = asyncio.Queue()
    audio_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Producer callback (runs in thread)
    def on_sentence(sent: str):
        loop.call_soon_threadsafe(text_queue.put_nowait, sent)

    # Stage 1: launch cleanup streaming in executor
    producer = loop.run_in_executor(None, cleanup_agent.stream_response, on_sentence)

    # Stage 2: TTS‐generation worker
    async def tts_worker():
        while True:
            sent = await text_queue.get()
            if sent is None:
                await audio_queue.put(None)
                text_queue.task_done()
                break
            audio = await tts_generate(instruction, sent, voice_model)
            await audio_queue.put(audio)
            text_queue.task_done()

    tts_task = asyncio.create_task(tts_worker())

    # Stage 3: Playback worker
    async def playback_worker():
        while True:
            audio = await audio_queue.get()
            if audio is None:
                audio_queue.task_done()
                break
            await loop.run_in_executor(None, play_audio, audio)
            audio_queue.task_done()

    playback_task = asyncio.create_task(playback_worker())

    # ─── Tear‐down: wait for all stages ────────────────────────────────────
    await producer
    await text_queue.put(None)
    await text_queue.join()
    await tts_task

    await audio_queue.join()
    await playback_task


async def run(t0):
    parser = argparse.ArgumentParser()
    parser.add_argument('--cleanup',  type=str, default='./prompts/cleanup_prompt.txt')
    parser.add_argument('--response', type=str, default='./prompts/response_prompt.txt')
    parser.add_argument('--tts',      type=str, default='./prompts/tts_instructions.txt')
    args = parser.parse_args()

    await pipeline(t0, args)


if __name__ == "__main__":
    t0 = int(time.time())
    asyncio.run(main(t0))      # 1) live transcription
    asyncio.run(run(t0))       # 2) cleanup → generate → playback
