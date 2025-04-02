from pydantic import BaseModel
from typing import Union

class Problem_description(BaseModel):
    description: Union[None, str]

class Place(BaseModel):
    place: Union[None,str]

class Remote_intervention_needed(BaseModel):
    needed: Union[None, bool]

class Remote_intervention_only(BaseModel):
    only: Union[None, bool]

class Parts(BaseModel):
    parts: Union[None, list[str]]
    liquid_changed_or_added: Union[None, bool]

class Symptoms(BaseModel):
    symptoms: Union[None, str]

class Solution(BaseModel):
    solution: Union[None, str]

class Date(BaseModel):
    date: Union[None, str]

class Text_extraction(BaseModel):
    place: Place
    date: Date
    problem_description: Problem_description
    remote_int_needed: Remote_intervention_needed
    remote_int_only: Remote_intervention_only
    spare_parts: Parts
    symptoms: Symptoms
    solution: Solution
