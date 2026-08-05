from __future__ import annotations

import json
import platform
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import openai
import pydantic

from src.config import (
    LOGGING_DIR,
    MODEL_NAME,
    MODEL_PARAMETER_SIZE,
    POLICY_VERSION,
)


class TraceLogger:
    """Thread-safe JSONL trace writer that resets automatically for every run."""

    def __init__(self, log_dir: Path = LOGGING_DIR, llm_mode: str = "all"):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = log_dir / "trace.jsonl"
        self.metadata_path = log_dir / "metadata.json"
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        self.llm_mode = llm_mode
        self._lock = threading.Lock()
        self._sequence = 0
        self.trace_path.write_text("", encoding="utf-8")
        self.metadata: dict[str, Any] = {
            "run_id": self.run_id,
            "provider": "OpenAI",
            "model": MODEL_NAME,
            "parameter_size": MODEL_PARAMETER_SIZE,
            "parameter_limit_note": (
                "OpenAI does not publish the parameter count for gpt-4o-mini. "
                "The instructor approved this model for this lab."
            ),
            "model_approval": "approved by instructor for this lab",
            "framework": "Custom Python typed multi-agent orchestrator",
            "sdk": f"openai-python {openai.__version__}",
            "schema_library": f"pydantic {pydantic.__version__}",
            "runtime": f"Python {platform.python_version()} on {platform.system()}",
            "policy_version": POLICY_VERSION,
            "temperature": 0,
            "llm_mode": llm_mode,
            "started_at": self._timestamp(),
            "status": "running",
        }
        self._write_metadata()
        self.event("run_started", actor="coordinator", details={"llm_mode": llm_mode})

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe(value: Any) -> Any:
        """Convert trace payloads to JSON values without ever recording secrets."""
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if isinstance(value, dict):
            clean = {}
            for key, item in value.items():
                lowered = str(key).lower()
                if any(token in lowered for token in ("api_key", "authorization", "secret", "token")):
                    clean[key] = "[REDACTED]"
                else:
                    clean[key] = TraceLogger._safe(item)
            return clean
        if isinstance(value, (list, tuple)):
            return [TraceLogger._safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def event(
        self,
        event_type: str,
        *,
        actor: str,
        case_id: str | None = None,
        target: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._sequence += 1
            record = {
                "sequence": self._sequence,
                "run_id": self.run_id,
                "timestamp": self._timestamp(),
                "event_type": event_type,
                "case_id": case_id,
                "actor": actor,
                "target": target,
                "details": self._safe(details or {}),
            }
            with self.trace_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")

    def finish(self, *, processed: int, failed: int, issue_counts: dict[str, int]) -> None:
        status = "completed" if failed == 0 else "completed_with_errors"
        self.event(
            "run_completed",
            actor="coordinator",
            details={"processed": processed, "failed": failed, "issue_counts": issue_counts},
        )
        self.metadata.update(
            {
                "completed_at": self._timestamp(),
                "status": status,
                "processed_cases": processed,
                "failed_cases": failed,
                "issue_counts": issue_counts,
                "trace_events": self._sequence,
            }
        )
        self._write_metadata()

    def fail(self, error: BaseException, *, processed: int) -> None:
        self.event(
            "run_failed",
            actor="coordinator",
            details={"error_type": type(error).__name__, "message": str(error)},
        )
        self.metadata.update(
            {
                "completed_at": self._timestamp(),
                "status": "failed",
                "processed_cases": processed,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "trace_events": self._sequence,
            }
        )
        self._write_metadata()

    def _write_metadata(self) -> None:
        self.metadata_path.write_text(
            json.dumps(self.metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def install_exception_hook(logger: TraceLogger) -> None:
    old_hook = sys.excepthook

    def hook(exc_type, exc_value, traceback):
        logger.event(
            "uncaught_exception",
            actor="runtime",
            details={"error_type": exc_type.__name__, "message": str(exc_value)},
        )
        old_hook(exc_type, exc_value, traceback)

    sys.excepthook = hook
