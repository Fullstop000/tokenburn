from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Tuple

logger = logging.getLogger("llm247_v2.llm")


@dataclass(frozen=True)
class UsageInfo:
    """Token usage for a single LLM call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMClient(Protocol):
    """Contract for text generation backends."""

    def generate(self, prompt: str) -> str: ...

    def generate_tracked(self, prompt: str) -> Tuple[str, UsageInfo]:
        """Generate text and return token usage. Default delegates to generate()."""
        ...


class TokenTracker:
    """Thread-safe accumulator for token costs across multiple LLM calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._call_count = 0

    def record(self, usage: UsageInfo) -> None:
        with self._lock:
            self._prompt_tokens += usage.prompt_tokens
            self._completion_tokens += usage.completion_tokens
            self._total_tokens += usage.total_tokens
            self._call_count += 1

    @property
    def total(self) -> int:
        return self._total_tokens

    @property
    def call_count(self) -> int:
        return self._call_count

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._total_tokens,
                "call_count": self._call_count,
            }

    def reset(self) -> dict:
        """Return current snapshot and reset counters to zero."""
        with self._lock:
            snap = {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._total_tokens,
                "call_count": self._call_count,
            }
            self._prompt_tokens = 0
            self._completion_tokens = 0
            self._total_tokens = 0
            self._call_count = 0
            return snap


class LLMAuditLogger:
    """Records every LLM call (prompt + response + usage + timing) to JSONL.

    Human reviewers can inspect this file to see exactly what the agent
    asked the LLM and what it received, enabling full decision traceability.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = open(path, "a", encoding="utf-8", buffering=1)
        self._call_seq = 0

    def record(
        self,
        prompt: str,
        response: str,
        usage: UsageInfo,
        duration_ms: int,
        model: str = "",
        error: str = "",
    ) -> None:
        with self._lock:
            self._call_seq += 1
            entry = {
                "seq": self._call_seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "prompt_len": len(prompt),
                "prompt_preview": prompt[:500],
                "prompt_full": prompt,
                "response_len": len(response),
                "response_preview": response[:500],
                "response_full": response,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "duration_ms": duration_ms,
            }
            if error:
                entry["error"] = error
            self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self._file.close()


class ArkLLMClient:
    """Adapter wrapping Ark/OpenAI-compatible endpoint with token tracking."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        audit_logger: LLMAuditLogger | None = None,
    ) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self.tracker = TokenTracker()
        self._audit = audit_logger

    def generate(self, prompt: str) -> str:
        text, _ = self.generate_tracked(prompt)
        return text

    def generate_tracked(self, prompt: str) -> Tuple[str, UsageInfo]:
        t0 = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            usage_info = UsageInfo()
            raw_usage = response.usage
            if raw_usage:
                usage_info = UsageInfo(
                    prompt_tokens=raw_usage.prompt_tokens or 0,
                    completion_tokens=raw_usage.completion_tokens or 0,
                    total_tokens=raw_usage.total_tokens or 0,
                )
                logger.info(
                    "llm_call model=%s input=%d output=%d total=%d",
                    self._model,
                    usage_info.prompt_tokens,
                    usage_info.completion_tokens,
                    usage_info.total_tokens,
                )
            self.tracker.record(usage_info)

            if self._audit:
                elapsed = int((time.monotonic() - t0) * 1000)
                self._audit.record(prompt, content, usage_info, elapsed, model=self._model)

            return content, usage_info
        except Exception as exc:
            if self._audit:
                elapsed = int((time.monotonic() - t0) * 1000)
                self._audit.record(prompt, "", UsageInfo(), elapsed, model=self._model, error=str(exc)[:300])
            if _is_budget_error(exc):
                raise BudgetExhaustedError(str(exc)) from exc
            raise


class BudgetExhaustedError(Exception):
    """Raised when API budget/quota is exhausted."""


def _is_budget_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(kw in text for kw in ("quota", "budget", "rate_limit", "insufficient", "429"))


def extract_json(text: str) -> dict | None:
    """Extract first JSON object from LLM output."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
