
class CleanupAgent:
    def __init__(self, client, model="gpt-4.1-mini", transcript_path="./outputs/transcript.txt"):
        self.client = client
        self.transcript_path = transcript_path
        self.transcript = self._get_transcript()
        self.messages = self._construct_message()
        self.model = model


    def _get_transcript(self):
        with open(self.transcript_path, "r") as file:
            transcript = file.read()
        return transcript

    def _construct_message(self):
        messages = [
                {
                    "role": "system",
                    "content": [
                        {
                        "type": "text",
                        "text": "You are a model that will rewrite the transcriptions you are given. All you do is remove some filler words and change sentences that don't make sense into sentences that make sense. Do not output anything else besides the rewritten transcript"
                        }
                        ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self.transcript
                        }
                    ]
                }
                ]
        return messages
    def run(self):
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=self.messages,
            response_format={
            "type": "text"
            },
            temperature=1,
            max_completion_tokens=32768,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            store=False
        )
        # Example cleanup operation

        return response
