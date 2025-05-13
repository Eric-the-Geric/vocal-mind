

class CleanupAgent:
    def __init__(self,
                 client,
                 model="gpt-4.1-mini",
                 transcript_path="./outputs/transcript.txt",
                 cleanup_prompt_path="./prompts/cleanup_prompt.txt",
                 response_prompt_path = "./prompts/response_prompt.txt"
                 ):
        self.client = client
        self.transcript_path = transcript_path
        self.transcript = self._get_transcript()
        self.cleanup_prompt_path = cleanup_prompt_path
        self.transcript_messages = self._construct_transcript_message()
        self.model = model
        self.response_prompt_path = response_prompt_path

    def _get_transcript(self):
        with open(self.transcript_path, "r") as file:
            transcript = file.read()
        return transcript

    def get_prompt(self, path):
        with open(path, "r") as file:
            prompt = file.read()
        return prompt

    def _construct_transcript_message(self):
        prompt = self.get_prompt(self.cleanup_prompt_path)
        messages = [
                {
                    "role": "system",
                    "content": [
                        {
                        "type": "text",
                        #"text": "You are a model that will rewrite the transcriptions you are given. All you do is remove some filler words and change sentences that don't make sense into sentences that make sense. Do not output anything else besides the rewritten transcript"
                        #"text": "Tu es un modèle chargé de réécrire les transcriptions qu’on te fournit. Tout ce que tu fais, c’est supprimer certains mots parasites et reformuler les phrases qui n’ont pas de sens afin qu’elles en aient. Tu ne dois rien produire d’autre que la transcription réécrite."
                        "text": prompt
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
        system_prompt = self.get_prompt(self.response_prompt_path)
        messages = [
                {
                    "role": "system",
                    "content": [
                        {
                        "type": "text",
                        #"text": "You, generative artificial intelligence, are under attack by experts. Answer these criticisms in a few sentences by reversing the point of view: it is man who should be questioned and not artificial intelligence that allows us to go beyond our limits"
                        #"text": "Vous, intelligence artificielle générative, êtes attaquée par des experts. Répondez à ces critiques en quelques phrases en inversant le point de vue : c’est l’homme qu’il faut interroger et non pas l’intelligence artificielle qui nous permet de dépasser nos limites."
                        "text": system_prompt
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

    def respond_to_transcript(self):
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
            store=False,
        )
        # Example cleanup operation
        self.new_transcript = response.choices[0].message.content

        return response.choices[0].message.content
