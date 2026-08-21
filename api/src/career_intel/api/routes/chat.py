"""Chat session and message endpoints (Task 18).

Handlers stay thin per CLAUDE.md non-negotiable #3: the LLM call, retrieval,
and citation validation all live in ``chat/service.py``. This module only
builds the ``LLMClient``/``Embedder`` for a request, translates
``LookupError``/``ValueError`` into HTTP status codes, and serialises.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.api.schemas import (
    CreateSessionRequest,
    MessageSummary,
    SendMessageRequest,
    SessionSummary,
)
from career_intel.chat import service
from career_intel.chat.service import ChatReply, ChatService
from career_intel.config import get_settings
from career_intel.db import get_session, get_session_factory
from career_intel.llm.openai_client import OpenAIClient

router = APIRouter(prefix="/chat", tags=["chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionSummary)
async def create_session(payload: CreateSessionRequest, session: SessionDep) -> SessionSummary:
    chat_session = await service.create_session(session, job_doc_id=payload.job_doc_id)
    return SessionSummary(id=chat_session.id)


@router.post("/sessions/{session_id}/messages", response_model=ChatReply)
async def send_message(
    session_id: uuid.UUID, payload: SendMessageRequest, session: SessionDep
) -> ChatReply:
    # Built per request, from settings -- mirrors
    # analysis/service.py::run_fit_analysis_background's real-client wiring.
    # Built lazily internally (OpenAIClient's own docstring), so constructing
    # it here makes no network call by itself.
    llm = OpenAIClient(session_factory=get_session_factory(), settings=get_settings())
    chat_service = ChatService(session, llm=llm, embedder=llm)

    try:
        return await chat_service.send(session_id, content=payload.content, scope=payload.scope)
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/sessions/{session_id}/messages", response_model=list[MessageSummary])
async def get_messages(session_id: uuid.UUID, session: SessionDep) -> list[MessageSummary]:
    rows = await service.list_messages(session, session_id)
    return [
        MessageSummary(
            role=row.role, content=row.content, scope=row.scope, citations=row.citations
        )
        for row in rows
    ]
