# Sprout Architecture Evolution: Toward a Self-Evolving Agent

> Status: Design vision (not yet implemented)
> Date: 2026-03-05
> Scope: Top-level architectural roadmap for evolving TokenBurn from a task-execution engine into a continuously learning, strategically planning, proactively communicating, self-evolving agent.

## Vision

An autonomous engineering agent that runs 24/7, progressively building a deep understanding of its codebase, forming and pursuing multi-day goals, communicating naturally with humans, and deliberately improving its own capabilities — not just executing tasks, but genuinely growing as an engineer over time.

The defining property: **the agent on day 90 is fundamentally better than the agent on day 1, and it made itself that way.**

## Current State Assessment

V2 has a solid action layer. It can discover tasks, plan solutions, execute them safely in isolated worktrees, verify results, and ship PRs — all autonomously, 24/7. The Five Pillars defined in [project.md](project.md) are architecturally sound.

But V2 is a **worker**, not a **thinker**. It finds a task, does the task, extracts a lesson, moves on. It has no concept of long-term goals, no unified understanding of the codebase it works on, no ability to initiate a conversation with a human, and no mechanism to identify and fix its own weaknesses.

### Gap Analysis

| Capability | Current state | Gap |
|-----------|---------------|-----|
| **Task execution** | Complete | — |
| **Knowledge & memory** | Fragmented across 6 stores | No unified world model, no concept formation, no cross-domain reasoning |
| **Strategic planning** | None | Every cycle is independent; no multi-cycle goals or projects |
| **Human communication** | Passive (dashboard, NEEDS_HUMAN) | No proactive reports, no dialogue, no agent-initiated questions |
| **Meta-cognition** | None | Cannot identify its own weaknesses or measure its own growth |
| **Flexible cognition** | Rigid cycle (discover→execute) | Cannot choose to "just read and learn" or "plan a project" |

## Target Architecture: Five Cognitive Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                      STRATEGIC LAYER                             │
│                                                                  │
│  Projects, goals, multi-cycle planning, strategic review         │
│  "What am I trying to achieve? What's the best use of my next   │
│   cycle? Is my current direction working?"                       │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                   │
│  │ Project  │  │  Goal    │  │  Strategic   │                   │
│  │ Manager  │  │ Tracker  │  │  Reviewer    │                   │
│  └──────────┘  └──────────┘  └──────────────┘                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ "what to do"
┌────────────────────────▼────────────────────────────────────────┐
│                      COGNITIVE LAYER                             │
│                                                                  │
│  Unified knowledge model, codebase understanding, capability     │
│  self-assessment                                                 │
│  "What do I know? What don't I know? What am I good/bad at?"    │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                   │
│  │ Knowledge│  │ Codebase │  │  Capability  │                   │
│  │ Memory   │  │ Model    │  │  Profile     │                   │
│  └──────────┘  └──────────┘  └──────────────┘                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ "what I know"
┌────────────────────────▼────────────────────────────────────────┐
│                      ACTION LAYER  (V2 current)                  │
│                                                                  │
│  Discovery, planning, execution, verification, shipping          │
│  "How do I do this specific task?"                               │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Discovery│  │ Planner  │  │ Executor │  │ Verifier │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└────────────────────────┬────────────────────────────────────────┘
                         │ "what happened"
┌────────────────────────▼────────────────────────────────────────┐
│                      REFLECTION LAYER                            │
│                                                                  │
│  Learning extraction, meta-cognition, self-improvement           │
│  "What did I learn? Where am I weak? How do I get better?"       │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                   │
│  │ Learning │  │  Meta-   │  │    Self-     │                   │
│  │ Engine   │  │ Cognition│  │  Improvement │                   │
│  └──────────┘  └──────────┘  └──────────────┘                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ "what to say"
┌────────────────────────▼────────────────────────────────────────┐
│                      COMMUNICATION LAYER                         │
│                                                                  │
│  Proactive reports, human dialogue, questions, strategy          │
│  discussion                                                      │
│  "What should I tell the human? What should I ask?"              │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                   │
│  │ Reporter │  │ Dialogue │  │   Question   │                   │
│  │          │  │ Engine   │  │   Asker      │                   │
│  └──────────┘  └──────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

### Information Flow Between Layers

```
Strategic  ──"goal context"──►  Action     (plan tasks in service of projects)
Cognitive  ──"knowledge"────►  Action     (recall relevant knowledge when planning)
Action     ──"outcomes"─────►  Reflection (feed execution results to learning)
Reflection ──"learnings"────►  Cognitive  (update knowledge model)
Reflection ──"weaknesses"───►  Strategic  (generate self-improvement projects)
Cognitive  ──"understanding"►  Communication (ground reports in actual knowledge)
Strategic  ──"priorities"───►  Communication (decide what's worth reporting)
Communication ──"human input"► Strategic  (human guidance shapes goals)
```

## Layer Designs

### Layer 1: Strategic Layer

**Problem it solves:** The agent cannot pursue goals that span more than one cycle. A human engineer doesn't think in isolated tasks — they think in projects: "This week I'm refactoring the auth module, step 1 is understanding the current flow, step 2 is writing tests, step 3 is the refactor."

**Core concept: Project**

```python
@dataclass
class Project:
    id: str
    title: str                     # "Refactor TaskStore for better concurrency"
    goal: str                      # what success looks like
    status: str                    # active | paused | completed | abandoned
    milestones: List[Milestone]    # ordered steps toward the goal
    source: str                    # "self_improvement" | "human" | "meta_cognition"
    created_at: str
    progress_summary: str          # LLM-updated narrative of where things stand
    related_task_ids: List[str]    # tasks spawned by this project
```

**Cycle decision model:** At the start of each cycle, instead of always running discovery, the agent chooses a cycle mode:

```
cycle_start:
    if active_projects exist:
        review project progress
        if next milestone is actionable:
            mode = "execute" (plan + do the next project step)
        elif milestone needs research:
            mode = "study" (read code, build understanding, no task output)
        elif project is blocked:
            mode = "communicate" (ask human for guidance)
    elif no active projects:
        mode = "discover" (current behavior: find new tasks)

    every N cycles:
        mode = "reflect" (strategic review: are my projects working?)
```

**Strategic review:** Every K cycles (e.g., every 20), the agent steps back and asks:
- Which projects are progressing? Which are stuck?
- Am I spending tokens on the right things?
- Should I start, pause, or abandon any projects?
- What did I learn this week that changes my priorities?

### Layer 2: Cognitive Layer

**Problem it solves:** The agent's knowledge is scattered across 6 stores with no connections between them. It cannot reason about what it knows.

**Three sub-components:**

**2a. Knowledge Memory** (the experience recall upgrade already in design)

Unified, embedding-based, structured memory with multi-path recall and LLM rerank. Context-aware extraction that reinforces/updates existing knowledge instead of blindly appending. See `docs/plans/2026-03-05-experience-recall-upgrade.md`.

**2b. Codebase Model**

A persistent, evolving representation of the agent's understanding of the codebase. Not just "I scanned this directory" (exploration map), but "I understand what this module does, how it connects to other modules, and what its problems are."

```python
@dataclass
class ModuleUnderstanding:
    path: str                      # "src/llm247_v2/storage/"
    purpose: str                   # LLM-generated summary of what it does
    architecture_notes: str        # key design decisions the agent has identified
    known_issues: List[str]        # problems the agent has noticed
    understanding_depth: float     # 0.0 (never seen) to 1.0 (deeply understood)
    last_studied: str              # when the agent last read this module
    related_modules: List[str]     # connections to other modules
    task_history: List[str]        # tasks that touched this module
```

Updated by:
- Discovery strategies (when scanning code)
- Task execution (when modifying code)
- Study mode (when deliberately reading code to understand it)

Queried by:
- Planner (to provide richer context than just reading the file)
- Discovery (to identify under-understood areas worth exploring)
- Strategic review (to assess where the agent's knowledge gaps are)

**2c. Capability Profile**

The agent's self-model of what it's good and bad at.

```python
@dataclass
class CapabilityProfile:
    task_type_stats: Dict[str, TypeStats]  # success rate, avg time, by task type
    strength_areas: List[str]              # "test writing", "simple bug fixes"
    weakness_areas: List[str]              # "complex refactors", "async code"
    recent_failures: List[FailurePattern]  # recurring failure modes
    updated_at: str
```

Built from task history analysis. Used by:
- Strategic layer (avoid projects in weak areas, or deliberately target them for growth)
- Discovery (adjust task value scoring by capability match)
- Meta-cognition (identify improvement targets)

### Layer 3: Action Layer (Exists — V2 Current)

The current discover → plan → execute → verify → ship pipeline. Needs no structural change, but gains richer inputs from the layers above:

- **Planner** receives project context (not just task description) and codebase model context (not just raw file reads)
- **Discovery** is guided by strategic priorities, not just heuristic scanning
- **Execution** tracks which modules are touched, feeding the codebase model

### Layer 4: Reflection Layer

**Problem it solves:** The agent extracts lessons from individual tasks but never steps back to identify patterns across tasks, assess its own performance, or generate targeted self-improvement.

**Three sub-components:**

**4a. Learning Engine** (exists, being upgraded)

Post-task learning extraction. The experience recall upgrade moves this from blind extraction to context-aware structured extraction.

**4b. Meta-Cognition**

Periodic (every N tasks or every M cycles) analysis of the agent's own performance:

```
Meta-cognition process:
  1. Query task history: last 20 tasks
  2. Analyze patterns:
     - Failure clusters (same type of failure recurring?)
     - Time/token cost outliers (which tasks are disproportionately expensive?)
     - Planning accuracy (did plans need many steps? did execution match plan?)
     - Verification failure rate (are changes often broken?)
  3. Generate insights:
     - "3 of last 5 complex refactors failed at verification — my refactor plans may be too aggressive"
     - "Test-writing tasks take 3x fewer tokens than bug fixes — I'm efficient at testing"
  4. Feed to:
     - Capability Profile (update strengths/weaknesses)
     - Strategic Layer (suggest self-improvement projects)
```

**4c. Self-Improvement Engine**

Converts meta-cognition insights into concrete self-improvement actions:

- Meta-cognition identifies: "My planning prompts produce over-complex plans for refactoring tasks"
- Self-improvement generates a project: "Improve plan_task.txt to produce smaller, incremental refactoring steps"
- The agent executes this project through its normal action layer (plan, edit the prompt, test, PR)
- After the change lands, meta-cognition tracks whether refactoring success rate improves

This closes the evolution loop:

```
do tasks → reflect on performance → identify weakness →
improve self → do tasks better → reflect again → ...
```

### Layer 5: Communication Layer

**Problem it solves:** The agent is silent unless it fails. Humans have no way to have a conversation with it.

**Three sub-components:**

**5a. Reporter**

Periodic reports generated automatically:

```python
@dataclass
class AgentReport:
    period: str                    # "daily" | "weekly"
    tasks_summary: str             # what was done, outcomes
    learnings_summary: str         # key things learned
    projects_progress: str         # active projects and their status
    recommendations: List[str]     # suggestions for human attention
    questions: List[str]           # things the agent wants human input on
    metrics: Dict                  # tokens spent, success rate, etc.
```

Delivery: written to a file in `.llm247_v2/reports/`, shown in dashboard, optionally sent via webhook.

**5b. Proactive Messages**

Not just failure-triggered NEEDS_HUMAN, but a general message channel:

| Trigger | Message type | Example |
|---------|-------------|---------|
| Task blocked | Help request (existing) | "Verification failed, here's what happened" |
| Significant finding | Insight alert | "Found a security issue in auth module, severity high" |
| Uncertainty | Question | "I could approach this 2 ways. Option A is safer but slower. Preference?" |
| Milestone reached | Progress update | "Phase 1 of auth refactor complete. 3 tests added. Moving to phase 2." |
| Strategic decision | Proposal | "I've been studying the storage layer for 3 cycles. I propose a 5-step refactor project. Approve?" |

Requires a new `AgentMessage` model and a message queue (SQLite table) that the dashboard polls.

**5c. Dialogue Engine (Future)**

Eventually: the ability for humans to have a back-and-forth conversation with the agent about strategy, priorities, and technical decisions. This is the most complex component and depends on having the other layers in place first (the agent needs a world model to have an informed conversation).

Minimum viable form: a chat interface in the dashboard where humans can post messages, and the agent responds in its next cycle after consulting its knowledge memory and project context.

## Revised Cycle Model

The current rigid cycle:
```
every cycle: discover 1 task → execute 1 task → sleep
```

Evolves to a flexible cycle with multiple modes:

```
every cycle:
  1. Load directive + constitution
  2. Check message queue (human sent something?)
  3. Choose cycle mode:

     MODE: execute
       Pick next task from active project or queue
       Plan → execute → verify → ship
       Extract learnings

     MODE: discover
       Run discovery strategies
       Evaluate and queue candidates
       Optionally assign to projects

     MODE: study
       Select an under-understood module
       Read and analyze code (LLM-powered)
       Update codebase model
       No task output — pure learning

     MODE: reflect
       Run meta-cognition analysis
       Update capability profile
       Generate self-improvement proposals
       Generate periodic report if due

     MODE: communicate
       Process human messages
       Generate proactive messages/reports
       Update project plans based on human input

  4. Update knowledge memory
  5. Sleep
```

Mode selection is itself a decision the agent makes, informed by:
- Are there active projects with pending milestones? → execute
- Is the task queue empty? → discover
- Has it been N cycles since last reflection? → reflect
- Did a human send a message? → communicate
- Are there modules with low understanding depth? → study

## Evolution Phases

### Phase 1: Knowledge Memory (Current)
**Focus:** Fix the memory foundation. Without good recall, no higher layer works.
- Embedding-based experience recall
- Context-aware structured extraction (reinforce/update/new)
- Source task context for retrieval
- LLM rerank

**Deliverable:** `ExperienceStore` upgraded per `docs/plans/2026-03-05-experience-recall-upgrade.md`

### Phase 2: Strategic Layer
**Focus:** Give the agent the ability to pursue multi-cycle goals.
- `Project` model and persistence
- Cycle mode selection (execute vs discover)
- Project-aware task discovery and planning
- Basic strategic review (every N cycles)

**Deliverable:** Agent can create, track, and complete projects that span multiple cycles.

### Phase 3: Communication Layer
**Focus:** The agent can talk, not just show.
- `AgentMessage` model and message queue
- Periodic reporter (daily summary)
- Proactive message triggers (insight alerts, proposals)
- Dashboard message feed
- Human reply mechanism (post message → agent reads next cycle)

**Deliverable:** Two-way asynchronous communication between agent and human.

### Phase 4: Reflection & Meta-Cognition
**Focus:** The agent knows itself.
- Capability profile built from task history
- Meta-cognition analysis (failure patterns, cost analysis)
- Self-improvement project generation
- Prompt evolution tracking (did changing a prompt improve outcomes?)

**Deliverable:** Agent identifies its own weaknesses and generates targeted self-improvement tasks.

### Phase 5: Codebase Model & Study Mode
**Focus:** Deep understanding, not just task-level knowledge.
- `ModuleUnderstanding` model
- Study cycle mode (read-only, no task output)
- Architecture-aware planning (planner uses module model for richer context)
- Knowledge gap identification ("I've never looked at module X")

**Deliverable:** Agent builds and maintains a structured understanding of every module it has interacted with.

### Phase 6: Dialogue Engine
**Focus:** Real conversation.
- Chat interface in dashboard
- Agent responds to open-ended questions using its world model
- Strategy discussion (human and agent co-plan projects)
- Requires all previous layers to be meaningful

**Deliverable:** Human can have a technical conversation with the agent about the codebase and strategy.

## What NOT to Change

The following V2 design decisions remain correct and should be preserved:

- **Constitution + Directive split** — immutable identity vs mutable behavior control
- **Git worktree isolation** — safe self-modification through PR review
- **SQLite for persistence** — no new infrastructure dependencies
- **Observer event system** — centralized observability
- **LLM audit trail** — full prompt/response logging
- **Prompt templates in `.txt` files** — separated from business logic
- **Safety policy** — command allowlist, path protection, immutable paths

## Architectural Invariant

Every new layer must satisfy the Five Pillars:

1. **Autonomous** — new capabilities run without human intervention
2. **Learning** — every new layer feeds knowledge back to memory
3. **Self-modifiable** — the agent can improve its own strategic/reflection/communication logic
4. **Observable** — all decisions in new layers are logged and visible
5. **Controllable** — humans can override any layer's behavior via directive

A layer that violates any pillar is architecturally broken, regardless of how clever it is.
