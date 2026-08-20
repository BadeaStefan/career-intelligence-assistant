"""Request and response models for the HTTP layer.

Kept separate from the ORM models so the wire format is an explicit decision
rather than a side effect of the schema. ``raw_text`` in particular is never
serialised: it is the user's resume.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from career_intel.models import DocumentKind


class PasteRequest(BaseModel):
    kind: DocumentKind
    text: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=512)
    company: str | None = Field(default=None, max_length=512)


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DocumentKind
    source: Literal["upload", "paste"]
    title: str | None
    company: str | None
    filename: str | None
    status: Literal["pending", "ready", "failed"]
    extraction_status: Literal["pending", "ready", "failed"]
    created_at: datetime
