import asyncio
import json
import os
import websockets
import pyaudio
import argparse
from dotenv import load_dotenv
from termcolor import colored
import numpy as np
import base64
import time
import sys
import traceback

# Load environment variables from .env file
load_dotenv()

class RealtimeTranscriber:
    def __init__(self, api_key=None, language="en", sample_rate=16000, debug=True):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass it as an argument.")
        
        self.language = language
        self.sample_rate = sample_rate
        self.channels = 1
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.ws = None
        self.audio = pyaudio.PyAudio()
        self.current_transcription = ""
        self.item_id_to_transcription = {}
        self.ordered_item_ids = []
        self.session_started = False
        self.debug = debug
        self.audio_chunks_sent = 0
        self.last_audio_sent_time = time.time()
        
    def debug_print(self, message, end="\n", flush=True):
        """Print debug messages if debug mode is enabled"""
        if self.debug:
            print(f"[DEBUG] {message}", end=end, flush=flush)
        
    async def create_transcription_session(self):
        """Create a transcription session by sending configuration message through WebSocket"""
        self.debug_print("Creating transcription session...")
        
        session_config = {
            "type": "transcription_session.update",
            "input_audio_format": "pcm16",  # Use 'pcm16' as specified by the docs
            "input_audio_transcription": [{
                "model": "gpt-4o-transcribe",
                "prompt": f"Transcribe speech in {self.language}",
                "language": self.language
            }],
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.3,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 700
            },
            "input_audio_noise_reduction": {
                "type": "near_field"
            }
        }
        
        self.debug_print(f"Sending session config: {json.dumps(session_config, indent=2)}")
        await self.ws.send(json.dumps(session_config))
        self.debug_print("Transcription session configuration sent successfully")
    
    def audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for PyAudio to get microphone data"""
        try:
            # Check audio level for debugging
            audio_array = np.frombuffer(in_data, dtype=np.int16)
            audio_level = np.abs(audio_array).mean()
            
            # Show audio levels more frequently in debug mode
            if time.time() % 1 < 0.1:  # Every ~1 second
                self.debug_print(f"Audio buffer received - Level: {audio_level:.2f}, Frame count: {frame_count}", end="\r")
            
            if self.ws:
                # Check if WebSocket is connected
                is_open = True
                if hasattr(self.ws, 'closed'):
                    is_open = not self.ws.closed
                elif hasattr(self.ws, 'close'):
                    is_open = not self.ws.close
                
                if not is_open:
                    self.debug_print("WebSocket is closed, cannot send audio")
                    return (in_data, pyaudio.paContinue)
                
                # Send the audio data asynchronously
                asyncio.run_coroutine_threadsafe(self.send_audio(in_data), self.loop)
            else:
                self.debug_print("WebSocket is None, cannot send audio", end="\r")
        except Exception as e:
            self.debug_print(f"\nError in audio callback: {e}")
            self.debug_print(traceback.format_exc())
        
        return (in_data, pyaudio.paContinue)
    
    async def send_audio(self, audio_chunk):
        """Send audio data to the websocket"""
        try:
            if not self.ws:
                self.debug_print("WebSocket not available in send_audio", end="\r")
                return
            
            # Check if websocket is still connected
            is_open = True
            if hasattr(self.ws, 'closed'):
                is_open = not self.ws.closed
            elif hasattr(self.ws, 'close'):
                is_open = not self.ws.close
            
            if not is_open:
                self.debug_print("WebSocket is closed in send_audio", end="\r")
                return
                
            # Convert the audio data to base64
            audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
            
            message = {
                "type": "input_audio_buffer.append",
                "data_base64": audio_base64
            }
            
            await self.ws.send(json.dumps(message))
            self.audio_chunks_sent += 1
            
            # Print stats periodically
            current_time = time.time()
            if current_time - self.last_audio_sent_time >= 5.0:
                chunks_per_second = self.audio_chunks_sent / (current_time - self.last_audio_sent_time)
                self.debug_print(f"Audio stats: Sent {self.audio_chunks_sent} chunks in the last {current_time - self.last_audio_sent_time:.1f}s ({chunks_per_second:.2f} chunks/sec)")
                self.audio_chunks_sent = 0
                self.last_audio_sent_time = current_time
                
        except Exception as e:
            self.debug_print(f"\nError sending audio: {e}")
            self.debug_print(traceback.format_exc())
    
    async def handle_messages(self):
        """Handle incoming websocket messages"""
        self.debug_print("Message handler started, waiting for messages...")
        message_count = 0
        last_message_time = time.time()
        
        while True:
            try:
                # If we haven't received any message in 30 seconds, print a warning
                current_time = time.time()
                if current_time - last_message_time > 30:
                    self.debug_print(f"WARNING: No messages received in {current_time - last_message_time:.1f} seconds")
                    last_message_time = current_time
                
                # Use a timeout to periodically check if we're still receiving messages
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                    last_message_time = time.time()
                    message_count += 1
                except asyncio.TimeoutError:
                    # No message received in the timeout period, continue the loop
                    continue
                
                # Process the received message
                data = json.loads(message)
                event_type = data.get("type")
                
                # Debug output
                if event_type == "keep_alive":
                    if message_count % 10 == 0:  # Only show every 10th keep-alive
                        self.debug_print(f"Keep-alive received (message #{message_count})")
                else:
                    self.debug_print(f"Received message type: {event_type}")
                    self.debug_print(f"Message content: {json.dumps(data, indent=2)[:200]}...")
                
                # Check if this is the initial welcome message
                if event_type == "welcome" and not self.session_started:
                    self.debug_print("Received welcome message, creating transcription session...")
                    await self.create_transcription_session()
                    self.session_started = True
                    self.debug_print("Waiting for session to initialize...")
                    await asyncio.sleep(2)  # Give time for initialization
                    self.debug_print("Ready to transcribe. Start speaking...")
                    continue
                
                # Handle different message types
                elif event_type == "conversation.item.input_audio_buffer.committed":
                    item_id = data.get("item_id")
                    if item_id and item_id not in self.ordered_item_ids:
                        self.ordered_item_ids.append(item_id)
                        self.debug_print(f"Audio buffer committed, item_id: {item_id}")
                
                elif event_type == "conversation.item.input_audio_transcription.delta":
                    item_id = data.get("item_id")
                    delta = data.get("delta", "")
                    
                    if item_id not in self.item_id_to_transcription:
                        self.item_id_to_transcription[item_id] = ""
                        self.debug_print(f"New transcription item started: {item_id}")
                    
                    self.item_id_to_transcription[item_id] += delta
                    
                    # Print incremental transcription
                    print(f"\r{colored('Transcribing:', 'cyan')} {self.item_id_to_transcription[item_id]}", end="", flush=True)
                
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    item_id = data.get("item_id")
                    transcript = data.get("transcript", "")
                    
                    if transcript:
                        self.item_id_to_transcription[item_id] = transcript
                        print(f"\r{colored('Transcribed:', 'green')} {transcript}\n", flush=True)
                    else:
                        self.debug_print(f"Empty transcript received for item_id: {item_id}")
                
                elif event_type == "error":
                    error_message = data.get("message", "Unknown error")
                    self.debug_print(f"ERROR from server: {error_message}")
                    print(f"\n{colored('ERROR:', 'red')} {error_message}\n", flush=True)
                
            except websockets.exceptions.ConnectionClosed as e:
                self.debug_print(f"WebSocket connection closed: {e}")
                print(f"\n{colored('Connection closed:', 'red')} {e}\n", flush=True)
                break
            except Exception as e:
                self.debug_print(f"Error handling message: {e}")
                self.debug_print(traceback.format_exc())
                try:
                    self.debug_print(f"Last message content: {message[:200]}...")
                except:
                    pass
    
    async def run(self):
        """Run the real-time transcriber"""
        try:
            self.loop = asyncio.get_event_loop()
            
            # Connect to the WebSocket endpoint for transcription
            ws_url = "wss://api.openai.com/v1/realtime?intent=transcription"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            self.debug_print(f"Connecting to WebSocket: {ws_url}")
            self.debug_print(f"Headers: {headers}")
            
            # Test the API key format
            if not self.api_key.startswith("sk-"):
                self.debug_print("WARNING: API key doesn't start with 'sk-'. Check that you're using a valid OpenAI API key")
            
            # Connect with timeout
            try:
                async with websockets.connect(
                    ws_url,
                    additional_headers=headers,
                    ping_interval=20,  # Send ping every 20 seconds
                    ping_timeout=10,   # Wait 10 seconds for pong response
                    close_timeout=10   # Wait 10 seconds for close handshake
                ) as ws:
                    self.ws = ws
                    self.debug_print("Connected to WebSocket successfully")
                    
                    # Check if WebSocket connection is working
                    if hasattr(ws, 'open'):
                        self.debug_print(f"WebSocket.open: {ws.open}")
                    if hasattr(ws, 'closed'):
                        self.debug_print(f"WebSocket.closed: {ws.closed}")
                    
                    print(f"Transcribing in language: {self.language}")
                    print("Speak into your microphone. Press Ctrl+C to exit.")
                    
                    # Start the message handler
                    message_handler = asyncio.create_task(self.handle_messages())
                    
                    # Start recording from the microphone
                    self.debug_print("Setting up audio stream...")
                    stream = self.audio.open(
                        format=self.format,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk,
                        stream_callback=self.audio_callback
                    )
                    
                    self.debug_print("Starting audio stream...")
                    stream.start_stream()
                    self.debug_print("Microphone stream started successfully")
                    
                    # Main loop
                    try:
                        counter = 0
                        while True:
                            await asyncio.sleep(1.0)
                            counter += 1
                            if counter % 15 == 0:  # Every 15 seconds
                                self.debug_print(f"Main loop still running ({counter}s)")
                    except KeyboardInterrupt:
                        self.debug_print("\nKeyboard interrupt detected, stopping...")
                    finally:
                        # Clean up
                        self.debug_print("Cleaning up resources...")
                        stream.stop_stream()
                        stream.close()
                        message_handler.cancel()
                        
            except asyncio.TimeoutError:
                self.debug_print("Timeout while connecting to WebSocket")
                print(f"{colored('ERROR:', 'red')} Connection timeout", flush=True)
            except websockets.exceptions.WebSocketException as e:
                self.debug_print(f"WebSocket connection error: {e}")
                print(f"{colored('ERROR:', 'red')} WebSocket connection error: {e}", flush=True)
                
        except Exception as e:
            self.debug_print(f"Error in main run loop: {e}")
            self.debug_print(traceback.format_exc())
            print(f"{colored('ERROR:', 'red')} {e}", flush=True)
        finally:
            self.audio.terminate()
            self.debug_print("Audio system terminated")

def main():
    parser = argparse.ArgumentParser(description="Real-time speech transcription using OpenAI's Realtime API")
    parser.add_argument("--api-key", help="OpenAI API key (or set OPENAI_API_KEY env variable)")
    parser.add_argument("--language", default="en", help="Language code for transcription (default: en)")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Audio sample rate (default: 16000)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    print("Starting Realtime Transcriber...")
    print(f"Language: {args.language}")
    print(f"Debug mode: {'Enabled' if args.debug else 'Disabled'}")
    
    transcriber = RealtimeTranscriber(
        api_key=args.api_key,
        language=args.language,
        sample_rate=args.sample_rate,
        debug=args.debug
    )
    
    # Print Python and library versions for debugging
    if args.debug:
        print(f"Python version: {sys.version}")
        print(f"PyAudio version: {pyaudio.__version__}")
        print(f"Websockets version: {websockets.__version__}")
    
    try:
        asyncio.run(transcriber.run())
    except KeyboardInterrupt:
        print("\nProgram terminated by user")

if __name__ == "__main__":
    main()
