from __future__ import annotations

import os
import json
import time
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.config import MODEL_NAME, ROOT_DIR
from src.schemas import AgentAudit
from src.trace_logger import TraceLogger


class AgentLLM:
    def __init__(self, logger: TraceLogger, enabled: bool):
        self.logger = logger
        self.enabled = enabled
        self.client: OpenAI | None = None
        if enabled:
            load_dotenv(ROOT_DIR / ".env")
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is missing from .env or the environment")
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def audit(
        self,
        *,
        agent_name: str,
        case_id: str,
        system_prompt: str,
        finding: Any,
        source_context: Any,
    ) -> AgentAudit | None:
        if not self.enabled:
            self.logger.event(
                "llm_call_skipped",
                actor=agent_name,
                case_id=case_id,
                details={"reason": "llm mode does not enable this agent"},
            )
            return None

        assert self.client is not None
        def jsonable(value: Any) -> Any:
            if hasattr(value, "model_dump"):
                return value.model_dump(mode="json")
            if isinstance(value, dict):
                return {str(key): jsonable(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [jsonable(item) for item in value]
            return value

        payload = json.dumps(
            {
                "source_context": jsonable(source_context),
                "deterministic_finding": jsonable(finding),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        started = time.perf_counter()
        self.logger.event(
            "llm_call_started",
            actor=agent_name,
            case_id=case_id,
            target="openai",
            details={"requested_model": MODEL_NAME, "payload_characters": len(payload)},
        )
        try:
            completion = self.client.chat.completions.parse(
                model=MODEL_NAME,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "Review the source context and deterministic finding within your "
                            "assigned domain. The deterministic verifier is authoritative; do "
                            "not rewrite the finding and do not add facts. Return the structured "
                            "handoff acknowledgement with handoff_ready=true and "
                            "schema_version='agent_audit_v1'. "
                            f"The exact case ID is {case_id}.\n\n{payload}"
                        ),
                    },
                ],
                response_format=AgentAudit,
            )
            message = completion.choices[0].message
            if message.refusal:
                raise RuntimeError(f"Model refused agent audit: {message.refusal}")
            audit = message.parsed
            if audit is None:
                raise RuntimeError("OpenAI returned no parsed structured output")
            if audit.case_id != case_id or audit.agent != agent_name:
                raise ValueError("Agent audit identity does not match the requested handoff")
            usage = completion.usage
            self.logger.event(
                "llm_call_completed",
                actor=agent_name,
                case_id=case_id,
                target="coordinator",
                details={
                    "requested_model": MODEL_NAME,
                    "response_model": completion.model,
                    "response_id": completion.id,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                    "audit": audit,
                },
            )
            return audit
        except Exception as exc:
            self.logger.event(
                "llm_call_failed",
                actor=agent_name,
                case_id=case_id,
                target="coordinator",
                details={
                    "requested_model": MODEL_NAME,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise
