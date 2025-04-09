#!/usr/bin/env python3
import argparse
import asyncio
import json
import sys
import time

import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer

# -----------------------------------------------------------------------------
# Session Class
# -----------------------------------------------------------------------------
class Session:
    def __init__(self, api_key):
        self.api_key = api_key
        self.use_session_token = True
        self.ms = None        # Media stream track (an audio MediaStreamTrack)
        self.pc = None        # RTCPeerConnection
        self.dc = None        # Data channel for messages/control
        self.muted = False

        # Callback placeholders—set these from your main code.
        self.ontrack = None
        self.onconnectionstatechange = None
        self.onopen = None
        self.onmessage = None
        self.onerror = None

    async def start(self, stream, session_config):
        """Starts a non‑transcription session (if needed) using the given stream."""
        await self.start_internal(stream, session_config, "/v1/realtime/sessions")

    async def start_transcription(self, stream, session_config):
        """Starts a transcription session using the provided audio track and config."""
        await self.start_internal(stream, session_config, "/v1/realtime/transcription_sessions")

    def stop(self):
        """Stops the session by closing the data channel, the peer connection,
           and stopping the media track (if possible)."""
        if self.dc:
            self.dc.close()
            self.dc = None
        if self.pc:
            # Close returns a coroutine; we create a task so we don't block here.
            asyncio.create_task(self.pc.close())
            self.pc = None
        if self.ms and hasattr(self.ms, "stop"):
            self.ms.stop()
            self.ms = None
        self.muted = False

    def mute(self, muted):
        """Mute (or unmute) the audio track. Actual muting may require a custom implementation."""
        self.muted = muted
        # In aiortc, MediaStreamTracks do not typically have an 'enabled' property.
        # Implement track swapping or stopping if you need to mute the audio.

    async def start_internal(self, stream, session_config, token_endpoint):
        """
        Common logic for both session and transcription session:
          • Save the media stream (audio track).
          • Create an RTCPeerConnection and attach the audio track.
          • Setup callbacks for incoming tracks, connection state, and data channel events.
          • Create and send an SDP offer using signaling via HTTP.
        """
        self.ms = stream
        self.pc = RTCPeerConnection()

        # Add the audio track to the PeerConnection.
        self.pc.addTrack(stream)

        @self.pc.on("track")
        def on_track(track):
            if self.ontrack:
                self.ontrack(track)

        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if self.onconnectionstatechange:
                self.onconnectionstatechange(self.pc.connectionState)

        # Create a data channel (used to exchange messages) with an empty label.
        self.dc = self.pc.createDataChannel("")
        @self.dc.on("open")
        def on_open():
            if self.onopen:
                self.onopen()

        @self.dc.on("message")
        def on_message(message):
            try:
                data = json.loads(message)
                if self.onmessage:
                    self.onmessage(data)
            except Exception as e:
                if self.onerror:
                    self.onerror(e)

        # Create an SDP offer and set it as the local description.
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        try:
            answer = await self.signal(offer, session_config, token_endpoint)
            remote_desc = RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            await self.pc.setRemoteDescription(remote_desc)
        except Exception as e:
            if self.onerror:
                self.onerror(e)

    async def signal(self, offer, session_config, token_endpoint):
        """
        Handles signaling with the OpenAI realtime API:
          • If using session tokens, first requests a session token.
          • Then sends the offer’s SDP to the realtime endpoint and returns the answer.
        """
        url_root = "https://api.openai.com"
        realtime_url = f"{url_root}/v1/realtime"
        sdp_response_text = None

        if self.use_session_token:
            session_url = f"{url_root}{token_endpoint}"
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "openai-beta": "realtime-v1",
                    "Content-Type": "application/json"
                }
                async with session.post(session_url, headers=headers, json=session_config) as resp:
                    if resp.status != 200:
                        raise Exception("Failed to request session token")
                    session_data = await resp.json()
                    client_secret = session_data.get("client_secret", {}).get("value")
                    if not client_secret:
                        raise Exception("Client secret not returned from session token request")
            offer_sdp = offer.sdp
            headers2 = {
                "Authorization": f"Bearer {client_secret}",
                "Content-Type": "application/sdp"
            }
            async with aiohttp.ClientSession() as session2:
                async with session2.post(realtime_url, headers=headers2, data=offer_sdp) as resp2:
                    if resp2.status != 200:
                        raise Exception("Failed to signal SDP offer")
                    sdp_response_text = await resp2.text()
        else:
            from aiohttp import FormData
            form = FormData()
            form.add_field("session", json.dumps(session_config))
            form.add_field("sdp", offer.sdp)
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                async with session.post(realtime_url, headers=headers, data=form) as resp:
                    if resp.status != 200:
                        raise Exception("Failed to signal SDP offer")
                    sdp_response_text = await resp.text()

        return {"type": "answer", "sdp": sdp_response_text}

    def send_message(self, message):
        """Sends a JSON-encoded message over the data channel."""
        if self.dc:
            self.dc.send(json.dumps(message))


# -----------------------------------------------------------------------------
# Global Variables and Callbacks for Transcription Events
# -----------------------------------------------------------------------------
global_vad_time = None  # Used to compute latency for demonstration

def handle_message(message):
    global global_vad_time
    msg_type = message.get("type")
    if msg_type == "transcription_session.created":
        session_info = message.get("session", {})
        print(f"\nSession created: {session_info.get('id', 'unknown')}")
    elif msg_type == "input_audio_buffer.speech_started":
        print("...", end="", flush=True)
    elif msg_type == "input_audio_buffer.speech_stopped":
        print("***", end="", flush=True)
        silence_duration_ms = message.get("silence_duration_ms", 1000)
        global_vad_time = time.perf_counter() - (silence_duration_ms / 1000)
    elif msg_type == "conversation.item.input_audio_transcription.completed":
        transcript = message.get("transcript", "")
        if global_vad_time is not None:
            elapsed_ms = int((time.perf_counter() - global_vad_time) * 1000)
        else:
            elapsed_ms = 0
        print(f"\n{transcript} (latency: {elapsed_ms} ms)")
    else:
        print(f"\nMessage: {message}")

def handle_error(e):
    print(f"\nError: {e}")
    sys.exit(1)

def handle_connection_state_change(state):
    print(f"Connection state: {state}")

def handle_open():
    print("Data channel is open.")


# -----------------------------------------------------------------------------
# Main Function
# -----------------------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(
        description="Realtime Transcription Command-Line Client using OpenAI API (WebRTC via aiortc)"
    )
    parser.add_argument("--api-key", required=True, help="Your OpenAI API key.")
    parser.add_argument("--model", default="whisper-1", help="Transcription model to use.")
    parser.add_argument("--prompt", default="", help="Optional transcription prompt.")
    parser.add_argument("--turn-detection", default="default", help="Type of turn detection to use.")
    parser.add_argument("--silence-duration-ms", type=int, default=1000,
                        help="Silence duration (ms) used for turn detection latency computation.")
    parser.add_argument("--mode", choices=["microphone", "file"], default="microphone",
                        help="Input mode: 'microphone' for live capture or 'file' for audio file input.")
    parser.add_argument("--file", help="Path to audio file (required if mode is 'file').")
    args = parser.parse_args()

    if args.mode == "file" and not args.file:
        print("For file mode you must supply --file.")
        sys.exit(1)

    # Build the session configuration (mirroring the JavaScript config structure).
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

    # Create the transcription session.
    session = Session(args.api_key)
    session.onconnectionstatechange = handle_connection_state_change
    session.onmessage = handle_message
    session.onerror = handle_error
    session.onopen = handle_open

    # Select the audio input using aiortc's MediaPlayer.
    if args.mode == "file":
        print(f"Starting transcription from file: {args.file}")
        player = MediaPlayer(args.file)
        audio_track = player.audio
        if audio_track is None:
            print("No audio track found in the file.")
            sys.exit(1)
    else:
        print("Starting microphone transcription...")
        # For microphone input you may need to adjust the device name/back-end depending on your OS.
        # The example below uses "default" with PulseAudio (common on Linux).
        player = MediaPlayer("default", format="pulse")
        audio_track = player.audio
        if audio_track is None:
            print("No audio track found for microphone.")
            sys.exit(1)

    # Start the transcription session.
    await session.start_transcription(audio_track, session_config)
    print("Transcription session ended.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
