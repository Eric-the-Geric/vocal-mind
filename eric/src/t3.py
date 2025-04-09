import asyncio
import websockets
import argparse
import json
import time
import sys

# Global variable to help compute latency (in seconds)
vad_time = None

# -------------------------------------------------------------------
# Session class wrapping the transcription websocket
# -------------------------------------------------------------------
class Session:
    def __init__(self, api_key):
        self.api_key = api_key
        self.on_connection_state_change = None  # Callback for connection state changes
        self.on_message = None                  # Callback for incoming messages
        self.on_error = None                    # Callback for errors
        self.ws = None

    async def start_transcription(self, audio_generator, session_config):
        """
        Connects to the websocket endpoint, sends an initialization message,
        starts sending audio data from the generator, and handles incoming messages.
        """
        url = "wss://api.openai.com/v1/realtime/transcribe"  # Placeholder endpoint!
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with websockets.connect(url, extra_headers=headers) as ws:
                self.ws = ws
                # Notify the caller about connection state.
                if self.on_connection_state_change:
                    self.on_connection_state_change("connected")

                # Send initial session configuration to start transcription.
                init_message = {
                    "type": "start",
                    "config": session_config
                }
                await ws.send(json.dumps(init_message))
                # Create concurrent tasks for sending audio and receiving messages.
                send_task = asyncio.create_task(self._send_audio(audio_generator))
                recv_task = asyncio.create_task(self._receive_messages())
                done, pending = await asyncio.wait(
                    [send_task, recv_task], return_when=asyncio.FIRST_EXCEPTION
                )
                # Cancel any pending tasks if one finishes or errors.
                for task in pending:
                    task.cancel()
        except Exception as e:
            if self.on_error:
                self.on_error(e)

    async def _send_audio(self, audio_generator):
        """
        Reads chunks from the async generator and sends them over the websocket.
        """
        async for chunk in audio_generator:
            await self.ws.send(chunk)
        # Optionally signal the end of stream.
        await self.ws.send(json.dumps({"type": "end_of_stream"}))

    async def _receive_messages(self):
        """
        Receives incoming messages from the websocket and passes them to the on_message callback.
        """
        async for message in self.ws:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue
            if self.on_message:
                self.on_message(data)

    def stop(self):
        """
        Stops the session by closing the websocket connection.
        """
        if self.ws:
            # Fire and forget closing the websocket.
            asyncio.create_task(self.ws.close())

# -------------------------------------------------------------------
# Audio generators
# -------------------------------------------------------------------
async def audio_generator_file(file_path, chunk_size=1024):
    """
    Async generator to read audio data from a file.
    """
    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
                # Give control back to the event loop.
                await asyncio.sleep(0)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

async def audio_generator_microphone(chunk_size=1024, sample_rate=16000):
    """
    Async generator that captures audio from the microphone.
    It uses the PyAudio callback to insert audio chunks into an asyncio queue.
    """
    try:
        import pyaudio
    except ImportError:
        print("pyaudio is required for microphone input. Please install it with 'pip install pyaudio'")
        sys.exit(1)

    loop = asyncio.get_running_loop()
    q = asyncio.Queue()

    p = pyaudio.PyAudio()

    # Define a callback function that puts audio data into the asyncio queue.
    def callback(in_data, frame_count, time_info, status):
        loop.call_soon_threadsafe(q.put_nowait, in_data)
        return (None, pyaudio.paContinue)

    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=sample_rate,
                    input=True,
                    frames_per_buffer=chunk_size,
                    stream_callback=callback)

    stream.start_stream()
    try:
        while stream.is_active():
            data = await q.get()
            yield data
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

# -------------------------------------------------------------------
# Callback functions to handle messages and errors.
# -------------------------------------------------------------------
def handle_message(message):
    """
    Processes incoming messages from the transcription websocket.
    The behavior mimics the JavaScript code by printing temporary placeholders
    for speech events and printing final transcript text with latency.
    """
    global vad_time
    msg_type = message.get("type")
    if msg_type == "transcription_session.created":
        session_info = message.get("session", {})
        print(f"\nSession created: {session_info.get('id', 'unknown')}")
    elif msg_type == "input_audio_buffer.speech_started":
        # Indicate that speech has started.
        print("...", end="", flush=True)
    elif msg_type == "input_audio_buffer.speech_stopped":
        # Indicate that speech has stopped and note the VAD (voice activity detection) time.
        print("***", end="", flush=True)
        # Here we simulate subtracting the configured silence duration.
        silence_duration_ms = message.get("silence_duration_ms", 1000)
        vad_time = time.perf_counter() - (silence_duration_ms / 1000)
    elif msg_type == "conversation.item.input_audio_transcription.completed":
        transcript = message.get("transcript", "")
        # Calculate latency if we have timing info.
        if vad_time is not None:
            elapsed_ms = int((time.perf_counter() - vad_time) * 1000)
        else:
            elapsed_ms = 0
        print(f"\n{transcript} (latency: {elapsed_ms} ms)")
    else:
        # For any other message type, just print it.
        print(f"\nMessage: {message}")

def handle_error(e):
    """
    Simple error handler that prints the exception.
    """
    print(f"\nError: {e}")
    sys.exit(1)

# -------------------------------------------------------------------
# Main function
# -------------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(
        description="Realtime Transcription Command-Line Client using OpenAI API (Websocket)"
    )
    parser.add_argument("--api-key", required=True, help="Your OpenAI API key.")
    parser.add_argument("--model", default="whisper-1", help="Transcription model to use.")
    parser.add_argument("--prompt", default="", help="Optional transcription prompt.")
    parser.add_argument("--turn-detection", default="default", help="Type of turn detection to use.")
    parser.add_argument("--silence-duration-ms", type=int, default=1000,
                        help="Silence duration (ms) to compute turn detection latency.")
    parser.add_argument("--mode", choices=["microphone", "file"], default="microphone",
                        help="Input mode: 'microphone' to capture live audio or 'file' to transcribe an audio file.")
    parser.add_argument("--file", help="Path to audio file (required if mode is 'file').")

    args = parser.parse_args()

    # Check that if mode is file, the --file argument is provided.
    if args.mode == "file" and not args.file:
        print("For file mode you must supply --file.")
        sys.exit(1)

    # Build the session configuration (similar to the JS config)
    session_config = {
        "input_audio_transcription": {
            "model": args.model,
            "prompt": args.prompt if args.prompt else None,
        },
        "turn_detection": {
            "type": args.turn_detection,
            "silence_duration_ms": args.silence_duration_ms
        }
    }

    # Create the transcription session
    session = Session(args.api_key)
    session.on_connection_state_change = lambda state: print(f"Connection state: {state}")
    session.on_message = handle_message
    session.on_error = handle_error

    # Choose the appropriate audio generator
    if args.mode == "microphone":
        print("Starting microphone transcription...")
        audio_gen = audio_generator_microphone()
    else:
        print(f"Starting transcription from file: {args.file}")
        audio_gen = audio_generator_file(args.file)

    # Start the transcription session. This call will block until the websocket ends or an error occurs.
    await session.start_transcription(audio_gen, session_config)
    print("Transcription stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
