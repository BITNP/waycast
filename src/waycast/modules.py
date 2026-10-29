"""Built-in input and output modules for Waycast.

These are the concrete, pluggable modules that register with the Agent:
- input modules turn external signals into UnifiedInput;
- output modules declare a schema and accept units, returning OutputResult.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from waycast.protocols import InputModule, OutputModule, UnifiedInput
from waycast.state import OutputResult


# -- demo-side stores ----------------------------------------------------

_blob_store: dict[str, str] = {}
_notifications: list[str] = []
_seen_urls: list[str] = []
_echo_log: list[dict[str, Any]] = []


# -- Output module schemas ----------------------------------------------


class NotificationSchema(BaseModel):
    """A notification to be delivered through the notify output module."""

    message: str = Field(description="The notification text")
    level: str = Field(default="info", description="info | warning | error")


class MemoryLogSchema(BaseModel):
    """A structured log entry the memory-log output module accepts."""

    text: str = Field(description="Human-readable log line")
    tags: list[str] = Field(default_factory=list, description="Optional tags")


# -- Output modules -----------------------------------------------------


class NotifyOutputModule(OutputModule):
    """Deliver a notification and return its immediate result."""

    @property
    def name(self) -> str:
        return "notify"

    @property
    def output_schema(self) -> type[NotificationSchema]:
        return NotificationSchema

    def accept(self, payload: dict[str, Any]) -> OutputResult:
        data = NotificationSchema.model_validate(payload)
        _notifications.append(data.model_dump())
        return OutputResult(module=self.name, status="ok", detail=f"notification {data.level}: {data.message!r}")

    def describe(self) -> str:
        return "Deliver a notification to the human (message + level)."


class MemoryLogOutputModule(OutputModule):
    """Append a structured log entry to demo memory."""

    @property
    def name(self) -> str:
        return "memory_log"

    @property
    def output_schema(self) -> type[MemoryLogSchema]:
        return MemoryLogSchema

    def accept(self, payload: dict[str, Any]) -> OutputResult:
        data = MemoryLogSchema.model_validate(payload)
        _echo_log.append(data.model_dump())
        return OutputResult(module=self.name, status="ok", detail=f"logged: {data.text!r}")

    def describe(self) -> str:
        return "Append a structured log entry to the demo memory log."


def default_output_modules() -> list[OutputModule]:
    return [NotifyOutputModule(), MemoryLogOutputModule()]


# -- Input modules ------------------------------------------------------


class HttpInputModule(InputModule):
    """Turns an HTTP POST body into a UnifiedInput (source: http)."""

    @property
    def name(self) -> str:
        return "http"

    def emit(self, **kwargs: Any) -> UnifiedInput:
        content = str(kwargs.get("content", ""))
        metadata = dict(kwargs.get("metadata", {}) or {})
        return UnifiedInput(content=content, source="http", metadata=metadata)


def default_input_modules() -> list[InputModule]:
    return [HttpInputModule()]


__all__ = [
    "NotificationSchema",
    "MemoryLogSchema",
    "NotifyOutputModule",
    "MemoryLogOutputModule",
    "HttpInputModule",
    "default_output_modules",
    "default_input_modules",
    "_blob_store",
    "_notifications",
    "_seen_urls",
]
