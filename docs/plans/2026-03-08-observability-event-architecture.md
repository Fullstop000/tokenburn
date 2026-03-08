# Plan: Observability Event Architecture

> Status: Pending
> Created: 2026-03-08
> Proposal: [docs/proposals/2026-03-08-observability-event-architecture.md](../proposals/2026-03-08-observability-event-architecture.md)

## Goal

Refactor Sprout observability into an explicit architecture with:

1. one standard event reporting interface through `Observer`
2. first-class module event catalogs
3. explicit event correlation rules
4. dashboard and API projections built on those contracts instead of ad hoc raw-event filtering

The target architecture uses stable business subsystems as the top-level event ownership boundary. Internal mechanisms such as `git`, `filesystem`, and `command` are not treated as modules. They are execution tool-call categories inside the `Execution` subsystem.

## Scope

**In scope:** `observability/`, dashboard event projections, event/entity correlation rules, design docs updated after implementation

**Out of scope:** redesigning unrelated runtime behavior, replacing all event persistence in one step, changing dashboard visual design beyond what new projections require

## Architecture After

### Top-Level Modules

- `Cycle`
- `Discovery`
- `Execution`
- `Memory`
- `Inbox`
- `LLM`
- `ControlPlane`

### Event Families Per Module

- `Cycle.lifecycle`
- `Cycle.budget`
- `Discovery.strategy`
- `Discovery.candidate`
- `Discovery.valuation`
- `Discovery.queue`
- `Discovery.funnel`
- `Execution.planning`
- `Execution.tool_call`
- `Execution.verification`
- `Execution.state`
- `Memory.recall`
- `Memory.learning`
- `Memory.persistence`
- `Inbox.thread`
- `Inbox.message`
- `Inbox.handoff`
- `LLM.routing`
- `LLM.audit_link`
- `ControlPlane.directive`
- `ControlPlane.runtime`

### Core Modeling Rule

Tool categories such as `git`, `filesystem`, and `command` are not event modules and not event families. They are classification fields on `Execution.tool_call` events:

- `tool_type`
- `tool_name`

This avoids promoting execution mechanics into false first-class observability domains.

## Standard Event Envelope

Every event emitted through `Observer` must use one shared envelope plus a module-specific `data` payload.

### Required Envelope Fields

| Field | Type | Meaning |
|------|------|---------|
| `event_id` | `str` | Unique id for this event row |
| `module` | `str` | Top-level subsystem that owns the event, such as `Execution` |
| `family` | `str` | Event family inside the owning module, such as `tool_call` |
| `event_name` | `str` | Specific event type, such as `tool_call_succeeded` |
| `timestamp` | `str` | RFC3339 / ISO timestamp for event creation |

### Shared Optional Envelope Fields

| Field | Type | Meaning |
|------|------|---------|
| `task_id` | `str` | Stable task identifier when the event belongs to a task |
| `cycle_id` | `int` | Stable cycle identifier when the event belongs to a cycle |
| `thread_id` | `str` | Stable inbox thread identifier when the event belongs to a human review thread |
| `llm_seq` | `int` | Sequence id of the related LLM audit entry when the event has model provenance |
| `success` | `bool` | Event outcome when pass/fail semantics apply |
| `detail` | `str` | Short human-readable event summary |
| `reasoning` | `str` | Human-readable explanation for why the event happened |
| `data` | `dict` | Module-specific structured payload decoded using the module and family registry |

### Envelope Rule

Top-level fields are reserved for:

- event identity
- module ownership
- cross-module correlation keys
- short human-readable summaries

Module-local payload must live in `data`. Fields such as `step_id` and `tool_call_id` do not belong at the top level unless they later become true cross-module correlation keys.

## Event Registry And Dispatch

Event parsing should be registry-driven rather than page-specific.

The registry key is:

- `(module, family, event_name)`

The registry value defines:

- event purpose
- allowed envelope fields
- `data` schema
- decoder
- downstream projection adapters

This gives the system one standard parse flow:

1. parse the envelope
2. identify the event definition from `(module, family, event_name)`
3. decode `data` using that event definition
4. route the typed result into correlation and projection code

## Family Data Schemas

The schemas below define the shared `data` payload shape for each event family. Event-specific additions are listed in the module catalogs.

### `Cycle.lifecycle.data`

| Field | Type | Meaning |
|------|------|---------|
| `started_at` | `str` | Explicit cycle start time when different from event timestamp |
| `completed_at` | `str` | Explicit cycle completion time when different from event timestamp |
| `abort_reason` | `str` | Structured reason for early termination |
| `poll_interval_seconds` | `int` | Poll interval active when the cycle ran |

### `Cycle.budget.data`

| Field | Type | Meaning |
|------|------|---------|
| `budget_kind` | `str` | Budget type being evaluated, such as `tokens`, `time`, or `spend` |
| `budget_limit` | `number` | Configured budget ceiling for the checked resource |
| `budget_used` | `number` | Amount already consumed at check time |
| `budget_remaining` | `number` | Remaining budget at check time |
| `exhausted_reason` | `str` | Explanation for why execution must stop |

### `Discovery.strategy.data`

| Field | Type | Meaning |
|------|------|---------|
| `strategy_name` | `str` | Selected discovery strategy identifier |
| `queue_depth` | `int` | Number of queued tasks at strategy selection time |
| `focus_areas` | `list[str]` | Directive focus areas that influenced strategy choice |
| `source_names` | `list[str]` | Discovery sources considered during strategy choice |
| `skipped_reason` | `str` | Reason a strategy was not used |

### `Discovery.candidate.data`

| Field | Type | Meaning |
|------|------|---------|
| `candidate_id` | `str` | Stable id for the raw candidate before or while it becomes a task |
| `source` | `str` | Discovery source that produced the candidate |
| `title` | `str` | Human-readable candidate title when available |
| `file_path` | `str` | Primary file associated with the candidate |
| `line` | `int` | Primary line number associated with the candidate |
| `severity` | `str` | Relative severity classification such as `low`, `medium`, or `high` |
| `duplicate_of_task_id` | `str` | Existing task id if this candidate was deduplicated |
| `rejection_reason` | `str` | Reason the candidate was rejected before valuation |

### `Discovery.valuation.data`

| Field | Type | Meaning |
|------|------|---------|
| `candidate_id` | `str` | Stable id of the candidate being valued |
| `score` | `number` | Final numeric score assigned to the candidate |
| `decision` | `str` | Valuation decision such as `queue`, `filter_out`, or `defer` |
| `heuristic_breakdown` | `dict[str, number]` | Per-dimension scoring contribution breakdown |
| `model_name` | `str` | Model used for valuation when LLM scoring applies |
| `deferred_reason` | `str` | Explanation for why a candidate was deferred |
| `filtered_reason` | `str` | Explanation for why a candidate was filtered out |

### `Discovery.queue.data`

| Field | Type | Meaning |
|------|------|---------|
| `candidate_id` | `str` | Candidate id that was considered for queue insertion |
| `queue_position` | `int` | Queue position assigned at insertion time |
| `source` | `str` | Discovery source for the queued task |
| `task_status` | `str` | Task status immediately after queue insertion |
| `skipped_reason` | `str` | Reason queue insertion was skipped |

### `Discovery.funnel.data`

| Field | Type | Meaning |
|------|------|---------|
| `raw_candidates` | `int` | Number of raw candidates discovered |
| `deduplicated` | `int` | Number of candidates removed as duplicates |
| `scored` | `int` | Number of candidates that reached valuation |
| `filtered_out` | `int` | Number of candidates excluded after valuation |
| `deferred` | `int` | Number of candidates intentionally deferred |
| `queued` | `int` | Number of candidates inserted into the queue |

### `Execution.planning.data`

| Field | Type | Meaning |
|------|------|---------|
| `plan_version` | `int` | Monotonic plan version for the task |
| `round` | `int` | Planning or replanning round number |
| `step_count` | `int` | Number of steps in the current plan version |
| `plan_summary` | `str` | Short summary of the plan contents |
| `revision_reason` | `str` | Reason this plan version differs from the previous one |

### `Execution.tool_call.data`

| Field | Type | Meaning |
|------|------|---------|
| `step_id` | `str` | Execution-local step identifier that groups tool calls under one step |
| `tool_call_id` | `str` | Unique identifier for one tool invocation inside the task |
| `tool_type` | `str` | Tool category such as `git`, `filesystem`, `command`, `control`, or `other` |
| `tool_name` | `str` | Specific tool name such as `read_file` or `git_create_worktree` |
| `input_summary` | `str` | Redacted summary of tool input arguments |
| `output_summary` | `str` | Redacted summary of tool output or effect |
| `duration_ms` | `int` | Tool runtime duration in milliseconds |
| `exit_code` | `int` | Process exit code when the tool wraps a command |
| `artifact_refs` | `list[dict]` | Structured references to produced artifacts such as files, branches, PRs, or worktrees |

### `Execution.verification.data`

| Field | Type | Meaning |
|------|------|---------|
| `verification_id` | `str` | Identifier for one verification run or batch |
| `check_name` | `str` | Name of the verification check that ran |
| `command` | `str` | Verification command when the check is command-driven |
| `exit_code` | `int` | Command exit code when verification executed a process |
| `duration_ms` | `int` | Verification runtime duration in milliseconds |
| `inconclusive_reason` | `str` | Explanation for a verification run that produced no clear result |

### `Execution.state.data`

| Field | Type | Meaning |
|------|------|---------|
| `from_status` | `str` | Previous execution state or task state |
| `to_status` | `str` | New execution state or task state |
| `blocked_reason` | `str` | Reason execution cannot currently proceed |
| `resumed_by` | `str` | Actor that resumed execution such as `human`, `system`, or `retry` |
| `completion_kind` | `str` | Final completion classification such as `success`, `failure`, or `aborted` |

### `Memory.recall.data`

| Field | Type | Meaning |
|------|------|---------|
| `query` | `str` | Recall query or search seed used for experience lookup |
| `match_count` | `int` | Number of experiences matched by the lookup |
| `recalled_experience_ids` | `list[str]` | Experience ids returned by the lookup |
| `injected_count` | `int` | Number of recalled experiences injected into downstream context |

### `Memory.learning.data`

| Field | Type | Meaning |
|------|------|---------|
| `extraction_kind` | `str` | Learning extraction mode such as `task`, `failure`, or `verification` |
| `learned_count` | `int` | Number of learnings produced by extraction |
| `stored_experience_ids` | `list[str]` | Experience ids written from this extraction |
| `failure_reason` | `str` | Reason learning extraction failed |

### `Memory.persistence.data`

| Field | Type | Meaning |
|------|------|---------|
| `experience_id` | `str` | Experience id written or updated by the event |
| `deduplicated_against` | `str` | Experience id that caused deduplication |
| `exploration_map_updated` | `bool` | Whether exploration state changed |
| `interest_profile_updated` | `bool` | Whether interest profile state changed |

### `Inbox.thread.data`

| Field | Type | Meaning |
|------|------|---------|
| `thread_title` | `str` | Human-readable title of the thread |
| `created_by` | `str` | Actor that created the thread, typically `agent` or `human` |
| `old_status` | `str` | Previous thread status before a status change |
| `new_status` | `str` | New thread status after a status change |

### `Inbox.message.data`

| Field | Type | Meaning |
|------|------|---------|
| `message_id` | `str` | Stable identifier for one thread message |
| `role` | `str` | Message role such as `agent` or `human` |
| `body_preview` | `str` | Short preview of the message content |
| `read_by` | `str` | Actor that consumed the message, such as `agent`, `human`, or `system` |

### `Inbox.handoff.data`

| Field | Type | Meaning |
|------|------|---------|
| `handoff_kind` | `str` | Handoff stage such as `help_request`, `response`, or `resolution` |
| `resolution_kind` | `str` | Resolution classification such as `resume`, `redirect`, or `close` |
| `applied_by` | `str` | Actor that applied the resolution |

### `LLM.routing.data`

| Field | Type | Meaning |
|------|------|---------|
| `binding_point` | `str` | Runtime binding point used for the model call |
| `model_id` | `str` | Registered model id selected for the call |
| `model_name` | `str` | Human-readable model name used for the call |
| `provider` | `str` | Provider or adapter label for the selected model |

### `LLM.audit_link.data`

| Field | Type | Meaning |
|------|------|---------|
| `linked_event_id` | `str` | Event id being linked to the audit row |
| `prompt_preview` | `str` | Safe preview of the related prompt |
| `response_preview` | `str` | Safe preview of the related response |

### `ControlPlane.directive.data`

| Field | Type | Meaning |
|------|------|---------|
| `changed_fields` | `list[str]` | Directive field names changed by the update |
| `paused` | `bool` | Pause state stored after the update |
| `focus_areas` | `list[str]` | Focus areas active after the update |
| `forbidden_paths` | `list[str]` | Forbidden paths active after the update |

### `ControlPlane.runtime.data`

| Field | Type | Meaning |
|------|------|---------|
| `action_source` | `str` | Origin of the runtime action such as `dashboard`, `api`, or `system` |
| `runtime_action` | `str` | Runtime control action such as `pause`, `resume`, `shutdown`, or `inject_task` |
| `injected_task_title` | `str` | Human-readable title of an injected task |
| `rejection_reason` | `str` | Explanation for why a runtime action was rejected |

## Module Catalogs

### Cycle

#### `Cycle.lifecycle`

Purpose: describe the lifecycle boundaries of one autonomous agent cycle.

##### `cycle_started`

- `purpose`: record that a new cycle began
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`
- `optional_fields`: `reasoning`, `data.started_at`, `data.poll_interval_seconds`
- `correlation_keys`: `cycle_id`
- `producer`: cycle orchestrator
- `consumers`: cycle dashboard view, audit trail

##### `cycle_completed`

- `purpose`: record that a cycle finished normally
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`, `success`
- `optional_fields`: `data.completed_at`
- `correlation_keys`: `cycle_id`
- `producer`: cycle orchestrator
- `consumers`: cycle dashboard view, audit trail

##### `cycle_aborted`

- `purpose`: record that a cycle terminated early
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`, `success`
- `optional_fields`: `reasoning`, `data.abort_reason`
- `correlation_keys`: `cycle_id`
- `producer`: cycle orchestrator
- `consumers`: cycle dashboard view, audit trail, debugging tools

#### `Cycle.budget`

Purpose: explain token or runtime budget decisions at cycle scope.

##### `budget_checked`

- `purpose`: record a cycle budget check
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`
- `optional_fields`: `data.budget_kind`, `data.budget_limit`, `data.budget_used`, `data.budget_remaining`
- `correlation_keys`: `cycle_id`
- `producer`: cycle orchestrator
- `consumers`: cycle dashboard view, debugging tools

##### `budget_exhausted`

- `purpose`: record that cycle progression stopped because budget was exhausted
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`, `success`
- `optional_fields`: `reasoning`, `data.budget_kind`, `data.budget_limit`, `data.budget_used`, `data.exhausted_reason`
- `correlation_keys`: `cycle_id`
- `producer`: cycle orchestrator
- `consumers`: cycle dashboard view, debugging tools

### Discovery

#### `Discovery.strategy`

Purpose: explain which discovery strategy ran and why.

##### `strategy_selected`

- `purpose`: record the strategy chosen for this discovery pass
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`
- `optional_fields`: `reasoning`, `llm_seq`, `data.strategy_name`, `data.queue_depth`, `data.focus_areas`, `data.source_names`
- `correlation_keys`: `cycle_id`, `llm_seq`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view, audit trail

##### `strategy_skipped`

- `purpose`: record that a strategy was considered but not used
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`
- `optional_fields`: `reasoning`, `data.strategy_name`, `data.skipped_reason`
- `correlation_keys`: `cycle_id`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view, debugging tools

#### `Discovery.candidate`

Purpose: describe raw candidate generation before value decisions.

##### `candidate_found`

- `purpose`: record one raw discovery candidate
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `task_id`, `detail`, `data.candidate_id`, `data.source`
- `optional_fields`: `llm_seq`, `data.title`, `data.file_path`, `data.line`, `data.severity`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`, `llm_seq`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view, correlation layer

##### `candidate_deduplicated`

- `purpose`: record that a duplicate candidate was detected
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `task_id`, `detail`, `data.candidate_id`
- `optional_fields`: `reasoning`, `data.duplicate_of_task_id`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view, debugging tools

##### `candidate_rejected`

- `purpose`: record that a raw candidate was rejected before scoring
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `task_id`, `detail`, `data.candidate_id`
- `optional_fields`: `reasoning`, `data.rejection_reason`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view

#### `Discovery.valuation`

Purpose: record candidate scoring and exclusion decisions.

##### `candidate_scored`

- `purpose`: record a score assigned to a candidate
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `task_id`, `detail`, `data.candidate_id`, `data.score`
- `optional_fields`: `reasoning`, `llm_seq`, `data.decision`, `data.heuristic_breakdown`, `data.model_name`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`, `llm_seq`
- `producer`: discovery/value subsystem
- `consumers`: discovery dashboard view, audit trail

##### `candidate_filtered_out`

- `purpose`: record that a candidate did not pass valuation
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `task_id`, `detail`, `data.candidate_id`
- `optional_fields`: `reasoning`, `data.filtered_reason`, `data.score`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`
- `producer`: discovery/value subsystem
- `consumers`: discovery dashboard view

##### `candidate_deferred`

- `purpose`: record that a candidate was intentionally deferred rather than queued or dropped
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `task_id`, `detail`, `data.candidate_id`
- `optional_fields`: `reasoning`, `data.deferred_reason`, `data.score`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`
- `producer`: discovery/value subsystem
- `consumers`: discovery dashboard view, task prioritization tooling

#### `Discovery.queue`

Purpose: record the handoff from discovery into persistent task state.

##### `candidate_queued`

- `purpose`: record that a candidate became a queued task
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `task_id`, `detail`
- `optional_fields`: `data.candidate_id`, `data.queue_position`, `data.source`, `data.task_status`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view, task/task-event correlation layer

##### `queue_skipped`

- `purpose`: record that queue insertion was skipped for policy or runtime reasons
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`
- `optional_fields`: `task_id`, `reasoning`, `data.candidate_id`, `data.skipped_reason`
- `correlation_keys`: `cycle_id`, `task_id`, `data.candidate_id`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view, debugging tools

#### `Discovery.funnel`

Purpose: summarize one discovery pass.

##### `funnel_summarized`

- `purpose`: record aggregate counts and transitions for a discovery pass
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`
- `optional_fields`: `reasoning`, `data.raw_candidates`, `data.deduplicated`, `data.scored`, `data.filtered_out`, `data.deferred`, `data.queued`
- `correlation_keys`: `cycle_id`
- `producer`: discovery subsystem
- `consumers`: discovery dashboard view, audit trail

### Execution

#### `Execution.planning`

Purpose: describe how a task execution plan was created or revised.

##### `plan_started`

- `purpose`: record start of planning for one task
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `cycle_id`, `detail`
- `optional_fields`: `reasoning`, `data.round`
- `correlation_keys`: `task_id`, `cycle_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view

##### `plan_created`

- `purpose`: record that an initial plan was produced
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `reasoning`, `llm_seq`, `data.plan_version`, `data.round`, `data.step_count`, `data.plan_summary`
- `correlation_keys`: `task_id`, `llm_seq`, `data.plan_version`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task detail, audit tools

##### `plan_revised`

- `purpose`: record that an existing plan was changed
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `reasoning`, `llm_seq`, `data.plan_version`, `data.round`, `data.step_count`, `data.plan_summary`, `data.revision_reason`
- `correlation_keys`: `task_id`, `llm_seq`, `data.plan_version`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task detail

##### `plan_completed`

- `purpose`: record end of the planning stage
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`
- `optional_fields`: `data.plan_version`
- `correlation_keys`: `task_id`, `data.plan_version`
- `producer`: execution subsystem
- `consumers`: execution dashboard view

#### `Execution.tool_call`

Purpose: provide one consistent event model for all tool invocations during execution.

Allowed `tool_type` values initially:

- `git`
- `filesystem`
- `command`
- `control`
- `other`

##### `tool_call_requested`

- `purpose`: record that the agent decided to call a tool
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `data.step_id`, `data.tool_call_id`, `data.tool_type`, `data.tool_name`
- `optional_fields`: `reasoning`, `llm_seq`, `data.input_summary`
- `correlation_keys`: `task_id`, `llm_seq`, `data.step_id`, `data.tool_call_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, audit tools

##### `tool_call_started`

- `purpose`: record that tool execution actually began
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `data.step_id`, `data.tool_call_id`, `data.tool_type`, `data.tool_name`
- `optional_fields`: `data.input_summary`
- `correlation_keys`: `task_id`, `data.step_id`, `data.tool_call_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view

##### `tool_call_succeeded`

- `purpose`: record successful completion of a tool invocation
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`, `data.step_id`, `data.tool_call_id`, `data.tool_type`, `data.tool_name`
- `optional_fields`: `data.output_summary`, `data.duration_ms`, `data.exit_code`, `data.artifact_refs`
- `correlation_keys`: `task_id`, `data.step_id`, `data.tool_call_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task trace projection

##### `tool_call_failed`

- `purpose`: record failed completion of a tool invocation
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`, `data.step_id`, `data.tool_call_id`, `data.tool_type`, `data.tool_name`
- `optional_fields`: `reasoning`, `data.output_summary`, `data.duration_ms`, `data.exit_code`, `data.artifact_refs`
- `correlation_keys`: `task_id`, `data.step_id`, `data.tool_call_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task trace projection, debugging tools

#### `Execution.verification`

Purpose: record execution-local verification behavior before the task is finalized.

##### `verification_started`

- `purpose`: record start of verification for a task
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `reasoning`, `data.verification_id`
- `correlation_keys`: `task_id`, `data.verification_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view

##### `verification_passed`

- `purpose`: record a successful verification outcome
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`
- `optional_fields`: `data.verification_id`, `data.check_name`, `data.command`, `data.exit_code`, `data.duration_ms`
- `correlation_keys`: `task_id`, `data.verification_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task detail

##### `verification_failed`

- `purpose`: record a failed verification outcome
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`
- `optional_fields`: `reasoning`, `data.verification_id`, `data.check_name`, `data.command`, `data.exit_code`, `data.duration_ms`
- `correlation_keys`: `task_id`, `data.verification_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task detail, human review tooling

##### `verification_inconclusive`

- `purpose`: record that verification did not reach a pass/fail decision
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `reasoning`, `data.verification_id`, `data.inconclusive_reason`
- `correlation_keys`: `task_id`, `data.verification_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, debugging tools

#### `Execution.state`

Purpose: record coarse execution lifecycle transitions for a task.

##### `execution_started`

- `purpose`: record start of execution
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `cycle_id`, `detail`
- `optional_fields`: `data.from_status`, `data.to_status`
- `correlation_keys`: `task_id`, `cycle_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view

##### `execution_blocked`

- `purpose`: record that execution cannot progress
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `reasoning`, `data.blocked_reason`, `data.from_status`, `data.to_status`
- `correlation_keys`: `task_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, human review tooling

##### `execution_resumed`

- `purpose`: record that previously blocked execution resumed
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `data.resumed_by`, `data.from_status`, `data.to_status`
- `correlation_keys`: `task_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view

##### `execution_completed`

- `purpose`: record successful end of execution
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`
- `optional_fields`: `data.completion_kind`, `data.to_status`
- `correlation_keys`: `task_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task detail

##### `execution_failed`

- `purpose`: record failed end of execution
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`
- `optional_fields`: `reasoning`, `data.completion_kind`, `data.from_status`, `data.to_status`
- `correlation_keys`: `task_id`
- `producer`: execution subsystem
- `consumers`: execution dashboard view, task detail, debugging tools

### Memory

#### `Memory.recall`

Purpose: describe retrieval of prior experiences or exploration context.

##### `experience_lookup_started`

- `purpose`: record start of experience lookup
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `data.query`
- `correlation_keys`: `task_id`
- `producer`: memory subsystem
- `consumers`: memory dashboard view, audit trail

##### `experience_found`

- `purpose`: record that at least one relevant experience was found
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `data.query`, `data.match_count`, `data.recalled_experience_ids`
- `correlation_keys`: `task_id`
- `producer`: memory subsystem
- `consumers`: memory dashboard view

##### `experience_injected`

- `purpose`: record that recalled experiences were injected into downstream context
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `llm_seq`, `data.query`, `data.injected_count`, `data.recalled_experience_ids`
- `correlation_keys`: `task_id`, `llm_seq`
- `producer`: memory subsystem
- `consumers`: memory dashboard view, audit tools

##### `experience_lookup_empty`

- `purpose`: record that no relevant experience was found
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `data.query`
- `correlation_keys`: `task_id`
- `producer`: memory subsystem
- `consumers`: memory dashboard view

#### `Memory.learning`

Purpose: describe learning extraction from completed or failed work.

##### `learning_extraction_started`

- `purpose`: record start of learning extraction
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `llm_seq`, `data.extraction_kind`
- `correlation_keys`: `task_id`, `llm_seq`
- `producer`: memory subsystem
- `consumers`: memory dashboard view

##### `learning_extraction_succeeded`

- `purpose`: record successful learning extraction
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`
- `optional_fields`: `llm_seq`, `data.extraction_kind`, `data.learned_count`, `data.stored_experience_ids`
- `correlation_keys`: `task_id`, `llm_seq`
- `producer`: memory subsystem
- `consumers`: memory dashboard view, audit tools

##### `learning_extraction_failed`

- `purpose`: record failed learning extraction
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`, `success`
- `optional_fields`: `reasoning`, `llm_seq`, `data.extraction_kind`, `data.failure_reason`
- `correlation_keys`: `task_id`, `llm_seq`
- `producer`: memory subsystem
- `consumers`: memory dashboard view, debugging tools

#### `Memory.persistence`

Purpose: describe durable writes to experience and exploration state.

##### `experience_recorded`

- `purpose`: record that a new experience was stored
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `data.experience_id`
- `correlation_keys`: `task_id`, `data.experience_id`
- `producer`: memory subsystem
- `consumers`: memory dashboard view

##### `experience_deduplicated`

- `purpose`: record that an experience write was deduplicated
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `data.experience_id`, `data.deduplicated_against`
- `correlation_keys`: `task_id`, `data.experience_id`
- `producer`: memory subsystem
- `consumers`: memory dashboard view, debugging tools

##### `exploration_state_updated`

- `purpose`: record that exploration or interest state changed
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `cycle_id`, `detail`
- `optional_fields`: `data.exploration_map_updated`, `data.interest_profile_updated`
- `correlation_keys`: `cycle_id`
- `producer`: memory subsystem
- `consumers`: memory dashboard view, audit trail

### Inbox

#### `Inbox.thread`

Purpose: describe the lifecycle of human-visible review threads.

##### `thread_created`

- `purpose`: record thread creation
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `thread_id`, `detail`
- `optional_fields`: `task_id`, `data.thread_title`, `data.created_by`
- `correlation_keys`: `thread_id`, `task_id`
- `producer`: inbox subsystem
- `consumers`: inbox dashboard view, task correlation layer

##### `thread_status_changed`

- `purpose`: record a thread status transition
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `thread_id`, `detail`
- `optional_fields`: `task_id`, `data.old_status`, `data.new_status`
- `correlation_keys`: `thread_id`, `task_id`
- `producer`: inbox subsystem
- `consumers`: inbox dashboard view

#### `Inbox.message`

Purpose: describe message activity within a thread.

##### `message_added`

- `purpose`: record that a message was added to a thread
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `thread_id`, `detail`
- `optional_fields`: `task_id`, `data.message_id`, `data.role`, `data.body_preview`
- `correlation_keys`: `thread_id`, `task_id`, `data.message_id`
- `producer`: inbox subsystem
- `consumers`: inbox dashboard view

##### `message_read`

- `purpose`: record that a message was consumed by the runtime or a human
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `thread_id`, `detail`
- `optional_fields`: `task_id`, `data.message_id`, `data.read_by`
- `correlation_keys`: `thread_id`, `task_id`, `data.message_id`
- `producer`: inbox subsystem
- `consumers`: inbox dashboard view, audit tools

#### `Inbox.handoff`

Purpose: describe task escalation to human review and its resolution.

##### `human_help_requested`

- `purpose`: record that the agent asked for human help
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `thread_id`, `detail`
- `optional_fields`: `reasoning`, `data.handoff_kind`
- `correlation_keys`: `task_id`, `thread_id`
- `producer`: inbox/execution boundary
- `consumers`: inbox dashboard view, task detail

##### `human_response_received`

- `purpose`: record that a human response arrived
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `thread_id`, `detail`
- `optional_fields`: `data.handoff_kind`
- `correlation_keys`: `task_id`, `thread_id`
- `producer`: inbox subsystem
- `consumers`: inbox dashboard view, task detail

##### `human_resolution_applied`

- `purpose`: record that a human response was applied to runtime state
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `thread_id`, `detail`
- `optional_fields`: `data.handoff_kind`, `data.resolution_kind`, `data.applied_by`
- `correlation_keys`: `task_id`, `thread_id`
- `producer`: inbox/execution boundary
- `consumers`: inbox dashboard view, task detail

### LLM

#### `LLM.routing`

Purpose: explain which model route or binding point was used for a module action.

##### `binding_point_selected`

- `purpose`: record binding point selection for an LLM-backed action
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `task_id`, `cycle_id`, `llm_seq`, `data.binding_point`
- `correlation_keys`: `task_id`, `cycle_id`, `llm_seq`
- `producer`: LLM routing layer
- `consumers`: LLM dashboard view, audit tools

##### `model_resolved`

- `purpose`: record the specific model registration used
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `task_id`, `cycle_id`, `llm_seq`, `data.binding_point`, `data.model_id`, `data.model_name`, `data.provider`
- `correlation_keys`: `task_id`, `cycle_id`, `llm_seq`
- `producer`: LLM routing layer
- `consumers`: LLM dashboard view, audit tools

#### `LLM.audit_link`

Purpose: correlate module events with LLM audit rows without duplicating full prompt/response data.

##### `llm_call_linked`

- `purpose`: record a reusable correlation from a module action to an LLM audit sequence
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `llm_seq`, `detail`
- `optional_fields`: `task_id`, `cycle_id`, `data.linked_event_id`, `data.prompt_preview`, `data.response_preview`
- `correlation_keys`: `llm_seq`, `task_id`, `cycle_id`, `data.linked_event_id`
- `producer`: correlation layer
- `consumers`: module projections, LLM dashboard view

### ControlPlane

#### `ControlPlane.directive`

Purpose: describe directive reads and writes that affect runtime behavior.

##### `directive_loaded`

- `purpose`: record that the directive was read for runtime use
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `cycle_id`, `data.paused`, `data.focus_areas`, `data.forbidden_paths`
- `correlation_keys`: `cycle_id`
- `producer`: control plane / runtime bootstrap
- `consumers`: control dashboard view, audit trail

##### `directive_updated`

- `purpose`: record that the directive changed
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `data.changed_fields`, `data.paused`, `data.focus_areas`, `data.forbidden_paths`
- `correlation_keys`: none mandatory beyond event id
- `producer`: control plane
- `consumers`: control dashboard view, audit trail

#### `ControlPlane.runtime`

Purpose: describe runtime control operations initiated by humans or the system.

##### `pause_requested`

- `purpose`: record a pause request
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `reasoning`, `cycle_id`, `data.action_source`, `data.runtime_action`
- `correlation_keys`: `cycle_id`
- `producer`: control plane
- `consumers`: control dashboard view, audit trail

##### `resume_requested`

- `purpose`: record a resume request
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `reasoning`, `cycle_id`, `data.action_source`, `data.runtime_action`
- `correlation_keys`: `cycle_id`
- `producer`: control plane
- `consumers`: control dashboard view, audit trail

##### `shutdown_requested`

- `purpose`: record a shutdown request
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `reasoning`, `cycle_id`, `data.action_source`, `data.runtime_action`
- `correlation_keys`: `cycle_id`
- `producer`: control plane
- `consumers`: control dashboard view, audit trail

##### `task_injected`

- `purpose`: record that a task was injected externally
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `task_id`, `detail`
- `optional_fields`: `data.action_source`, `data.runtime_action`, `data.injected_task_title`
- `correlation_keys`: `task_id`
- `producer`: control plane
- `consumers`: control dashboard view, task correlation layer

##### `task_injection_rejected`

- `purpose`: record that external task injection was rejected
- `required_fields`: `event_id`, `module`, `family`, `event_name`, `timestamp`, `detail`
- `optional_fields`: `task_id`, `reasoning`, `data.action_source`, `data.runtime_action`, `data.rejection_reason`
- `correlation_keys`: `task_id`
- `producer`: control plane
- `consumers`: control dashboard view, debugging tools

## Correlation Rules

The implementation must define explicit mappings at least for:

- `Discovery.candidate_queued` → persisted `Task`
- `Discovery.candidate_scored` and `Discovery.candidate_filtered_out` → task or candidate lineage
- `Execution.plan_*` → task planning artifacts and linked `llm_seq`
- `Execution.tool_call_*` → execution trace rows, tool outputs, and task detail
- `Execution.verification_*` → task verification result
- `Inbox.*` → thread store and linked tasks
- `LLM.llm_call_linked` → specific LLM audit rows
- `ControlPlane.task_injected` → persisted `Task`

Correlation logic must not live only in page code. It should be testable independently of the dashboard.

## Projection Rules

Each dashboard or API projection must declare:

- which module events it reads
- which correlated entities it joins
- which artifacts are shown inline
- which artifacts are drill-down only

Examples:

- Discovery projection:
  - source events: `Discovery.*`
  - joins: queued task summaries, relevant score provenance
- Execution projection:
  - source events: `Execution.*`
  - joins: task detail, execution trace, verification result
- Inbox projection:
  - source events: `Inbox.*`
  - joins: thread details, linked task summaries
- LLM projection:
  - source events: `LLM.*`
  - joins: audit summaries by `llm_seq`

## Frontend Implementation

Frontend code should not treat observability events as untyped blobs. It should consume the new architecture in three layers.

### 1. Typed Envelope And Data Models

The frontend should define:

- a shared event envelope type
- family-level `data` schema types
- specific decoded event types where page logic needs event-specific guarantees

Recommended layout:

- `frontend/src/types/events.ts`
- `frontend/src/types/eventData.ts`

The shared envelope type should mirror the backend event envelope:

- `event_id`
- `module`
- `family`
- `event_name`
- `timestamp`
- optional cross-module correlation keys
- `detail`
- `reasoning`
- `success`
- `data`

Family-level `data` types should mirror the documented schemas in this plan. Frontend code must not read `data` as `any` in page components.

### 2. Decoder Registry

Frontend event parsing should be registry-driven.

Recommended layout:

- `frontend/src/lib/eventDecoders.ts`

The registry key is:

- `module.family.event_name`

Each decoder should:

- validate the envelope shape needed by the event
- validate and decode `data`
- return a typed decoded event object

This keeps parsing logic out of page components and prevents repeated `if module == ... and family == ...` branching across the UI.

### 3. Projection Builders

Pages should not directly transform raw events into UI state. They should consume module-scoped projection builders.

Recommended layout:

- `frontend/src/lib/projections/buildDiscoveryProjection.ts`
- `frontend/src/lib/projections/buildExecutionProjection.ts`
- `frontend/src/lib/projections/buildInboxProjection.ts`

Each projection builder should:

- accept decoded events and any joined entity payloads
- apply module-specific ordering, grouping, and correlation logic
- return a stable view model for the page

This makes page rendering independent from raw event storage details.

### 4. Page Consumption

Pages should only consume:

- decoded event objects
- projection builder output

Pages should not:

- decode `data` inline
- hardcode `module` / `family` / `event_name` branching
- reconstruct cross-entity joins locally

This keeps display concerns separate from event semantics and correlation rules.

### 5. API Shape Expectations

Dashboard APIs may return:

- raw event envelopes for diagnostic or timeline views
- projection payloads for feature pages

When raw events are returned, frontend code must still pass them through the decoder registry before page use.

When projection payloads are returned, the payload contract must still map back to documented module catalogs so the frontend is not inventing semantics that differ from the backend.

### 6. Frontend Migration Sequence

The frontend migration should proceed in this order:

1. introduce shared event envelope and family `data` types
2. add decoder registry
3. migrate Discovery to decoded events plus a projection builder
4. migrate Execution views to the same model
5. migrate remaining observability pages

Discovery should be the first exemplar because it currently exposes the strongest mismatch between raw event filtering and task-correlated observability artifacts.

## Migration Plan

### Phase 1: Introduce Envelope And Registry Contracts

- define the standard envelope in code and docs
- align observer helpers with module, family, and event naming
- add registry-driven decoding for `data`
- add tests for envelope consistency
- add frontend shared event types that mirror the backend envelope

### Phase 2: Implement Discovery Projection On Catalog Rules

- migrate Discovery to the new catalog structure
- remove ad hoc raw-event assumptions from Discovery-specific projections
- add frontend decoder coverage for `Discovery.*`
- introduce a Discovery projection builder in the frontend

### Phase 3: Implement Execution Projection On Catalog Rules

- migrate planning, tool calls, verification, and execution state
- ensure task trace correlation is explicit and tested
- add frontend decoder coverage for `Execution.*`
- introduce an Execution projection builder in the frontend

### Phase 4: Implement Inbox, LLM, And Control Plane Correlations

- connect human review, llm linkage, and control-plane actions through the same model
- migrate remaining frontend observability pages to decoder plus projection patterns

### Phase 5: Update Design Docs

- update `docs/design/observability.md`
- update any affected design docs that depend on old event assumptions

## Verification

The implementation is complete only when:

- every event emitted by runtime code maps to a documented module, family, and event name
- every projection decodes `data` through the registry rather than page-local string matching
- frontend pages consume typed decoded events or projection builders rather than raw `data` access
- correlation rules are unit-tested
- each dashboard projection is tested against module contracts rather than ad hoc phase or action filters
- Discovery and Execution are both migrated to the new model
- design docs describe the implemented architecture accurately
