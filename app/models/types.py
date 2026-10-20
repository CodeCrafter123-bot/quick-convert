"""Request, result and capability models (report section 5)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from app.models.errors import ErrorCode


class FileType(str, Enum):
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    PDF = "pdf"

    @property
    def extension(self) -> str:
        return ".jpg" if self is FileType.JPEG else f".{self.value}"

    @property
    def is_image(self) -> bool:
        return self is not FileType.PDF


@dataclass(frozen=True)
class FileInfo:
    path: Path
    file_type: FileType
    size_bytes: int
    width: int | None = None
    height: int | None = None
    page_count: int | None = None
    encrypted: bool = False


Color = tuple[int, int, int]


@dataclass(frozen=True)
class ConversionOptions:
    """Only fields listed in a capability's supported_options may be set."""

    quality: int | None = None  # 1-100, JPEG/WebP
    width: int | None = None
    height: int | None = None
    pdf_page: int | None = None  # 1-based
    dpi: int | None = None
    background_color: Color | None = None  # used when flattening alpha
    password: str | None = None
    keep_metadata: bool = False

    def set_fields(self) -> set[str]:
        return {
            name
            for name, value in self.__dict__.items()
            if value is not None and value is not False
        }


@dataclass(frozen=True)
class ConversionRequest:
    source_path: Path
    target_format: FileType
    destination_path: Path
    options: ConversionOptions = field(default_factory=ConversionOptions)
    overwrite: bool = False


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_final(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass(frozen=True)
class ConversionResult:
    job_id: str
    output_paths: list[Path]
    output_sizes: list[int]
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConversionJob:
    request: ConversionRequest
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: float = 0.0
    error_code: ErrorCode | None = None
    error_message: str | None = None
    result: ConversionResult | None = None


@dataclass(frozen=True)
class Capability:
    input_type: FileType
    output_type: FileType
    adapter: str
    available: bool
    supported_options: frozenset[str]
    unavailable_reason: str | None = None
