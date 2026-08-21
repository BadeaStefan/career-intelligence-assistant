"""Document upload, paste, listing, and deletion.

Handlers stay thin: validate, delegate, serialise. The parsing rules live in
``ingest.parsing`` and the background work in ``ingest.pipeline``.
"""

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.api.schemas import DocumentSummary, PasteRequest
from career_intel.config import Settings, get_settings
from career_intel.db import get_session
from career_intel.ingest.parsing import (
    EmptyDocumentError,
    ParsedDocument,
    UnsupportedDocumentError,
    parse_document,
)
from career_intel.ingest.pipeline import (
    delete_existing_resumes,
    enrich_document,
    list_documents,
)
from career_intel.models import Document, DocumentKind

router = APIRouter(prefix="/documents", tags=["documents"])

READ_CHUNK_BYTES = 64 * 1024

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/upload", status_code=status.HTTP_201_CREATED, response_model=DocumentSummary)
async def upload_document(
    background_tasks: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
    kind: Annotated[DocumentKind, Form()],
    file: Annotated[UploadFile, File()],
) -> Document:
    data = await _read_capped(file, settings.max_upload_bytes)

    # Parsed here rather than in the background task. It is fast and local, and
    # its failures -- a scanned PDF, an unsupported type -- are things the user
    # can act on, so they belong in this response instead of in a row the user
    # discovers by polling.
    parsed = await run_in_threadpool(
        _parse_or_reject, data, file.filename or "upload", file.content_type or ""
    )

    document = Document(
        kind=kind,
        source="upload",
        filename=file.filename,
        raw_text=parsed.text,
        status="ready",
    )

    return await _persist_and_enrich(session, background_tasks, document)


@router.post("/paste", status_code=status.HTTP_201_CREATED, response_model=DocumentSummary)
async def paste_document(
    payload: PasteRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
) -> Document:
    if len(payload.text.encode()) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Pasted text exceeds the maximum accepted size.",
        )

    document = Document(
        kind=payload.kind,
        source="paste",
        title=payload.title,
        company=payload.company,
        raw_text=payload.text,
        status="ready",
    )

    return await _persist_and_enrich(session, background_tasks, document)


@router.get("", response_model=list[DocumentSummary])
async def get_documents(session: SessionDep) -> list[Document]:
    return await list_documents(session)


@router.get("/{document_id}", response_model=DocumentSummary)
async def get_document(document_id: uuid.UUID, session: SessionDep) -> Document:
    return await _require_document(session, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, session: SessionDep) -> None:
    document = await _require_document(session, document_id)

    await session.delete(document)
    await session.commit()


async def _persist_and_enrich(
    session: AsyncSession, background_tasks: BackgroundTasks, document: Document
) -> Document:
    # Spec §5: a new resume replaces the old one rather than joining it.
    # Deleted in this same transaction as the insert, so there is no window
    # in which zero resumes exist -- and none in which two do, which is the
    # state the four "current resume" lookups across this codebase silently
    # disagree about. Job documents accumulate; only resumes are singular.
    if document.kind == "resume":
        await delete_existing_resumes(session)

    session.add(document)
    await session.commit()
    await session.refresh(document)

    background_tasks.add_task(enrich_document, document.id)

    return document


async def _require_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)

    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")

    return document


def _parse_or_reject(data: bytes, filename: str, content_type: str) -> ParsedDocument:
    """Translate parsing failures into the HTTP status that describes them."""
    try:
        return parse_document(data, filename, content_type)
    except UnsupportedDocumentError as error:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)) from error
    except EmptyDocumentError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """Read the upload, refusing anything past ``limit``.

    Read in chunks rather than trusting Content-Length, which is client
    supplied and can lie, and rather than calling ``read()`` outright, which
    would pull an arbitrarily large body into memory before rejecting it.
    """
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(READ_CHUNK_BYTES):
        total += len(chunk)

        if total > limit:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Upload exceeds the maximum of {limit} bytes.",
            )

        chunks.append(chunk)

    return b"".join(chunks)
