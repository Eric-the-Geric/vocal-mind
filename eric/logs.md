
# LOGS for optimization of the system:

Using 10 minutes of audio (in english as a .mp3 -> which is 3.7M (max 25 M per 
chunk for openai api) takes 27 seconds. I think that is too long. 


# A couple ideas for improvment.

1. Real time transcription with FastWHsiper
2. Real time trnascription creating a websocket with openai realtime api
3. splitting the audio into small single sentence or so chunks -> async send to be transcribed and then put together with an llm to fix mistakes



What do you think about that?



