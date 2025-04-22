import fs from "fs";
import path from "path";
import { Readable } from "stream";

import mic from "./matthieu-mic";

function recordAudio(filename: string) {
  return new Promise((resolve, reject) => {
    const micInstance = mic({
      channels: "2",
      fileType: "wav",
      debug: true,
    });

    const micInputStream = micInstance.getAudioStream();
    const output = fs.createWriteStream(filename);
    const writable = new Readable().wrap(micInputStream);

    console.log("Recording... Press Ctrl+C to stop.");

    writable.pipe(output);

    micInstance.start();

    process.on("SIGINT", () => {
      micInstance.stop();
      console.log("Finished recording");
      resolve(true);
    });

    micInputStream.on("error", (err: Error) => {
      reject(err);
    });
  });
}

recordAudio("output.wav");
