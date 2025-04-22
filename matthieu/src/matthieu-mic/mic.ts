import { spawn, ChildProcess } from "child_process";
import type { ChildProcessWithoutNullStreams } from "child_process";
import { type } from "os";
import { PassThrough } from "stream";
import IsSilence from "./silenceTransform";

// Check OS type
const isMac = type() === "Darwin";
const isWindows = type().indexOf("Windows") > -1;

export interface MicOptions {
  endian?: "big" | "little";
  bitwidth?: string;
  encoding?: "signed-integer" | "unsigned-integer";
  rate?: string;
  channels?: string;
  device?: string;
  exitOnSilence?: number;
  fileType?: string;
  debug?: boolean;
}

export interface MicInstance {
  start: () => void;
  stop: () => void;
  pause: () => void;
  resume: () => void;
  getAudioStream: () => IsSilence;
}

const mic = function mic(options: MicOptions = {}): MicInstance {
  const that: MicInstance = {} as MicInstance;

  // Set default options
  const endian = options.endian || "little";
  const bitwidth = options.bitwidth || "16";
  const encoding = options.encoding || "signed-integer";
  const rate = options.rate || "16000";
  const channels = options.channels || "1";
  const device = options.device || "plughw:1,0";
  const exitOnSilence = options.exitOnSilence || 0;
  const fileType = options.fileType || "raw";
  const debug = options.debug || false;

  // Format variables
  let format: string;
  let formatEndian: string;
  let formatEncoding: string;

  let audioProcess: ChildProcess | null = null;
  const infoStream = new PassThrough();
  const audioStream = new IsSilence({ debug });

  const audioProcessOptions = {
    stdio: ["ignore", "pipe", "ignore"] as ("ignore" | "pipe")[],
  };

  if (debug) {
    audioProcessOptions.stdio[2] = "pipe";
  }

  // Setup format variable for arecord call
  if (endian === "big") {
    formatEndian = "BE";
  } else {
    formatEndian = "LE";
  }

  if (encoding === "unsigned-integer") {
    formatEncoding = "U";
  } else {
    formatEncoding = "S";
  }

  format = formatEncoding + bitwidth + "_" + formatEndian;
  audioStream.setNumSilenceFramesExitThresh(
    parseInt(exitOnSilence.toString(), 10)
  );

  that.start = function start(): void {
    if (audioProcess === null) {
      if (isWindows) {
        audioProcess = spawn(
          "sox",
          [
            "-b",
            bitwidth,
            "--endian",
            endian,
            "-c",
            channels,
            "-r",
            rate,
            "-e",
            encoding,
            "-t",
            "waveaudio",
            "default",
            "-p",
          ],
          audioProcessOptions
        );
      } else if (isMac) {
        audioProcess = spawn(
          "rec",
          [
            "-b",
            bitwidth,
            "--endian",
            endian,
            "-c",
            channels,
            "-r",
            rate,
            "-e",
            encoding,
            "-t",
            fileType,
            "-",
          ],
          audioProcessOptions
        );
      } else {
        audioProcess = spawn(
          "arecord",
          ["-c", channels, "-r", rate, "-f", format, "-D", device],
          audioProcessOptions
        );
      }

      if (audioProcess) {
        audioProcess.on(
          "exit",
          function (code: number | null, sig: string | null) {
            if (code != null && sig === null) {
              audioStream.emit("audioProcessExitComplete");
              if (debug)
                console.log(
                  "recording audioProcess has exited with code = %d",
                  code
                );
            }
          }
        );

        if (audioProcess.stdout) {
          audioProcess.stdout.pipe(audioStream);
        }

        if (debug && audioProcess.stderr) {
          audioProcess.stderr.pipe(infoStream);
        }
      }

      audioStream.emit("startComplete");
    } else {
      if (debug) {
        throw new Error(
          "Duplicate calls to start(): Microphone already started!"
        );
      }
    }
  };

  that.stop = function stop(): void {
    if (audioProcess != null) {
      audioProcess.kill("SIGTERM");
      audioProcess = null;
      audioStream.emit("stopComplete");
      if (debug) console.log("Microhphone stopped");
    }
  };

  that.pause = function pause(): void {
    if (audioProcess != null) {
      audioProcess.kill("SIGSTOP");
      audioStream.pause();
      audioStream.emit("pauseComplete");
      if (debug) console.log("Microphone paused");
    }
  };

  that.resume = function resume(): void {
    if (audioProcess != null) {
      audioProcess.kill("SIGCONT");
      audioStream.resume();
      audioStream.emit("resumeComplete");
      if (debug) console.log("Microphone resumed");
    }
  };

  that.getAudioStream = function getAudioStream(): IsSilence {
    return audioStream;
  };

  if (debug) {
    infoStream.on("data", function (data: Buffer) {
      console.log("Received Info: " + data.toString());
    });

    infoStream.on("error", function (error: Error) {
      console.log("Error in Info Stream: " + error.message);
    });
  }

  return that;
};

export default mic;
