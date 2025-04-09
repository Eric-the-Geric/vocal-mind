import os
import json
import base64
import asyncio
import logging
import aiohttp
import websockets

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Missing OpenAI API key.")

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

final_transcription = ""

async def create_transcription_session():
    """
    Create a transcription session via the REST API to obtain an ephemeral token.
    This endpoint uses the beta header "OpenAI-Beta: assistants=v2".
    """
    url = "https://api.openai.com/v1/realtime/transcription_sessions"
    payload = {
        "input_audio_format": "pcm16",
        "input_audio_transcription": {
            "model": "gpt-4o-transcribe",
            "language": "en",
            "prompt": "Transcribe the incoming audio in real time."
        },
    
        "turn_detection": {"type": "server_vad", "silence_duration_ms": 1000}
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
                raise Exception(f"Failed to create transcription session: {resp.status} {text}")
            data = await resp.json()
            ephemeral_token = data["client_secret"]["value"]
            logger.info("Transcription session created; ephemeral token obtained.")
            return ephemeral_token

async def send_audio(ws, file_path: str, chunk_size: int, speech_stopped_event: asyncio.Event):
    """
    Read the local ulaw file and send it in chunks.
    After finishing, wait for 1 second to see if the server auto-commits.
    If not, send a commit event manually.
    """
    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                # Base64-encode the audio chunk.
                audio_chunk = base64.b64encode(chunk).decode("utf-8")
                audio_event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_chunk
                }
                await ws.send(json.dumps(audio_event))
                await asyncio.sleep(0.02)  # simulate real-time streaming
        logger.info("Finished sending audio file.")

        # Wait 1 second to allow any late VAD events before committing.
        try:
            await asyncio.wait_for(speech_stopped_event.wait(), timeout=1.0)
            logger.debug("Speech stopped event received; no manual commit needed.")
        except asyncio.TimeoutError:
            commit_event = {"type": "input_audio_buffer.commit"}
            await ws.send(json.dumps(commit_event))
            logger.info("Manually sent input_audio_buffer.commit event.")
    except FileNotFoundError:
        logger.error(f"Audio file not found: {file_path}")
    except Exception as e:
        logger.error("Error sending audio: %s", e)

async def receive_events(ws, speech_stopped_event: asyncio.Event):
    """
    Listen for events from the realtime endpoint.
    Capture transcription deltas and the final complete transcription.
    Set the speech_stopped_event when a "speech_stopped" event is received.
    """
    global final_transcription
    try:
        async for message in ws:
            try:
                event = json.loads(message)
                event_type = event.get("type")
                if event_type == "input_audio_buffer.speech_stopped":
                    logger.debug("Received event: input_audio_buffer.speech_stopped")
                    speech_stopped_event.set()
                elif event_type == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    logger.info("Transcription delta: %s", delta)
                    final_transcription += delta
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    completed_text = event.get("transcript", "")
                    logger.info("Final transcription completed: %s", completed_text)
                    final_transcription = completed_text  # Use the completed transcript
                    break  # Exit after final transcription
                elif event_type == "error":
                    logger.error("Error event: %s", event.get("error"))
                else:
                    logger.debug("Received event: %s", event_type)
            except Exception as ex:
                logger.error("Error processing message: %s", ex)
    except Exception as e:
        logger.error("Error receiving events: %s", e)


import pyaudio
import threading

class MicrophoneStreamer:
    def __init__(self, ws, chunk_size=1024, rate=16000, format=pyaudio.paInt16):
        self.ws = ws
        self.chunk_size = chunk_size
        self.rate = rate
        self.format = format
        self.channels = 1
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.running = False

    async def start_streaming(self):
        loop = asyncio.get_running_loop()
        self.running = True

        def callback(in_data, frame_count, time_info, status):
            if self.running:
                encoded = base64.b64encode(in_data).decode("utf-8")
                asyncio.run_coroutine_threadsafe(
                    self.send_chunk(encoded), loop
                )
            return (None, pyaudio.paContinue)

        self.stream = self.p.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=callback
        )
        self.stream.start_stream()

    async def send_chunk(self, encoded_audio):
        audio_event = {
            "type": "input_audio_buffer.append",
            "audio": encoded_audio
        }
        try:
            await self.ws.send(json.dumps(audio_event))
        except Exception as e:
            logger.error(f"Error sending mic chunk: {e}")
            self.running = False

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()


async def test_transcription():
    try:
        # Step 1: Create transcription session and get ephemeral token.
        ephemeral_token = await create_transcription_session()

        # Step 2: Connect to the base realtime endpoint.
        websocket_url = "wss://api.openai.com/v1/realtime"
        connection_headers = {
            "Authorization": f"Bearer {ephemeral_token}",
            "OpenAI-Beta": "realtime=v1"
        }
        async with websockets.connect(websocket_url, extra_headers=connection_headers) as ws:
            logger.info("Connected to realtime endpoint.")

            # Step 3: Send transcription session update event with adjusted VAD settings.
            update_event = {
                "type": "transcription_session.update",
                "session": {
                    "input_audio_transcription": {
                        "model": "gpt-4o-transcribe",
                        "language": "en",
                        "prompt": "Transcribe the incoming audio in real time."
                    },
                    # Matching the REST API settings
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 1000}
                }
            }
            await ws.send(json.dumps(update_event))
            logger.info("Sent transcription session update event.")

            # Create an event to signal if speech stopped is detected.
            speech_stopped_event = asyncio.Event()

            # Step 4: Run sender and receiver concurrently.
            mic_streamer = MicrophoneStreamer(ws)

            sender_task = asyncio.create_task(mic_streamer.start_streaming())
            receiver_task = asyncio.create_task(receive_events(ws, speech_stopped_event))

            await asyncio.gather(sender_task, receiver_task)
            #await asyncio.gather(receiver_task)
            mic_streamer.stop()

            # Print the final transcription.
            logger.info("Final complete transcription: %s", final_transcription)
            print("Final complete transcription:")
            print(final_transcription)

    except Exception as e:
        logger.error("Error in transcription test: %s", e)

if __name__ == "__main__":
    asyncio.run(test_transcription())
