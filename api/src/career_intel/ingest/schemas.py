"""Pydantic shapes the LLM must fill in during structured extraction.

``quote`` is mandatory and must be verbatim -- ``locate.py`` finds it in
``raw_text``; the model is never asked for offsets (spec section 3).
"""

from typing import Literal

from pydantic import BaseModel


class ExtractedEvidence(BaseModel):
    kind: Literal["skill", "achievement", "role"]
    text: str
    quote: str


class ResumeExtraction(BaseModel):
    evidence: list[ExtractedEvidence]


class ExtractedRequirement(BaseModel):
    text: str
    importance: Literal["required", "preferred"]
    category: str


class JobExtraction(BaseModel):
    title: str | None
    company: str | None
    requirements: list[ExtractedRequirement]
