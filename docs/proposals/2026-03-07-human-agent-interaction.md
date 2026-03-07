# Proposal: Issue + Chat Interaction Model for Human-Agent Collaboration

> Status: Approved for Plan
> Created: 2026-03-07
> Decision: Approved — GitHub Issues as primary surface, internal DB as mirror; Shape A + B in first deliverable
> Scope: Human-agent interaction layer — affects Task state machine, dashboard, and agent cycle
> Next Step: Implementation plan at [../plans/2026-03-07-human-agent-interaction.md](../plans/2026-03-07-human-agent-interaction.md)
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
1. Agent hits a blocker → opens a GitHub Issue with structured context (what it tried, what failed, what it needs) and links the issue URL to the task
2. Task status → `needs_human`
3. Human reads the issue, comments with instructions or a resolution
4. Agent picks up the new comment on the next cycle, appends it to the execution context, and resumes
5. Agent closes the issue and posts a summary when the task completes

**Shape B — Human-initiated (new request):**
1. Human opens a GitHub Issue ("add dark mode to the dashboard")
2. Agent detects the open issue on the next cycle, creates a Task from it (`source=github_issue`), links the issue URL
3. Execution proceeds normally; agent comments progress updates on the issue
4. Agent closes the issue when the task completes or reaches a new blocker

**Shape C — Ambient directives:**
1. Human opens a GitHub Issue with a directive ("pause all lint tasks", "focus on performance this week")
2. Agent applies it as a temporary directive override and acknowledges via comment
3. Scoped ambient interaction without needing a dedicated chat page

### Where threads live

**GitHub Issues is the primary interaction surface.** Humans open issues, comment, and close them using GitHub's native UI — no custom chat page needed. The agent polls open issues each cycle, acts on them, and comments results back.

**Internal DB is a mirror, not the source of truth.** A `threads` + `messages` table in SQLite syncs GitHub Issue content each cycle. This gives the agent fast local reads without hitting the GitHub API repeatedly, provides a persistent record if the issue is later deleted, and enables dashboard display without an API call per render.

### Agent cycle change

Add a `_phase_sync_github_issues` step at the start of each cycle (before discovery):
- Fetch all open GitHub Issues and new comments since last sync
- Mirror fetched content into the local `threads` + `messages` tables
- For issues linked to a `needs_human` task with new comments → re-queue as `human_resolved`, append thread to execution context
- For unlinked open issues → create a Task (`source=github_issue`), link the issue
- Post any pending agent comments back to GitHub

## Expected Value

- Unblocks the agent faster: human gives specific instructions instead of blind "resolve"
- Enables human-initiated tasks with the same lifecycle guarantees as discovered tasks
- Creates a legible audit trail of every human-agent decision
- Makes the dashboard a collaboration surface, not just a monitor
- Lays the foundation for richer async workflows (approval gates, priority overrides, multi-turn planning)

## Risks and Open Questions

- **Polling latency**: agent reads GitHub only at cycle start; replies may take up to `poll_interval_seconds` (default 120s) to be seen. Acceptable for async work; mitigable with a shorter interval if needed.
- **Mid-execution comments**: if the human comments while the agent is executing, the comment isn't visible until the next cycle. Intentional — the agent is not a real-time system.
- **GitHub token scope**: agent needs `issues: write` permission. Must be added to the credential setup docs.
- **Issue noise**: all open issues are scanned each cycle. Needs a label or convention to distinguish agent-managed issues from other project issues (e.g. a `sprout` label).
- **No dedicated chat page needed** for the initial scope — GitHub Issues is the UI for all three shapes.

## Exit Criteria

This proposal is ready to become a plan when:
- [ ] GitHub Issues as primary surface (internal DB as mirror) is confirmed
- [ ] The `threads` + `messages` schema is agreed on
- [ ] The first deliverable slice is defined (Shape A only, or A + B together)
- [ ] The `sprout` label convention (or equivalent) for issue filtering is decided
- [ ] The agent cycle integration point is agreed on (`_phase_sync_github_issues` before discovery)
