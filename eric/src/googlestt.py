import argparse
import time
import speech_recognition as sr

def main():
    parser = argparse.ArgumentParser(
        description="Real-time speech transcription CLI tool."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="transcription.txt",
        help="Output text file where the transcriptions will be saved (default: transcription.txt)"
    )
    args = parser.parse_args()

    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    # Define a callback function that will be called from the background thread
    def callback(recognizer, audio):
        try:
            # Use Google Web Speech API to transcribe the audio
            transcription = recognizer.recognize_google(audio)
            print("You said:", transcription)
            # Append the transcribed text to the output file
            with open(args.output, "a", encoding="utf-8") as f:
                f.write(transcription + "\n")
        except sr.UnknownValueError:
            print("Could not understand audio")
        except sr.RequestError as e:
            print(f"Could not request results; {e}")

    # Use the microphone as source and adjust for ambient noise
    with microphone as source:
        print("Calibrating microphone for ambient noise... Please wait.")
        recognizer.adjust_for_ambient_noise(source, duration=2)
        print("Calibration complete. Listening... (Press Ctrl+C to stop)")

    # Start listening in the background
    stop_listening = recognizer.listen_in_background(microphone, callback)

    try:
        # Keep the program running indefinitely while listening in the background
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        # Stop background listening when user interrupts (Ctrl+C)
        stop_listening(wait_for_stop=False)
        print("\nStopped listening. Transcription saved to:", args.output)

if __name__ == "__main__":
    main()
