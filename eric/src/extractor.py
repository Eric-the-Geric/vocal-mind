from openai import OpenAI
from pydantic import BaseModel
from typing import Union
import json
from .structured_output import Text_extraction

class Extractor:
    def __init__(self,
                 model_version: str = "gpt-4o-2024-08-06",
                 Text_extraction=Text_extraction,
                 path_to_system_prompt: Union[None, str]=None,
                 path_to_transcript: Union[None, str]=None,
                 path_to_task_prompt: Union[None, str]=None,
                 path_to_template: Union[None, str]=None
                 ):

        self.model_version = model_version
        self.message = None
        self.template = self._get_template(path_to_template)
        self.Text_extraction = Text_extraction
        self.client = OpenAI()
        self.transcript = self._get_transcript(path_to_transcript)
        self.messages = []
        self._generate_system_prompt(path_to_system_prompt)
        self._construct_messages(path_to_task_prompt)
        self.completion = None

    def _get_transcript(self, path_to_transcript: str):
        with open(path_to_transcript, 'r') as f:
            text = f.read()
        return text

    def _generate_system_prompt(self, path_to_system_prompt: str):
        with open(path_to_system_prompt, 'r') as f:
            text = f.read()
        system_prompt = {"role": "system", "content": text}
        self.messages.append(system_prompt)

    def _get_template(self, path_to_template):
        with open(path_to_template, 'r') as f:
            template = f.read()
        return template

    def _construct_messages(self, path_to_prompt: str):
        with open(path_to_prompt, 'r') as f:
            text = f.read()
        text = text.replace('####', self.transcript)
        user_message = {"role": "user", "content": text}
        self.messages.append(user_message)

    def extract_data(self):
        self.completion = self.client.beta.chat.completions.parse(
                model=self.model_version,
                messages=self.messages,
                response_format=Text_extraction,
            )
        self.message = self.completion.choices[0].message

        if self.message.parsed:
            new_template = self.template.replace(
                "PLACEHOLDERPLACE",
                str(getattr(self.message.parsed.place, 'place', "None")) if self.message.parsed.place else "None"
            ).replace(
                "PLACEHOLDERDESCRIPTION",
                str(getattr(self.message.parsed.problem_description, 'description', "None")) if self.message.parsed.problem_description else "None"
            ).replace(
                "PLACEHOLDERSYMPTOMS",
                str(getattr(self.message.parsed.symptoms, 'symptoms', "None")) if self.message.parsed.symptoms else "None"
            ).replace(
                "PLACEHOLDERNEEDED",
                'Y' if getattr(self.message.parsed.remote_int_needed, 'needed', False) else 'N'
            ).replace(
                "PLACEHOLDERONLY",
                'Y' if getattr(self.message.parsed.remote_int_only, 'only', False) else 'N'
            ).replace(
                "PLACEHOLDERPARTS",
                " ".join(map(str, getattr(self.message.parsed.spare_parts, 'parts', []))) if isinstance(getattr(self.message.parsed.spare_parts, 'parts', []), (list, tuple)) else "None"
            ).replace(
                "PLACEHOLDERLIQUID",
                'Y' if getattr(self.message.parsed.spare_parts, 'liquid_changed_or_added', False) else 'N'
            ).replace(
                "PLACEHOLDERSOLUTIONS",
                str(getattr(self.message.parsed.solution, 'solution', "None")) if self.message.parsed.solution else "None"
            )
            return new_template

        else:
            return False

    def __call__(self, output_path):
        new_template = self.extract_data()
        with open(output_path, 'w') as f:
            f.write(new_template)

    def save_json(self, output_path):
        self.completion = self.client.beta.chat.completions.parse(
                model=self.model_version,
                messages=self.messages,
                response_format=Text_extraction,
            )
        self.message = self.completion.choices[0].message

        if self.message.parsed:
            try:
                parsed_dict = self.message.parsed.dict()
                with open(output_path, 'w') as f:
                    json.dump(parsed_dict, f, indent=4, ensure_ascii=False)
                return True
            except Exception as e:
                print(f'Error saving JSON: {e}')
                return False
        else:
            return False

        


if __name__ == "__main__":
    extractor = Extractor(
                 path_to_system_prompt = "./prompt_templates/system_prompt.txt",
                 path_to_transcript= "./data/transcripts/French1.txt",
                 path_to_task_prompt= "./prompt_templates/task_prompt.txt",
                 path_to_template = "./generated_reports/Real_Template/GF.tex"
            )
    extractor.save_json("test.json")
