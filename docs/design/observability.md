# Observability Module Design

> Module: `src/llm247_v2/observability/observer.py`
> Last updated: 2026-03-05

## Purpose

The Observer module is the single point through which all agent actions become visible to humans. Every significant decision, state change, and error the agent makes is emitted as a structured event — logged to multiple sinks simultaneously so humans can inspect the agent's behavior at any granularity without modifying agent code.

## Architecture

```
  Agent code
      │
      ▼
  Observer.emit(AgentEvent)
      │
      ├──→ HumanLogHandler   → .llm247_v2/activity.log     (tail -f friendly)
      ├──→ JsonLogHandler     → .llm247_v2/activity.jsonl   (jq-queryable)
      ├──→ StoreHandler       → tasks.db / task_events      (per-task audit)
      └──→ ConsoleHandler     → stderr                       (colored terminal)
```

Additionally, the LLMAuditLogger captures every LLM call independently:

```
  ArkLLMClient.generate_tracked()
      │
      └──→ LLMAuditLogger    → .llm247_v2/llm_audit.jsonl  (full prompts + responses)
```

## Design Principles

**Single emission point.** All agent code calls `self.obs.emit()` or typed helpers (`obs.task_queued()`, `obs.plan_created()`, etc.). No handler is called directly. This ensures every event goes to all sinks.

**Typed event helpers.** Raw `emit(AgentEvent(...))` is the low-level API. Typed helpers (e.g., `obs.experience_injected(task_id, count, summaries)`) enforce consistent field usage across callers and make the call sites readable.

**NullObserver for tests.** `NullObserver` implements the full Observer interface with no-ops. Tests instantiate it by default so they don't need to mock or suppress output.

**LLM audit is separate.** The Observer handles agent-level events (what the agent decided). The LLMAuditLogger handles LLM-level events (what was sent to and received from the model). These are different audiences: Observer events are for operational monitoring; LLM audit is for debugging model behavior and cost analysis.

## Human Review Protocol

| What to check | How |
|----------------|-----|
| Is the agent alive? | `tail -f .llm247_v2/activity.log` |
| What is it doing now? | Console output (stderr) or Dashboard |
| What tasks did it find? | Dashboard → Tasks tab |
| Why did it pick task X? | `cat .llm247_v2/activity.jsonl \| jq 'select(.phase=="value")'` |
| What did it ask the LLM? | `cat .llm247_v2/llm_audit.jsonl \| jq '{seq, prompt_preview, response_preview}'` |
| Full plan for task X? | Dashboard → click task → Execution Plan |
| Full LLM conversation? | `cat .llm247_v2/llm_audit.jsonl \| jq 'select(.seq==N) \| .prompt_full'` |
| What did it learn? | Dashboard → click task → What Was Learned |
| Cost breakdown? | Dashboard → stats cards (total tokens) + per-task tokens/time |
