import OpenAI from "openai";
const openai = new OpenAI();

const completion = await openai.chat.completions.create({
  model: "gpt-4o",
  messages: [
    {
      role: "user",
      content: `Write a short text accusing an AI to be bad for humanity. 
        Make it structured, it should be read as it is in a court`,
    },
  ],
});

const accusationText = completion.choices[0]?.message.content;
console.log("ACCUSATION TEXT : ", accusationText);

if (!accusationText) throw new Error("No accusation text generated");

const mp3 = await openai.audio.speech.create({
  model: "gpt-4o-mini-tts",
  voice: "alloy",
  input: accusationText,
});

const buffer = Buffer.from(await mp3.arrayBuffer());
await Bun.file("accusation.mp3").write(buffer);
