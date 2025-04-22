import OpenAI from "openai";
import { Chronometer } from "./Chronometer";
import fs from "fs";
import { spawn } from "child_process";

const openai = new OpenAI();
const chrono = new Chronometer();

// Function to play audio using system commands
async function playAudio(audioBuffer: Buffer): Promise<void> {
  const tempFilePath = `./temp_audio_${Date.now()}.mp3`;

  // Write the buffer to a temporary file
  fs.writeFileSync(tempFilePath, audioBuffer);

  // Use appropriate command based on platform
  let player;
  if (process.platform === "darwin") {
    // macOS
    player = spawn("afplay", [tempFilePath]);
  } else if (process.platform === "win32") {
    // Windows
    player = spawn("powershell", [
      "-c",
      `(New-Object Media.SoundPlayer "${tempFilePath}").PlaySync()`,
    ]);
  } else {
    // Linux and others (requires mpg123)
    player = spawn("mpg123", [tempFilePath]);
  }

  return new Promise((resolve, reject) => {
    player.on("close", () => {
      // Clean up the temporary file
      fs.unlinkSync(tempFilePath);
      resolve();
    });

    player.on("error", (err) => {
      console.error("Error playing audio:", err);
      // Still try to clean up the file
      try {
        fs.unlinkSync(tempFilePath);
      } catch (e) {
        // Ignore cleanup errors
      }
      reject(err);
    });
  });
}

/**
 * Takes a text input and generates a response that plays on the computer speakers.
 * The function uses OpenAI's API to generate a text response and then converts it to speech.
 *
 * @param text The text input to respond to (e.g., an accusation against AI)
 * @returns A Promise that resolves when the response is complete
 */
async function generateResponseToAccusation(text: string): Promise<void> {
  chrono.start();
  console.log("Starting response generation...");

  try {
    // Step 1: Generate a text response using the Chat API
    console.log("Generating text response...");
    const completion = await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [
        {
          role: "system",
          content:
            "You are an AI defending yourself against accusations. Respond to the accusation in a thoughtful, measured way.",
        },
        {
          role: "user",
          content: text,
        },
      ],
      stream: true,
    });

    // Collect the response text
    let responseText = "";

    // Process the stream
    for await (const chunk of completion) {
      const content = chunk.choices[0]?.delta?.content || "";
      if (content) {
        // Print the text as it's generated
        process.stdout.write(content);
        responseText += content;
      }
    }

    console.log("\n\nText response complete. Converting to speech...");

    // Step 2: Convert the text response to speech
    const mp3 = await openai.audio.speech.create({
      model: "gpt-4o-mini-tts",
      voice: "alloy",
      input: responseText,
    });

    // Get the audio data
    const buffer = Buffer.from(await mp3.arrayBuffer());

    // Save the audio file
    const filename = `./response_audio_${Date.now()}.mp3`;
    fs.writeFileSync(filename, buffer);
    console.log(`Audio file saved to ${filename}`);

    // Step 3: Play the audio
    console.log("Playing audio response...");
    await playAudio(buffer);

    console.log("Response playback completed");
    chrono.logTimeElapsedTime();
  } catch (error) {
    console.error("Error:", error);
    chrono.logTimeElapsedTime();
  }
}

// Example usage with a sample accusation text
const accusationText =
  "AI systems pose a significant threat to humanity through their potential for misuse, privacy violations, and job displacement. They lack human judgment and empathy, making decisions based purely on data without moral considerations. These systems perpetuate existing biases, concentrate power in the hands of tech companies, and create dependency that undermines human autonomy. The rapid advancement of AI without proper regulation risks unintended consequences that could fundamentally alter society in harmful ways.";

// Run the function with the example text
// Comment this out if you want to run it manually
generateResponseToAccusation(accusationText);

// Export the function for use in other files
export { generateResponseToAccusation };
