"""Pydantic shapes the LLM must fill in during fit-analysis matching.

Mirrors ``ingest/schemas.py``: short handles, not UUIDs, survive
tokenisation, and the model's citations are validated in Python
(``analysis/validation.py``) rather than trusted (spec §5).
"""

from typing import Literal

from pydantic import BaseModel


class RequirementVerdict(BaseModel):
    requirement_handle: str
    verdict: Literal["strong", "partial", "missing"]
    rationale: str
    evidence_handles: list[str]


class MatchBatchResult(BaseModel):
    verdicts: list[RequirementVerdict]
