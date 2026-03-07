from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol, Tuple

from llm247_v2.core.models import ModelType, RegisteredModel, ToolCall

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

    def generate_tracked(self, prompt: str) -> Tuple[str, UsageInfo]: ...

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> Tuple[str | None, list[ToolCall], UsageInfo]:
        """Send a multi-turn tool-calling request.

        Returns (text_content, tool_calls, usage).
        Exactly one of text_content or tool_calls will be non-empty.
        """
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
        tracker: TokenTracker | None = None,
    ) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self.tracker = tracker or TokenTracker()
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
            usage_info = self._extract_usage(response.usage)
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

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> Tuple[str | None, list[ToolCall], UsageInfo]:
        t0 = time.monotonic()
        prompt_preview = str(messages)[:500]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.7,
            )
            msg = response.choices[0].message
            usage_info = self._extract_usage(response.usage)
            self.tracker.record(usage_info)

            tool_calls: list[ToolCall] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, ValueError):
                        arguments = {"_raw": tc.function.arguments}
                    tool_calls.append(ToolCall(
                        tool=tc.function.name,
                        arguments=arguments,
                    ))

            text_content = msg.content or None

            if self._audit:
                elapsed = int((time.monotonic() - t0) * 1000)
                response_preview = str(tool_calls) if tool_calls else (text_content or "")
                self._audit.record(
                    prompt_preview, response_preview[:500], usage_info, elapsed, model=self._model
                )

            logger.info(
                "llm_tool_call model=%s tools=%d input=%d output=%d total=%d",
                self._model, len(tool_calls),
                usage_info.prompt_tokens, usage_info.completion_tokens, usage_info.total_tokens,
            )
            return text_content, tool_calls, usage_info
        except Exception as exc:
            if self._audit:
                elapsed = int((time.monotonic() - t0) * 1000)
                self._audit.record(prompt_preview, "", UsageInfo(), elapsed, model=self._model, error=str(exc)[:300])
            if _is_budget_error(exc):
                raise BudgetExhaustedError(str(exc)) from exc
            raise

    def _extract_usage(self, raw_usage) -> UsageInfo:
        if not raw_usage:
            return UsageInfo()
        usage = UsageInfo(
            prompt_tokens=raw_usage.prompt_tokens or 0,
            completion_tokens=raw_usage.completion_tokens or 0,
            total_tokens=raw_usage.total_tokens or 0,
        )
        logger.info(
            "llm_call model=%s input=%d output=%d total=%d",
            self._model, usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
        )
        return usage


class BudgetExhaustedError(Exception):
    """Raised when API budget/quota is exhausted."""


def probe_registered_model_connection(
    model: RegisteredModel,
    *,
    timeout_seconds: float = 5.0,
) -> tuple[bool, str]:
    """Probe one registered model endpoint and return connectivity status."""
    endpoint = model.api_path if model.model_type == ModelType.EMBEDDING.value else _join_openai_path(model.base_url, "chat/completions")
    payload = _build_probe_payload(model)
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {model.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", 200)
            if 200 <= status_code < 300:
                return True, "Connection OK"
            return False, f"HTTP {status_code}"
    except urllib.error.HTTPError as exc:
        detail = _read_error_body(exc)
        return False, f"HTTP {exc.code}: {detail}" if detail else f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}"
    except Exception as exc:
        return False, f"Probe failed: {exc}"


class RoutedLLMClient:
    """Resolve per-point model bindings while preserving one default client."""

    def __init__(
        self,
        default_client: LLMClient,
        binding_resolver: Callable[[str], RegisteredModel | None],
        client_factory: Callable[[RegisteredModel], LLMClient],
    ) -> None:
        self._default_client = default_client
        self._binding_resolver = binding_resolver
        self._client_factory = client_factory
        self._clients: dict[str, LLMClient] = {}
        self.tracker = getattr(default_client, "tracker", None)

    def generate(self, prompt: str) -> str:
        return self._default_client.generate(prompt)

    def generate_tracked(self, prompt: str) -> Tuple[str, UsageInfo]:
        return self._default_client.generate_tracked(prompt)

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> Tuple[str | None, list[ToolCall], UsageInfo]:
        return self._default_client.generate_with_tools(messages, tools)

    def for_point(self, binding_point: str) -> LLMClient:
        """Return the client bound to one runtime point, or the default client."""
        model = self._binding_resolver(binding_point)
        if model is None:
            return self._default_client
        client = self._clients.get(model.id)
        if client is None:
            client = self._client_factory(model)
            self._clients[model.id] = client
        return client


def client_for_point(client: LLMClient, binding_point: str) -> LLMClient:
    """Resolve one binding point when the caller may have a router or a plain client."""
    selector = getattr(client, "for_point", None)
    if callable(selector):
        return selector(binding_point)
    return client


def _is_budget_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(kw in text for kw in ("quota", "budget", "rate_limit", "insufficient", "429"))


def _join_openai_path(base_url: str, suffix: str) -> str:
    """Join one OpenAI-compatible base URL with a relative endpoint path."""
    return f"{str(base_url).rstrip('/')}/{suffix.lstrip('/')}"


def _build_probe_payload(model: RegisteredModel) -> dict:
    """Build the smallest safe API payload for one model family."""
    if model.model_type == ModelType.EMBEDDING.value:
        endpoint = model.api_path or ""
        if "multimodal" in endpoint:
            return {
                "model": model.model_name,
                "input": [{"type": "text", "text": "connection-check"}],
            }
        return {
            "model": model.model_name,
            "input": "connection-check",
        }
    return {
        "model": model.model_name,
        "messages": [{"role": "user", "content": "connection-check"}],
        "temperature": 0,
        "max_tokens": 1,
    }


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    """Extract one short error preview from a failed HTTP response."""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    if not body:
        return ""
    return body[:160]


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
