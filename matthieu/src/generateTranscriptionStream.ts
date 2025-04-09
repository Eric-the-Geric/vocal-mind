import OpenAI from "openai";
import fs from "fs";
import path from "path";

const openai = new OpenAI();

const audioReadStream = fs.createReadStream(path.resolve("./accusation.mp3"));

const stream = await openai.audio.transcriptions.create({
  file: audioReadStream,
  model: "gpt-4o-mini-transcribe",
  stream: true,
});

for await (const event of stream) {
  if (event.type === "transcript.text.delta") {
    process.stdout.write(event.delta);
  }
}
