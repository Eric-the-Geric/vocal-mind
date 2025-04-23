

class CleanupAgent:
    def __init__(self, client, model="gpt-4.1-mini", transcript_path="./outputs/transcript.txt"):
        self.client = client
        self.transcript_path = transcript_path
        self.transcript = self._get_transcript()
        self.transcript_messages = self._construct_transcript_message()
        self.model = model


    def _get_transcript(self):
        with open(self.transcript_path, "r") as file:
            transcript = file.read()
        return transcript



    def _construct_transcript_message(self):
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
    def _construct_response_message(self):
        messages = [
                {
                    "role": "system",
                    "content": [
                        {
                        "type": "text",
                        "text": "You, generative artificial intelligence, are under attack by experts. Answer these criticisms in a few sentences by reversing the point of view: it is man who should be questioned and not artificial intelligence that allows us to go beyond our limits"
                        }
                        ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self.new_transcript
                        }
                    ]
                }
                ]
        return messages

    def respons_to_transcript(self):
        response = self.client.chat.completions.create(
            model="gpt-4.1",
            messages=self._construct_response_message(),
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
        return response.choices[0].message.content

    def run(self):
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=self.transcript_messages,
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
        self.new_transcript = response.choices[0].message.content

        return response.choices[0].message.content
