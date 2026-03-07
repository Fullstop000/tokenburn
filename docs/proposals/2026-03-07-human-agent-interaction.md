# Proposal: Issue + Chat Interaction Model for Human-Agent Collaboration

> Status: Draft
> Created: 2026-03-07
> Decision: Should we replace the single-field `human_help_request` handoff with a structured issue + threaded chat model?
> Scope: Human-agent interaction layer — affects Task state machine, dashboard, and agent cycle
> Next Step: Decide whether this is worth a plan; if yes, define the first deliverable slice
> Related: [../design/execution.md](../design/execution.md), [../design/observability.md](../design/observability.md), [../design/dashboard.md](../design/dashboard.md)

## Summary

The current human-agent handoff is a one-way, one-shot notification: the agent sets `human_help_request` on a blocked task and waits for a status flip to `human_resolved`. There is no back-and-forth, no way for humans to issue instructions mid-execution, and no way for humans to proactively request work. This proposal replaces that model with a GitHub Issue-like structure — a persistent, threaded, bidirectional channel between agent and human — combined with a lightweight chat interface for low-friction interaction.

## Problem

**1. The handoff is a dead end.**
When the agent is blocked, it leaves a text blob in `human_help_request` and halts. The human can only "resolve" the task without giving the agent any new information. If the resolution requires the agent to try a different approach, the human has no channel to say so.

**2. Humans cannot initiate work.**
All tasks currently originate from the agent's discovery cycle. There is no first-class way for a human to say "do this thing" and have it enter the same task lifecycle with priority, tracking, and audit trail. Ad-hoc task injection through the store is a workaround, not a feature.

**3. No persistent context across turns.**
Even if a human resolves a task and the agent retries, the conversation is lost. The next execution has no memory of what the human said or why the previous attempt failed. Learnings are extracted post-hoc, not fed back in real time.

**4. The dashboard is read-only.**
The dashboard shows task state but provides no mechanism for the human to influence it beyond crude status flips. It is an observer interface, not a collaboration interface.

## Proposal

Introduce a **Thread** model alongside Tasks. A thread is an ordered list of messages attached to a task (or standalone), where both the agent and human can post. Each message has a role (`agent` | `human`), a body, and a timestamp.

### Interaction shapes

**Shape A — Agent-initiated (blocked task):**
1. Agent hits a blocker → creates a thread on the task with structured context (what it tried, what failed, what it needs)
2. Task status → `needs_human`
3. Human reads thread, posts a reply with instructions or clarification
4. Agent picks up the reply on the next cycle, continues execution with the new context appended to its prompt
5. Thread stays attached to the task as permanent audit trail

**Shape B — Human-initiated (new request):**
1. Human posts a message in a standalone thread ("add dark mode to the dashboard")
2. Agent reads it on the next cycle, creates a Task from it (source: `human_request`), links the thread
3. Execution proceeds normally; agent posts progress updates to the thread
4. Human can comment mid-execution if priorities change

**Shape C — Ambient chat:**
1. Human asks a question or shares an observation not tied to a specific task
2. Agent responds in the next cycle
3. Useful for: "what are you working on?", "skip the lint tasks for now", directive updates

### Where threads live

Option 1 — **Internal DB**: a new `threads` + `messages` table in the existing SQLite store. Self-contained, no external dependencies, dashboard renders it directly.

Option 2 — **GitHub Issues**: agent opens/comments on real GitHub issues. Human interaction happens natively in GitHub. Agent polls the API each cycle. Strong external tooling (notifications, search, references) but adds a hard dependency on GitHub and requires credentials.

Option 1 is the right default. Option 2 can be a later adapter once the internal model is stable.

### Agent cycle change

Add a `_phase_check_human_messages` step at the start of each cycle (before discovery):
- Read any unacknowledged human messages from the thread store
- For tasks with new human replies, re-queue them as `human_resolved` with the thread appended to `experience_context`
- For standalone threads (shape B/C), create tasks or post agent replies accordingly

## Expected Value

- Unblocks the agent faster: human gives specific instructions instead of blind "resolve"
- Enables human-initiated tasks with the same lifecycle guarantees as discovered tasks
- Creates a legible audit trail of every human-agent decision
- Makes the dashboard a collaboration surface, not just a monitor
- Lays the foundation for richer async workflows (approval gates, priority overrides, multi-turn planning)

## Risks and Open Questions

- **Polling latency**: agent only reads messages at cycle start; for time-sensitive replies this may feel slow. Mitigable with a shorter poll interval or a wake-up signal.
- **Message ordering and concurrency**: if the agent is mid-execution when a human posts, the message isn't seen until the next cycle. Need to decide whether mid-execution injection is ever desirable.
- **GitHub Issues adapter complexity**: the internal model should be designed so a GitHub adapter can be bolted on later without changing the core thread store interface.
- **Scope creep**: chat could grow into a full product. The first deliverable must be narrowly scoped — likely just Shape A (blocked task thread) with a minimal dashboard UI.

## Exit Criteria

This proposal is ready to become a plan when:
- [ ] The Thread + Message data model is agreed on (fields, state machine)
- [ ] The first deliverable slice is defined (likely: Shape A only — threaded blocked-task handoff)
- [ ] The dashboard interaction design is sketched (how human reads and replies)
- [ ] The agent cycle integration point is agreed on (when and how agent reads new messages)
