"""Pydantic shapes the LLM must fill in during interview-prep generation.

Mirrors ``analysis/schemas.py``'s ``RequirementVerdict``/``MatchBatchResult``
pairing: short handles, not UUIDs, survive tokenisation, and every citation
the model returns is validated in Python (``analysis/validation.py``) rather
than trusted (spec §6b).
"""

from pydantic import BaseModel


class PrepQuestionOut(BaseModel):
    question: str
    probes_requirement_handle: str
    why_they_will_ask: str
    how_to_frame: str
    evidence_handles: list[str]


class PrepBatchResult(BaseModel):
    questions: list[PrepQuestionOut]
