"""API contracts for the archived space-imagery gallery."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ImageryCaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_key: str
    title: str
    source: str
    upstream_url: str
    captured_at: datetime
    content_hash: str
    byte_size: int
    content_type: str
    metadata_json: dict[str, Any]


class ImagerySourceStatus(BaseModel):
    key: str
    title: str
    source: str
    description: str
    capture_count: int
    latest_captured_at: datetime | None
    latest_capture_id: uuid.UUID | None


class ImageryGallery(BaseModel):
    generated_at: datetime
    total: int
    items: list[ImageryCaptureRead]
