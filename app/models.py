from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetails(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetails


class HoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resourceId: int = Field(strict=True, gt=0)
    clientId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    ttlSeconds: int = Field(strict=True, ge=1, le=60)


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resourceId: int = Field(strict=True, gt=0)
    clientId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    holdId: UUID


class HoldResponse(BaseModel):
    resourceId: int
    holdId: UUID
    expiresInSeconds: int


class BookingResponse(BaseModel):
    bookingId: UUID
    resourceId: int
    status: str


class ResourceResponse(BaseModel):
    resourceId: int
    name: str
    booked: bool
