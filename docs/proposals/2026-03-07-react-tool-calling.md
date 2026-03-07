# Proposal: Replace Plan-then-Execute with a ReAct Tool-Calling Loop

> Status: Superseded
> Created: 2026-03-07
> Decision: Approved — replace Plan-then-Execute + replan with ReAct tool-calling loop
> Scope: `execution/` subsystem only — discovery, git workflow, experience, and observability are unaffected
> Next Step: Implemented — see PR #12 and docs/archive/2026-03-07-react-tool-calling.md
> Related: [../design/execution.md](../design/execution.md), [../design/architecture.md](../design/architecture.md)

## Summary

The current Plan-then-Execute model requires the LLM to commit to a complete action sequence before seeing any file content, then relies on a bounded replan loop to recover from the inevitable planning errors. This proposal replaces that model with a ReAct (Reason + Act) tool-calling loop: the LLM calls one tool at a time, observes the real result, and decides the next step. The loop collapses the planner, executor, and replan logic into a single, simpler control flow. Reviewability and safety are preserved — all tool calls are intercepted, safety-checked, and logged before execution.

## Problem

The fundamental problem with Plan-then-Execute is **planning blindness**: the LLM generates a complete action sequence knowing only the task title and description, with no ability to read the actual files it will modify. Two consequences follow:

**1. Plans are guesses.**
The LLM cannot know what is actually in a file before planning how to change it. Plans frequently target the wrong line range, misquote existing content, or contradict the current state of the codebase. The replan mechanism exists precisely to compensate for this — it is a symptom, not a feature.

**2. The architecture is more complex than it needs to be.**
Working around planning blindness requires: a separate planner module, a separate executor module, a bounded replan loop with round tracking, and replan-specific prompts. This machinery exists to manage the gap between the LLM's upfront commitment and reality. A model that can read before it writes does not need any of it.

The replan loop itself has a secondary problem: each replan discards the LLM's in-context awareness of what it already tried and replaces it with a formatted summary. Information is lost. A continuous loop retains full context across every step.

## Proposal

Replace the `planner.py` + `executor.py` + replan loop with a single **tool-calling execution loop**.

### How it works

```
loop:
  LLM reasons about current state → emits a tool call
  Safety check: is this tool call allowed?
    No  → return error to LLM, continue
    Yes → execute tool, return real output to LLM
  LLM sees actual result → decides next tool call
  ...
  LLM calls done(commit_message, pr_title, pr_body)
  → execution complete
```

The LLM drives the entire execution. It reads what it needs, edits what it finds, runs checks, and signals when it is done. No upfront plan is required.

### Tool set

| Tool | Arguments | Purpose |
|------|-----------|---------|
| `read_file` | `path` | Read file content |
| `list_directory` | `path` | List files in a directory |
| `search_files` | `pattern`, `path` | Grep across files |
| `edit_file` | `path`, `content` | Overwrite a file |
| `create_file` | `path`, `content` | Create a new file |
| `delete_file` | `path` | Delete a file |
| `run_command` | `command` | Execute a shell command |
| `done` | `commit_message`, `pr_title`, `pr_body` | Signal task completion |

### Safety model

Safety checks apply **per tool call**, before execution — the same `SafetyPolicy` and `constitution.check_action_allowed` that currently run on plan steps. The difference is that checks happen incrementally rather than on a pre-committed batch. A blocked call returns an error message to the LLM so it can reason about an alternative approach.

### Observability

Every tool call and its result are logged to `llm_audit.jsonl`. The execution trace is equivalent to the current execution log but richer: it includes every read and search, not just writes. The observer emits the same per-step events as today. No observability regression.

### What is removed

- `execution/planner.py` — replaced by the tool loop
- `execution/executor.py` — replaced by individual tool handlers
- Replan logic in `agent.py` — the loop handles failures natively
- Replan-specific prompts (`plan_task.txt`, replan variant)

### What is unchanged

- `execution/safety.py` — applied per tool call
- `execution/verifier.py` — runs after `done` is called
- `execution/git_ops.py` — runs after successful verification
- `discovery/` — entirely unaffected
- `storage/experience.py` — learning extraction runs the same way
- `observability/` — same event interface

### Execution bounds

To prevent runaway loops, the tool-calling loop is bounded by:
- `max_steps` (e.g. 30 tool calls per task) — configurable via `Directive`
- Existing `max_tokens_per_task` budget — unchanged

## Expected Value

**Better plan quality.** The LLM can read a file before deciding how to edit it. Plans are grounded in reality from the first step, not reconstructed from guesses.

**Simpler codebase.** Three modules and their associated prompts collapse into one loop. The replan concept disappears because there is no static plan to replan.

**Better error recovery.** A failed tool call is just another observation. The LLM can read the error, understand why it failed, and try a different approach — all within the same context window, without losing the history of what it has tried.

**Natural read-before-write patterns.** `search_files` → `read_file` → `edit_file` is idiomatic. Today this requires encoding reading as a `run_command` step that the LLM must remember to include in its upfront plan.

## Risks and Open Questions

**Token cost.** More LLM calls per task. A task that previously required one planning call + deterministic execution may now require 5–15 LLM calls. The actual cost delta depends on average task complexity and needs to be measured.

**Loop termination.** The LLM must call `done` to end the loop. If it loops, stalls, or enters a repetitive pattern, the `max_steps` bound is the only safety net. Monitoring for loop pathologies is needed.

**No pre-execution plan artifact.** Today a human can read the full plan before any file is touched. With ReAct, the first action may already be a file write. For tasks requiring human pre-approval, a separate confirmation step would be needed (out of scope for this proposal).

**Prompt design.** The system prompt must clearly define all tools, their constraints, and the expected call-and-response format. Tool-calling quality is highly sensitive to prompt quality. This needs careful iteration.

**Open questions:**
- What is the realistic token cost per task vs. current approach?
- Should `max_steps` be per-task in `Directive`, or per-action-type?
- Do we need a `replace_in_file(path, old, new)` tool to avoid full-file rewrites for small edits?

## Exit Criteria

This proposal is ready to become a plan when:
- [ ] Token cost estimate is available (even rough: count average LLM calls × avg tokens per call)
- [ ] The tool set above is agreed on (additions, removals, or renames)
- [ ] The `max_steps` bound and loop-termination strategy are agreed on
- [ ] Decision is made on whether to run as a parallel executor option or a full replacement
