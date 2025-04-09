import OpenAI from "openai";
import { Chronometer } from "./Chronometer";
const openai = new OpenAI();

const chrono = new Chronometer();
chrono.start();

console.log("Starting text generation...");
const completion = await openai.chat.completions.create({
  model: "gpt-4o",
  messages: [
    {
      role: "user",
      content: `Write a 5min text accusing an AI to be bad for humanity. 
        Make it structured, it should be read as it is in a court`,
    },
  ],
});

const accusationText = completion.choices[0]?.message.content;
if (!accusationText) throw new Error("No accusation text generated");

console.log("ACCUSATION TEXT : ", accusationText);
console.log("Text length: ", accusationText.length);
chrono.logTimeElapsedTime();

const mp3 = await openai.audio.speech.create({
  model: "gpt-4o-mini-tts",
  voice: "alloy",
  input: accusationText,
});

const buffer = Buffer.from(await mp3.arrayBuffer());
await Bun.file(`../audios/accusation.mp3 - ${Date.now()}.mp3`).write(buffer);

console.log("Audio file created successfully!");
chrono.logTimeElapsedTime();
