# Experience Module Design

> Module: `src/llm247_v2/storage/experience.py`
> Last updated: 2026-03-05

## Purpose

The experience module is the agent's long-term memory. It captures lessons from every completed or failed task, stores them persistently, retrieves relevant past knowledge when planning future tasks, and periodically consolidates overlapping entries.

The goal is to make the agent smarter over time: what it learned on day 1 should inform what it does on day 90.

## Responsibilities

1. **Store** — persist structured learnings (patterns, pitfalls, insights, techniques) extracted from task outcomes.
2. **Recall** — given an incoming task, surface the most relevant past experiences to inject into the planning prompt.
3. **Organize** — periodically merge, deduplicate, and decay experiences so the store stays dense with high-quality knowledge rather than bloated with redundant entries.
4. **Expose** — provide stats and list APIs for the dashboard to display agent memory contents.

## Current Design

### Data Model

```python
@dataclass
class Experience:
    id: str               # sha256(task_id + summary)[:12]
    task_id: str          # source task
    category: str         # pattern | pitfall | insight | technique
    summary: str          # one-sentence takeaway
    detail: str           # supporting explanation
    tags: str             # comma-separated keywords
    confidence: float     # 0.0–1.0, decays over time if never applied
    created_at: str
    applied_count: int    # incremented each time injected into a planning prompt
    source_outcome: str   # "completed" or "failed"
```

### Write Path

```
task completes/fails
    -> LLM reflects on execution log + verification result
    -> extract_learnings() returns 1-3 Experience records
    -> ExperienceStore.add_batch()
```

Every experience is extracted independently, with no awareness of what already exists. Experiences from similar tasks accumulate as separate records.

### Read Path

```
task about to be planned
    -> ExperienceStore.search(task.title + task.source, limit=5)
    -> SQL LIKE on summary/detail/tags
    -> format_experiences_for_prompt()
    -> injected into plan_task prompt
```

Recall is pure keyword matching. Brittle when experience wording diverges from task title wording.

### Organization

`consolidate()` runs every 10 completed tasks:
1. Exact-summary dedup.
2. Confidence decay on old, never-applied experiences.
3. Prune experiences below confidence threshold.
4. LLM-merge clusters of experiences whose summaries share the same 3 sorted words.

## Known Limitations

| Limitation | Impact |
|------------|--------|
| Keyword recall | Misses semantically related experiences with different wording |
| Blind extraction | Same lesson extracted repeatedly from similar tasks |
| Crude clustering | LLM merge step groups by first-3-words — misses most semantic duplicates |
| No source-task context | Can't recall "what did I learn last time I did something like this?" |

## Planned Upgrade: Embedding-Based Recall + Structured Organization

Full specification: `docs/plans/2026-03-05-experience-recall-upgrade.md`

### Recall: Multi-Path + LLM Rerank

Replace keyword search with a two-path recall followed by LLM precision filtering.

**Path A — Embedding semantic recall**

Embed `task.title + task.description` at query time. Compare against stored embeddings of each experience (`summary + detail + source_task_title`). Cosine similarity, top-K candidates.

**Path B — Source task recall**

Each experience stores the title and description of the task it was learned from. Embed query against this source task context. Catches cases where current task resembles a past task even if the lesson wording is different.

**LLM rerank**

Merge Path A + B candidates (~15-20 items). LLM selects 3-5 most relevant for the current task with a short explanation per selection.

### Write: Context-Aware Structured Extraction

Before extracting learnings, recall top-10 existing relevant experiences. Pass them to the extraction prompt. LLM outputs structured operations instead of flat learnings:

```json
{
  "reinforce": [{"id": "exp_xxx", "confidence_delta": 0.1}],
  "update":    [{"id": "exp_yyy", "new_detail": "..."}],
  "new":       [{"category": "pattern", "summary": "...", ...}]
}
```

This eliminates duplication at the source: the LLM sees what already exists and decides whether to reinforce, refine, or add.

### Organization: Embedding-Based Consolidation

Replace sorted-first-3-words clustering with cosine similarity clustering across all stored embeddings. Merge clusters above similarity threshold via LLM.

### Schema Additions

```sql
ALTER TABLE experiences ADD COLUMN embedding BLOB DEFAULT NULL;
ALTER TABLE experiences ADD COLUMN source_task_title TEXT DEFAULT '';
ALTER TABLE experiences ADD COLUMN source_task_desc  TEXT DEFAULT '';
```

Backward compatible — existing rows have NULL embeddings and fall back to keyword search until batch-recomputed.

### Embedding Model

Pending decision: ARK API embedding endpoint (preferred, no new dependency) vs. `sentence-transformers` local model (no network cost, ~80MB download).

## Integration Points

| Caller | Usage |
|--------|-------|
| `agent.py:_execute_single_task` | Recall before planning, inject into prompt |
| `agent.py:_extract_and_store_learnings` | Extract and store after task completion/failure |
| `agent.py:_maybe_consolidate_experience` | Consolidate every 10 tasks |
| `discovery/interest.py:build_interest_profile` | Derive interest topics from experience category stats and tags |
| `dashboard/server.py:_api_experiences` | List/search for dashboard display |
| `execution/planner.py:plan_task_with_constitution` | Receives pre-formatted experience context string |

## Design Constraints

- **Zero new infrastructure dependencies** — no vector database, no external services. SQLite + brute-force cosine is sufficient at experience store scale (hundreds to low thousands of records).
- **Graceful degradation** — if embedding computation fails or embeddings are missing, fall back to keyword search.
- **LLM calls are bounded** — rerank adds one LLM call per task execution. Extraction remains one call. Total per-task LLM calls stays under 6.
