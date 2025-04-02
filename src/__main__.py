from . import Recorder, StreamParams, Transcription


def main():
    # Recording
    stream_params = StreamParams()
    recorder = Recorder(stream_params, stop_phrase="stop recording")
    recorder.record("audio.wav")

    # Transcription

    trans = Transcription()
    
    # Example usage
    trans("audio.wav", "./transcript.txt")
    
    # Print results
    print("Transcription Text:", trans.result.text)
    print(trans.result)
    # To access timestamps (if using verbose_json):
    if hasattr(trans.result, 'segments'):
        for segment in trans.result.segments:
            print(f"Start: {segment.start}s - End: {segment.end}s")
            print("Text:", segment.text)




if __name__ == "__main__":
    main()
