# Experience Recall & Structured Organization Upgrade

> Status: Design (not yet implemented)
> Date: 2026-03-05
> Context: Experience module currently uses keyword LIKE matching for recall, which is brittle. Experiences accumulate as flat, unconnected records with frequent semantic duplication.

## Problem Statement

1. **Recall is keyword-based** — `SQL LIKE` on `summary/detail/tags`. If experience wording doesn't share literal tokens with the task title, it misses. After structured organization (consolidation, LLM rewrite), keyword overlap drops further.

2. **Experiences pile up as duplicates** — extraction has no awareness of existing experiences. The same lesson from 10 similar tasks produces 10 near-identical records.

3. **No source-task context** — each experience stores `task_id` but not the source task's title/description. Can't do "find experiences from tasks similar to this one."

## Architecture: Multi-Path Recall + LLM Rerank + Structured Write

```
READ PATH (planning stage)                    WRITE PATH (post-task)
===========================                   ========================

  current task                                  completed task
      |                                              |
      v                                              v
 +-----------+    +-----------+              +------------------+
 | Path A:   |    | Path B:   |              | 1. Embed recall  |
 | embedding |    | source    |              |    top-10 exist  |
 | similarity|    | task sim  |              |                  |
 | task desc  |    | task desc  |              | 2. LLM extract  |
 | vs exp     |    | vs exp's   |              |    with context  |
 | embedding  |    | src task   |              |    of existing   |
 +-----+-----+    +-----+-----+              |                  |
       |                |                     | 3. Output:       |
       v                v                     |    reinforce /   |
   +---+----------------+---+                 |    update /      |
   | Merge & dedup candidates|                |    new           |
   |      (15-20 items)      |                +--------+---------+
   +----------+--------------+                         |
              |                                        v
              v                                  experience store
      +-------+--------+                        (with embeddings)
      | LLM rerank     |
      | select top 3-5 |
      +-------+--------+
              |
              v
       inject into plan prompt
```

## Read Path: Multi-Path Recall + LLM Rerank

### Path A: Embedding Semantic Recall

Query: `embed(task.title + " " + task.description)` -> cosine similarity against all `exp.embedding` -> top-K.

- Embedding computed at experience creation/update time, stored as BLOB in SQLite.
- At query time, embed the current task, compute cosine against all stored embeddings.
- Scale: hundreds to low thousands of experiences. Brute-force cosine is fine (<10ms for 5000 768-dim vectors in NumPy).

### Path B: Source Task Recall

Each experience records the source task's title and description. Recall path:

1. Embed current task description.
2. Compare against `exp.source_task_title + exp.source_task_desc` embeddings.
3. This catches: "I did a similar task before, what did I learn from it?"

Implementation: store `source_task_embedding` alongside `embedding`. At query time, compute cosine against both columns, take union of top-K from each.

Alternatively (simpler): store `source_task_title` and `source_task_desc` as text, concatenate with summary for a single combined embedding. This avoids a second embedding column.

**Recommended: single combined embedding** of `summary + detail + source_task_title`. Simpler, one cosine pass, still captures both the knowledge content and its origin context.

### Merge & LLM Rerank

1. Take union of top-K from Path A and Path B (K=10 each, deduplicated -> ~15-20 candidates).
2. Send to LLM with a rerank prompt:

```
You are selecting relevant past experiences for an engineering task.

## Current Task
Title: {task_title}
Description: {task_description}

## Candidate Experiences
{numbered list of candidate summaries + details}

## Instructions
Select 3-5 experiences most relevant to this task.
For each, explain in one sentence why it's relevant.
Discard anything not directly applicable.

## Output (strict JSON)
{"selected": [{"index": 1, "reason": "..."}, ...]}
```

3. Return selected experiences for injection into the planning prompt.

**Cost note**: one extra LLM call per task execution. Acceptable — the agent already makes 3-5 LLM calls per task (plan, execute, verify, extract learnings).

## Write Path: Structured Organization at Extraction Time

### Current flow (blind extraction)

```
task completes -> LLM extracts 1-3 learnings -> add_batch() -> done
```

### New flow (context-aware extraction)

```
task completes
    |
    v
embed(task.title + task.description)
    |
    v
recall top-10 existing experiences (by embedding similarity)
    |
    v
LLM extract_learnings with existing experiences as context
    |
    v
LLM outputs structured operations (not just flat learnings)
    |
    v
apply operations to experience store
```

### New extraction prompt output format

```json
{
  "reinforce": [
    {"id": "exp_xxx", "confidence_delta": 0.1, "reason": "confirmed by this task"}
  ],
  "update": [
    {"id": "exp_yyy", "new_detail": "also applies to async contexts", "reason": "..."}
  ],
  "new": [
    {
      "category": "pattern",
      "summary": "...",
      "detail": "...",
      "tags": "...",
      "confidence": 0.8
    }
  ]
}
```

- **reinforce**: existing experience confirmed; bump confidence.
- **update**: existing experience needs refinement; update detail/tags.
- **new**: genuinely novel learning; create new record.

This eliminates duplication at the source — the LLM sees what already exists and decides whether to add, merge, or skip.

### Embedding lifecycle

- **On new experience creation**: compute and store embedding.
- **On experience update**: recompute embedding.
- **On consolidation merge**: recompute embedding for merged record.

## Consolidation Upgrade

Current consolidation uses sorted-first-3-words clustering. Replace with embedding-based clustering:

1. Load all experience embeddings.
2. Compute pairwise cosine similarity matrix.
3. Cluster experiences with similarity > threshold (e.g., 0.85).
4. For each cluster with 2+ members, LLM-merge into one higher-quality experience.
5. Recompute embedding for merged record.
6. Continue: decay stale experiences, prune low-confidence.

## Data Schema Changes

### Experience table additions

```sql
ALTER TABLE experiences ADD COLUMN embedding BLOB DEFAULT NULL;
ALTER TABLE experiences ADD COLUMN source_task_title TEXT DEFAULT '';
ALTER TABLE experiences ADD COLUMN source_task_desc TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_exp_has_embedding
    ON experiences((embedding IS NOT NULL));
```

- `embedding`: serialized float32 array (e.g., 768 or 1536 dims depending on model).
- `source_task_title`: title of the task that produced this experience.
- `source_task_desc`: first 500 chars of source task description.

### Embedding storage format

Store as raw bytes via `struct.pack` / `numpy.tobytes()`. Deserialize on load. No need for a vector extension — brute-force cosine is sufficient at this scale.

## Embedding Model Decision

Options:

| Option | Dims | Latency | Dependency | Cost |
|--------|------|---------|------------|------|
| ARK API embedding endpoint | varies | network call | existing ARK client | per-token |
| sentence-transformers local | 384-768 | ~50ms/text | torch + model download | free |
| OpenAI text-embedding-3-small | 1536 | network call | openai SDK | $0.02/1M tokens |

**Recommendation**: check if the existing ARK API (ByteDance) supports an embedding endpoint. If yes, use it — no new dependency. If not, `sentence-transformers` with a small model (e.g., `all-MiniLM-L6-v2`, 384 dims, ~80MB) is the lightest local option.

**TODO**: confirm ARK embedding API availability before implementation.

## Code Changes Summary

| File | Change |
|------|--------|
| `storage/experience.py` | Add `embedding`, `source_task_title`, `source_task_desc` to schema and `Experience` dataclass. Add `semantic_search()` method. Add `update_experience()` for reinforce/update ops. Upgrade `consolidate()` to use embedding clustering. |
| `storage/experience.py` | New: `compute_embedding()` helper (wraps embedding model call). |
| `llm/prompts/extract_learnings.txt` | Add `{existing_experiences_section}` placeholder. Change output format to `reinforce/update/new`. |
| `llm/prompts/rerank_experiences.txt` | New prompt template for LLM reranking. |
| `agent.py:_execute_single_task` | Replace `exp_store.search()` with multi-path recall + LLM rerank. |
| `agent.py:_extract_and_store_learnings` | Recall existing experiences first. Pass to extraction. Apply structured operations (reinforce/update/new). |
| `dashboard/server.py` | No change needed initially. Experience API still returns flat list. |
| `interest.py:build_interest_profile` | Can later use embedding clusters instead of tag counting. (Deferred.) |
| `tests/test_v2_experience.py` | Add tests for semantic_search, update_experience, new extraction format. |

## Migration

- Schema changes via `ALTER TABLE` (backward compatible — new columns have defaults).
- Existing experiences without embeddings: batch-compute on first access or via a one-time migration script.
- `semantic_search()` falls back to keyword search if no embeddings exist yet.

## Sequence: What to Implement First

1. **Embedding infrastructure** — compute, store, load embeddings. This unblocks everything else.
2. **Semantic recall (Path A)** — replace keyword search with embedding cosine.
3. **Source task context** — store source_task_title/desc, enable Path B.
4. **LLM rerank** — add rerank prompt and call.
5. **Structured extraction** — context-aware write path with reinforce/update/new.
6. **Consolidation upgrade** — embedding-based clustering.
