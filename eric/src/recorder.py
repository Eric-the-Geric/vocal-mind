
from dataclasses import dataclass, asdict
import wave
import pyaudio
import speech_recognition as sr
from typing import Optional

@dataclass
class StreamParams:
    format: int = pyaudio.paInt16
    channels: int = 1  # Use mono for speech recognition
    rate: int = 16000  # Recommended sample rate for speech recognition
    frames_per_buffer: int = 2048
    input: bool = True
    output: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

class Recorder:
    def __init__(self, stream_params: StreamParams, stop_phrase: str) -> None:
        self.stream_params = stream_params
        self.stop_phrase = stop_phrase.lower()
        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._stream = None
        self._wav_file = None
        self.should_stop = False
        self.recognizer = sr.Recognizer()
        self.save_path = None

    def stop_recording(self):
        self.should_stop = True
        print("Stopping recording and saving file...")


    def record(self, save_path: str) -> None:
        self.save_path = save_path
        print(f"Recording... Say '{self.stop_phrase}' to stop.")
        self._create_recording_resources(save_path)

        # Buffer to accumulate audio data for recognition
        audio_buffer = b""
        # Calculate bytes per second of audio (sample width * rate * channels)
        bytes_per_frame = self._pyaudio.get_sample_size(self.stream_params.format)
        bytes_per_second = self.stream_params.rate * bytes_per_frame * self.stream_params.channels

        try:
            while not self.should_stop:
                audio_data = self._stream.read(
                    self.stream_params.frames_per_buffer,
                    exception_on_overflow=False
                )
                self._wav_file.writeframes(audio_data)
                audio_buffer += audio_data

                # Once we have roughly one second of audio, check for the stop phrase.
                if len(audio_buffer) >= bytes_per_second:
                    if self.phrase_detected(audio_buffer):
                        print(f"Phrase '{self.stop_phrase}' detected. Stopping recording.")
                        self.stop_recording()
                        break
                    else:
                        # Reset the buffer for the next segment
                        audio_buffer = b""
        except KeyboardInterrupt:
            print("Recording interrupted by user.")
        finally:
            self._close_recording_resources()
            print(f"Recording saved to {self.save_path}")

    def _create_recording_resources(self, save_path: str) -> None:
        self._pyaudio = pyaudio.PyAudio()
        self._stream = self._pyaudio.open(**self.stream_params.to_dict())
        self._create_wav_file(save_path)

    def _create_wav_file(self, save_path: str):
        self._wav_file = wave.open(save_path, "wb")
        self._wav_file.setnchannels(self.stream_params.channels)
        self._wav_file.setsampwidth(self._pyaudio.get_sample_size(self.stream_params.format))
        self._wav_file.setframerate(self.stream_params.rate)

    def _close_recording_resources(self) -> None:
        if self._wav_file:
            self._wav_file.close()
        if self._stream:
            self._stream.close()
        if self._pyaudio:
            self._pyaudio.terminate()

    def phrase_detected(self, audio_chunk):
        # Create an AudioData instance from the buffered audio
        audio = sr.AudioData(
            audio_chunk,
            self.stream_params.rate,
            self._pyaudio.get_sample_size(self.stream_params.format)
        )
        try:
            text = self.recognizer.recognize_google(audio).lower()
            print(f"Heard: '{text}'")
            return self.stop_phrase in text
        except sr.UnknownValueError:
            return False
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            return False

if __name__ == "__main__":
    stream_params = StreamParams()
    recorder = Recorder(stream_params, stop_phrase="stop recording")
    recorder.record("audio_test.wav")
