"""The deployment config must forward every setting the application reads.

`MAX_UPLOAD_BYTES` was silently dropped here once already: it lived in
`.env.example`, was read by `Settings`, and was never listed in the api
service's `environment:` block, so under compose the pydantic default won and
the env file appeared to do nothing. Nothing in the unit suite could catch that
-- the code was correct, the deployment was not. This test closes that gap by
asserting the two agree.
"""

from pathlib import Path

import yaml

from career_intel.config import Settings

COMPOSE = Path(__file__).resolve().parents[3] / "docker-compose.yml"


def _api_environment() -> dict[str, str]:
    compose = yaml.safe_load(COMPOSE.read_text())
    return compose["services"]["api"]["environment"]


def test_every_setting_is_forwarded_to_the_api_service() -> None:
    forwarded = _api_environment()

    missing = [
        name.upper() for name in Settings.model_fields if name.upper() not in forwarded
    ]

    assert not missing, (
        f"settings not forwarded to the api service in docker-compose.yml: {missing}."
        " A Settings field absent from the compose environment silently falls back"
        " to its default in every container, whatever .env says."
    )


def test_healthcheck_follows_the_configured_credentials() -> None:
    """A healthcheck pinned to literal credentials outlives the ones in use.

    `api` waits on `condition: service_healthy`, so a check probing a role the
    POSTGRES_* overrides renamed does not merely report wrongly -- it stops the
    API from ever starting.
    """
    compose = yaml.safe_load(COMPOSE.read_text())
    command = " ".join(compose["services"]["db"]["healthcheck"]["test"])

    assert "${POSTGRES_USER" in command
    assert "${POSTGRES_DB" in command
