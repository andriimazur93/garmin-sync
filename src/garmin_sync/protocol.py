"""Version-one wire models and deliberate protocol failures."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool

TrackId = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class WireModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SessionRequest(WireModel):
    session_id: UUID
    device_epoch: UUID
    server_id: UUID
    protocol_version: int


class DesiredRequest(WireModel):
    present: StrictBool


class AssociationRequest(WireModel):
    server_id: UUID
    device_epoch: UUID


class OperationResult(WireModel):
    status: Literal['success', 'failed']
    error: str | None = Field(default=None, max_length=256)


class FinishRequest(WireModel):
    outcome: Literal['success', 'cancelled', 'failed']


class InventoryEntry(WireModel):
    track_id: TrackId | None
    cache_id: str = Field(min_length=1, max_length=256)
    filename: str | None = Field(default=None, max_length=255)


class InventoryPage(WireModel):
    entries: list[InventoryEntry] = Field(max_length=20)


class InventoryCommit(WireModel):
    phase: Literal['before', 'after']
    expected_pages: int = Field(ge=0, le=4096)
    expected_entries: int = Field(ge=0, le=81920)


class ProtocolError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code


def install_errors(app):
    from fastapi.responses import JSONResponse

    @app.exception_handler(ProtocolError)
    async def protocol_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=exc.status_code)
