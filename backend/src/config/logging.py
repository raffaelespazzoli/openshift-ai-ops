"""Structured JSON logging configuration.

Every log line is JSON to stdout with fields:
timestamp, level, component, request_id|incident_id, message.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import StrEnum

from pythonjsonlogger.json import JsonFormatter

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
incident_id_var: ContextVar[str | None] = ContextVar("incident_id", default=None)


class Component(StrEnum):
    API = "api"
    PIPELINE = "pipeline"
    AGENT = "agent"
    DB = "db"
    KNOWLEDGE = "knowledge"


class _ComponentFilter(logging.Filter):
    """Injects a component field into every LogRecord."""

    def __init__(self, component: str) -> None:
        super().__init__()
        self._component = component

    def filter(self, record: logging.LogRecord) -> bool:
        record.component = self._component  # type: ignore[attr-defined]
        return True


class StructuredFormatter(JsonFormatter):
    """Custom JSON formatter that injects context vars."""

    def add_fields(
        self, log_record: dict, record: logging.LogRecord, message_dict: dict
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        utc_dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        log_record["timestamp"] = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        log_record["level"] = record.levelname
        log_record.setdefault("component", self._derive_component(record))

        req_id = request_id_var.get()
        inc_id = incident_id_var.get()
        if req_id:
            log_record["request_id"] = req_id
        if inc_id:
            log_record["incident_id"] = inc_id

    _UVICORN_LOGGERS = frozenset({"uvicorn", "uvicorn.error", "uvicorn.access"})

    @staticmethod
    def _derive_component(record: logging.LogRecord) -> str:
        if hasattr(record, "component"):
            return record.component  # type: ignore[return-value]
        if record.name in StructuredFormatter._UVICORN_LOGGERS:
            return Component.API.value
        parts = record.name.split(".")
        if len(parts) >= 2 and parts[0] == "openshift_ai_ops":
            candidate = parts[1]
            if candidate in Component.__members__.values():
                return candidate
            return Component.API.value
        return Component.API.value


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging to stdout.

    Overrides Uvicorn's default loggers so that access and error logs
    are also emitted as structured JSON.
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = StructuredFormatter(
        fmt="%(timestamp)s %(level)s %(component)s %(message)s",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uvicorn_logger_name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True


def get_logger(component: Component | str | None = None, *, module: str | None = None) -> logging.Logger:
    """Get a logger bound to a specific component.

    Args:
        component: Explicit component name or enum value. If None, derived from *module*.
        module: Module name (typically __name__) used to derive the component when
                *component* is not provided. Falls back to the last segment of the
                module path.
    """
    if component is not None:
        comp_value = component.value if isinstance(component, Component) else component
    elif module:
        comp_value = module.rsplit(".", maxsplit=1)[-1]
    else:
        comp_value = "api"

    logger = logging.getLogger(f"openshift_ai_ops.{comp_value}")
    logger.addFilter(_ComponentFilter(comp_value))
    return logger
