from . import Recorder, StreamParams, Transcription
import time


def main():
    # Recording
    #stream_params = StreamParams()
    #recorder = Recorder(stream_params, stop_phrase="stop recording")
    #recorder.record("./src/audio.mp3")

    # Transcription

    trans = Transcription()
    
    # Example usage
    start = time.time()
    trans("src/audio.mp3", "./test.txt")
    
    # Print results
    print("Transcription Text:", trans.result.text)
    print(trans.result)
    end = time.time()
    print(end - start)
    # To access timestamps (if using verbose_json):
    if hasattr(trans.result, 'segments'):
        for segment in trans.result.segments:
            print(f"Start: {segment.start}s - End: {segment.end}s")
            print("Text:", segment.text)




if __name__ == "__main__":
    main()
