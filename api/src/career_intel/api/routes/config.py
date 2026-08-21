"""Server-owned configuration the browser needs.

Exists so the client never has to hardcode a value the server owns. The upload
limit was previously duplicated as the literal "max 5 MB" in the empty state,
which then stayed put while MAX_UPLOAD_BYTES changed underneath it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from career_intel.api.schemas import ClientConfig
from career_intel.config import Settings, get_settings

router = APIRouter(prefix="/config", tags=["config"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("", response_model=ClientConfig)
async def get_client_config(settings: SettingsDep) -> ClientConfig:
    return ClientConfig(max_upload_bytes=settings.max_upload_bytes)
