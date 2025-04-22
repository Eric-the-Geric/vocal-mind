import { Transform } from "stream";
import type { TransformOptions } from "stream";

interface IsSilenceOptions extends TransformOptions {
  debug?: boolean;
}

class IsSilence extends Transform {
  private debug: boolean = false;
  private consecSilenceCount: number = 0;
  private numSilenceFramesExitThresh: number = 0;

  constructor(options?: IsSilenceOptions) {
    const opts = { ...options };
    super(opts);
    if (opts && opts.debug) {
      this.debug = opts.debug;
    }
  }

  getNumSilenceFramesExitThresh(): number {
    return this.numSilenceFramesExitThresh;
  }

  getConsecSilenceCount(): number {
    return this.consecSilenceCount;
  }

  setNumSilenceFramesExitThresh(numFrames: number): void {
    this.numSilenceFramesExitThresh = numFrames;
  }

  incrConsecSilenceCount(): number {
    this.consecSilenceCount++;
    return this.consecSilenceCount;
  }

  resetConsecSilenceCount(): void {
    this.consecSilenceCount = 0;
  }

  _transform(
    chunk: Buffer,
    encoding: string,
    callback: (error?: Error | null, data?: any) => void
  ): void {
    let i: number;
    let speechSample: number = 0;
    let silenceLength: number = 0;
    const numSilenceFramesExitThresh = this.getNumSilenceFramesExitThresh();

    if (numSilenceFramesExitThresh) {
      for (i = 0; i < chunk.length; i = i + 2) {
        // Make sure we have both bytes needed for the sample
        if (i + 1 < chunk.length) {
          const nexChunk = chunk[i + 1];
          if (nexChunk === undefined) {
            break;
          }
          if (nexChunk > 128) {
            speechSample = (nexChunk - 256) * 256;
          } else {
            speechSample = nexChunk * 256;
          }
          speechSample += chunk[i] || 0;

          if (Math.abs(speechSample) > 2000) {
            if (this.debug) {
              console.log("Found speech block");
            }
            this.resetConsecSilenceCount();
            break;
          } else {
            silenceLength++;
          }
        }
      }

      if (silenceLength == chunk.length / 2) {
        const consecutiveSilence = this.incrConsecSilenceCount();
        if (this.debug) {
          console.log(
            "Found silence block: %d of %d",
            consecutiveSilence,
            numSilenceFramesExitThresh
          );
        }
        // emit 'silence' only once each time the threshold condition is met
        if (consecutiveSilence === numSilenceFramesExitThresh) {
          this.emit("silence");
        }
      }
    }

    this.push(chunk);
    callback();
  }
}

export default IsSilence;
