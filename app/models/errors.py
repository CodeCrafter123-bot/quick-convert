"""Stable error codes shared by services, adapters and the UI."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    UNSUPPORTED_PAIR = "UNSUPPORTED_PAIR"
    INVALID_INPUT = "INVALID_INPUT"
    PASSWORD_REQUIRED = "PASSWORD_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    CONVERSION_FAILED = "CONVERSION_FAILED"
    CANCELLED = "CANCELLED"


class QuickConvertError(Exception):
    """An expected failure with a short, user-facing message."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"QuickConvertError({self.code.value}, {self.message!r})"


class Cancelled(QuickConvertError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.CANCELLED, "The job was cancelled.")
