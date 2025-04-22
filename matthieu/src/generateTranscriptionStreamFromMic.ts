import OpenAI from "openai";
import Microphone from "node-microphone";
import fs from "fs";
import path from "path";

const openai = new OpenAI();

// Create a temporary file path for the microphone recording
const tempFilePath = path.resolve(`./temp_audio_transcription.mp3`);

// Create a microphone instance
const mic = new Microphone();

// Create a write stream to save the microphone input to a file
const fileWriteStream = fs.createWriteStream(tempFilePath);

console.log("Recording from microphone...");
console.log("Press Ctrl+C to stop recording");

// Start the microphone stream and pipe it to the file
const micStream = mic.startRecording();
micStream.pipe(fileWriteStream);

// Set up a flag to track when we're ready to transcribe
let isRecording = true;

// Handle cleanup and transcription when the process is terminated
process.on("SIGINT", async () => {
  if (!isRecording) return;

  console.log("\nStopping recording...");
  mic.stopRecording();
  isRecording = false;

  // Close the file write stream
  fileWriteStream.end();
});
