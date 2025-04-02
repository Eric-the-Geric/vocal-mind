#import torch
#from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
import openai
import os
from typing import Optional

# this class uses the openai api so computation is done on their servers (not necessarily safe)
class Transcription:
    def __init__(self, model_id: str = "gpt-4o-transcribe"):
        """Initialize the OpenAI client and API parameters."""
        self.client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")  # Ensure your API key is set in environment
        )
        self.model_id = model_id
        self.kwargs = self._generate_kwargs()
        self.result = None

    def _generate_kwargs(self) -> dict:
        """Generate parameters for the OpenAI API call."""
        return {
            "model": self.model_id,
            "temperature": 0.0,  # Single float instead of tuple
            "response_format": "json",  # For timestamps
            # "timestamp_granularities": ["word"],  # Uncomment for word-level timestamps
            # Add other supported parameters here (e.g., "language")
        }

    def save_transcript(self, path_to_transcript: str) -> None:
        """Save the transcribed text to a file."""
        with open(path_to_transcript, 'w') as f:
            f.write(self.result.text)

    def transcribe_audio(self, path_to_audio: str) -> dict:
        """Transcribe audio using OpenAI's API."""
        with open(path_to_audio, "rb") as audio_file:
            self.result = self.client.audio.transcriptions.create(
                file=audio_file,
                **self.kwargs
            )
        return self.result

    def __call__(self, path_to_audio: str, path_to_transcript: str) -> None:
        """Handle full transcription pipeline."""
        self.transcribe_audio(path_to_audio)
        self.save_transcript(path_to_transcript)


if __name__ == "__main__":
    trans = Transcription()
    
    # Example usage
    trans("audio.wav", "./transcript.txt")
    
    # Print results
    print("Transcription Text:", trans.result.text)
    # To access timestamps (if using verbose_json):
    if hasattr(trans.result, 'segments'):
        for segment in trans.result.segments:
            print(f"Start: {segment.start}s - End: {segment.end}s")
            print("Text:", segment.text)

