"""Settings must resolve the same env file regardless of where the process starts.

`env_file=".env"` is resolved by pydantic against the process working
directory. That makes configuration depend on the directory uvicorn happens to
be launched from: the repo root and `api/` hold different files, and anywhere
else holds none at all -- in which case every field silently falls back to its
default and the misconfiguration only surfaces much later, far from the cause.
"""

from pathlib import Path

import pytest

from career_intel.config import API_ROOT, Settings


def test_env_file_is_anchored_to_the_api_directory() -> None:
    configured = Path(str(Settings.model_config["env_file"]))

    assert configured.is_absolute()
    assert configured == API_ROOT / ".env"


def test_ignores_a_dotenv_in_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stray .env next to the process must not reconfigure the application."""
    (tmp_path / ".env").write_text("LLM_MODEL=decoy-model-from-cwd\n")
    monkeypatch.chdir(tmp_path)

    assert Settings().llm_model != "decoy-model-from-cwd"
