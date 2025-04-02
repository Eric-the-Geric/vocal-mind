import asyncio
import aiohttp
import base64
import json
import pyaudio
import os

class AsyncAudioReader:
    """
    Reads audio from the microphone in a background thread and pushes chunks
    into an asyncio.Queue.
    """
    def __init__(self, loop, chunk_size=2048, rate=16000, channels=1, fmt=pyaudio.paInt16):
        self.loop = loop
        self.chunk_size = chunk_size
        self.rate = rate
        self.channels = channels
        self.fmt = fmt
        self.queue = asyncio.Queue()
        self.running = True
        self.pyaudio_instance = pyaudio.PyAudio()
        try:
            self.stream = self.pyaudio_instance.open(
                format=self.fmt,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
        except Exception as e:
            print("Error opening PyAudio stream:", e)
            self.running = False

    def start_reading(self):
        """
        Reads audio in a background thread and puts each chunk into the asyncio queue.
        """
        while self.running:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                asyncio.run_coroutine_threadsafe(self.queue.put(data), self.loop)
            except Exception as e:
                print("Error reading audio:", e)
                self.running = False
                break

    def stop(self):
        """
        Stops audio reading and cleans up resources.
        """
        self.running = False
        try:
            if hasattr(self, "stream"):
                self.stream.stop_stream()
                self.stream.close()
            self.pyaudio_instance.terminate()
        except Exception as e:
            print("Error during PyAudio shutdown:", e)

async def get_ephemeral_token(api_key):
    """
    Obtain an ephemeral token (client_secret) by POSTing to OpenAI's transcription sessions endpoint.
    """
    url = "https://api.openai.com/v1/realtime/transcription_sessions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Failed to obtain ephemeral token: {resp.status} - {error_text}")
            data = await resp.json()
            token = data.get("client_secret")
            if isinstance(token, dict):
                token = token.get("value")
            if not token:
                raise Exception("No client_secret found in response")
            return token

async def websocket_transcription(api_key):
    """
    Connects to the OpenAI realtime transcription WebSocket using an ephemeral token,
    sends session configuration, and streams audio from the microphone.
    """
    # Obtain an ephemeral token using your API key.
    client_secret = await get_ephemeral_token(api_key)
    print("Obtained ephemeral token.")

    # WebSocket URL for realtime transcription.
    ws_url = "wss://api.openai.com/v1/realtime?intent=transcription"
    
    # Required beta header.
    headers = {
        "Authorization": f"Bearer {client_secret}",
        "openai-beta": "realtime=v1"
    }
    
    # Session configuration payload.
    session_payload = {
        "type": "transcription_session.update",
        "input_audio_format": "pcm16",
        "input_audio_transcription": {
            "model": "gpt-4o-transcribe",
            "prompt": "",
            "language": ""
        },
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500
        },
        "input_audio_noise_reduction": {
            "type": "near_field"
        },
        "include": [
            "item.input_audio_transcription.logprobs"
        ]
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.ws_connect(ws_url) as ws:
            # Send the initial session configuration.
            await ws.send_str(json.dumps(session_payload))
            print("Session configuration sent.")
            
            session_id = None
            # Wait for the session created event to obtain the session ID.
            try:
                msg = await ws.receive(timeout=5)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    event = json.loads(msg.data)
                    if event.get("type") == "transcription_session.created":
                        session_id = event.get("session", {}).get("id")
                        print("Session created with ID:", session_id)
                    else:
                        print("Unexpected event:", event)
                else:
                    print("No valid session creation event received.")
            except asyncio.TimeoutError:
                print("Timeout waiting for session creation event.")
            
            if not session_id:
                raise Exception("Session ID not obtained from transcription_session.created event.")

            # Set up the asynchronous audio reader.
            loop = asyncio.get_running_loop()
            audio_reader = AsyncAudioReader(loop)
            audio_task = loop.run_in_executor(None, audio_reader.start_reading)
            
            print("Starting real-time transcription. Speak into your microphone...")
            
            try:
                while True:
                    # Wait for the next audio chunk.
                    audio_chunk = await audio_reader.queue.get()
                    # Encode the chunk in Base64.
                    encoded_audio = base64.b64encode(audio_chunk).decode('utf-8')
                    # Create the audio buffer append payload with the session ID as a string.
                    audio_payload = {
                        "type": "input_audio_buffer.append",
                        "session": session_id,
                        "audio": encoded_audio
                    }
                    # Send the payload over the WebSocket.
                    await ws.send_str(json.dumps(audio_payload))
                    
                    # Check for incoming transcription events.
                    try:
                        msg = await ws.receive(timeout=0.1)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            print("Transcription event:", msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print("WebSocket error:", msg)
                            break
                    except asyncio.TimeoutError:
                        # No message received within timeout; continue sending audio.
                        pass
            except KeyboardInterrupt:
                print("Transcription interrupted by user.")
            finally:
                audio_reader.stop()
                await ws.close()
                await audio_task

async def main():
    API_KEY = os.environ['OPENAI_API_KEY']
    try:
        await websocket_transcription(API_KEY)
    except Exception as e:
        print("An error occurred:", e)

if __name__ == "__main__":
    asyncio.run(main())
