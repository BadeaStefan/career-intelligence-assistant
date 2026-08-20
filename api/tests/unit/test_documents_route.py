import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from career_intel.config import get_settings
from career_intel.ingest.pipeline import enrich_document
from career_intel.models import Document
from tests.fixtures.builders import RESUME_LINES, make_imageonly_pdf, make_text_pdf

PLAIN_RESUME = "\n".join(RESUME_LINES).encode()
JOB_TEXT = (
    "Senior Backend Engineer at Datadog.\n"
    "Requirements: 5+ years Python, distributed systems experience,\n"
    "Kubernetes at scale, Go preferred."
)


@pytest.fixture(autouse=True)
def _stub_background_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise the HTTP contract, not enrichment.

    ``client`` runs FastAPI's BackgroundTasks synchronously, and enrichment
    now makes real Embedder/LLMClient calls when nothing is injected --
    coverage for that path belongs to test_ingest_pipeline.py, which injects
    fakes directly. Stubbed here so an upload/paste under TestClient never
    reaches the network.
    """

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("career_intel.api.routes.documents.enrich_document", _noop)


def test_upload_stores_parsed_text(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("cv.pdf", make_text_pdf(RESUME_LINES), "application/pdf")},
        data={"kind": "resume"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["source"] == "upload"


def test_upload_leaves_extraction_pending(client: TestClient) -> None:
    """Text is stored, but the structured records are not built yet.

    ``status`` answers "is this usable at all" and is satisfied by parsing.
    ``extraction_status`` tracks the background LLM work, which has not run.
    """
    body = client.post(
        "/documents/upload",
        files={"file": ("cv.txt", PLAIN_RESUME, "text/plain")},
        data={"kind": "resume"},
    ).json()

    assert body["extraction_status"] in {"pending", "ready"}


def test_paste_creates_a_document(client: TestClient) -> None:
    response = client.post(
        "/documents/paste",
        json={"kind": "job", "text": JOB_TEXT, "title": "Senior Backend Engineer"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "paste"
    assert body["title"] == "Senior Backend Engineer"


def test_scanned_pdf_fails_the_request_rather_than_the_row(client: TestClient) -> None:
    """Parsing happens in the request, so this is an answer, not a discovery.

    Were parsing deferred to the background task, the user would receive 201
    and only learn minutes later, by polling, that their upload was unusable.
    """
    response = client.post(
        "/documents/upload",
        files={"file": ("scan.pdf", make_imageonly_pdf(), "application/pdf")},
        data={"kind": "resume"},
    )

    assert response.status_code == 422
    assert "no usable text" in response.json()["detail"].lower()


def test_rejects_oversize_upload(client: TestClient) -> None:
    oversize = b"x" * (get_settings().max_upload_bytes + 1)

    response = client.post(
        "/documents/upload",
        files={"file": ("big.txt", oversize, "text/plain")},
        data={"kind": "resume"},
    )

    assert response.status_code == 413


def test_rejects_unsupported_content_type(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        data={"kind": "resume"},
    )

    assert response.status_code == 415


def test_rejects_unknown_kind(client: TestClient) -> None:
    response = client.post("/documents/paste", json={"kind": "banana", "text": JOB_TEXT})

    assert response.status_code == 422


def test_lists_documents_newest_first(client: TestClient) -> None:
    client.post("/documents/paste", json={"kind": "job", "text": JOB_TEXT, "title": "First"})
    client.post("/documents/paste", json={"kind": "job", "text": JOB_TEXT, "title": "Second"})

    listed = client.get("/documents").json()

    assert [doc["title"] for doc in listed] == ["Second", "First"]


def test_deletes_a_document(client: TestClient) -> None:
    created = client.post("/documents/paste", json={"kind": "job", "text": JOB_TEXT}).json()

    assert client.delete(f"/documents/{created['id']}").status_code == 204
    assert client.get(f"/documents/{created['id']}").status_code == 404


def test_missing_document_returns_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    assert client.get(f"/documents/{missing}").status_code == 404


async def test_enrichment_failure_settles_the_row_and_reraises(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live-process half of the pending-leak problem.

    An exception inside the task would otherwise leave extraction_status at
    pending forever while the UI waits. The row is settled first, then the
    error propagates so it still reaches the logs. Spec section 3.
    """
    doc = Document(kind="resume", source="paste", raw_text="x" * 100, status="ready")
    session.add(doc)
    await session.commit()

    async def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("extraction provider unavailable")

    monkeypatch.setattr("career_intel.ingest.pipeline._run_enrichment", explode)

    with pytest.raises(RuntimeError):
        await enrich_document(doc.id)

    await session.refresh(doc)
    assert doc.extraction_status == "failed"
