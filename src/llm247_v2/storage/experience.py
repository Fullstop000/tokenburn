"""Experience module — the agent's long-term memory.

Captures what the agent learned from each task (success or failure),
stores it persistently, retrieves relevant past experiences for future
planning, and periodically consolidates overlapping learnings.

Design:
- SQLite table in the same DB as TaskStore for transactional consistency
- Each experience has: category, summary, tags for retrieval
- ``search()`` does keyword matching; no vector DB dependency
- ``consolidate()`` uses LLM to merge similar experiences
- ``to_prompt_section()`` renders relevant experiences for planning prompts
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from llm247_v2.llm.prompts import render as render_prompt

logger = logging.getLogger("llm247_v2.storage.experience")

_EXP_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiences (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'insight',
    summary TEXT NOT NULL,
    detail TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    confidence REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    applied_count INTEGER DEFAULT 0,
    source_outcome TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_exp_category ON experiences(category);
CREATE INDEX IF NOT EXISTS idx_exp_tags ON experiences(tags);
"""


@dataclass
class Experience:
    id: str
    task_id: str
    category: str
    summary: str
    detail: str = ""
    tags: str = ""
    confidence: float = 0.5
    created_at: str = ""
    applied_count: int = 0
    source_outcome: str = ""


class ExperienceStore:
    """SQLite-backed store for agent experiences / learnings."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_EXP_SCHEMA)
        self._conn.commit()

    # ── Write ──

    def add(self, exp: Experience) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """INSERT OR IGNORE INTO experiences
                   (id, task_id, category, summary, detail, tags,
                    confidence, created_at, applied_count, source_outcome)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    exp.id, exp.task_id, exp.category, exp.summary,
                    exp.detail, exp.tags, exp.confidence,
                    exp.created_at or now, exp.applied_count,
                    exp.source_outcome,
                ),
            )
            self._conn.commit()

    def add_batch(self, exps: List[Experience]) -> int:
        added = 0
        for exp in exps:
            before = self._conn.total_changes
            self.add(exp)
            if self._conn.total_changes > before:
                added += 1
        return added

    def increment_applied(self, exp_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE experiences SET applied_count = applied_count + 1 WHERE id = ?",
                (exp_id,),
            )
            self._conn.commit()

    # ── Read ──

    def get(self, exp_id: str) -> Optional[Experience]:
        row = self._conn.execute("SELECT * FROM experiences WHERE id=?", (exp_id,)).fetchone()
        return _row_to_exp(row) if row else None

    def get_recent(self, limit: int = 20) -> List[Experience]:
        rows = self._conn.execute(
            "SELECT * FROM experiences ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_exp(r) for r in rows]

    def get_by_category(self, category: str, limit: int = 20) -> List[Experience]:
        rows = self._conn.execute(
            "SELECT * FROM experiences WHERE category=? ORDER BY confidence DESC, created_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()
        return [_row_to_exp(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> List[Experience]:
        """Keyword-based search across summary, detail, and tags."""
        keywords = [w.strip().lower() for w in query.split() if len(w.strip()) >= 2]
        if not keywords:
            return self.get_recent(limit)

        conditions = []
        params: list = []
        for kw in keywords[:5]:
            conditions.append(
                "(LOWER(summary) LIKE ? OR LOWER(detail) LIKE ? OR LOWER(tags) LIKE ?)"
            )
            pattern = f"%{kw}%"
            params.extend([pattern, pattern, pattern])

        where = " OR ".join(conditions)
        sql = f"SELECT * FROM experiences WHERE {where} ORDER BY confidence DESC, applied_count DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_exp(r) for r in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM experiences").fetchone()
        return row["cnt"] if row else 0

    def stats(self) -> Dict:
        categories: Dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT category, COUNT(*) as cnt FROM experiences GROUP BY category"
        ).fetchall():
            categories[row["category"]] = row["cnt"]
        return {
            "total": sum(categories.values()),
            "categories": categories,
        }

    # ── Organize ──

    def remove_low_confidence(self, threshold: float = 0.2) -> int:
        """Prune experiences below confidence threshold that were never applied."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM experiences WHERE confidence < ? AND applied_count = 0",
                (threshold,),
            )
            self._conn.commit()
            return cursor.rowcount

    def deduplicate(self) -> int:
        """Remove exact-summary duplicates, keeping highest confidence."""
        rows = self._conn.execute(
            """SELECT summary, COUNT(*) as cnt FROM experiences
               GROUP BY summary HAVING cnt > 1"""
        ).fetchall()

        removed = 0
        for row in rows:
            dups = self._conn.execute(
                "SELECT id, confidence FROM experiences WHERE summary=? ORDER BY confidence DESC",
                (row["summary"],),
            ).fetchall()
            ids_to_remove = [d["id"] for d in dups[1:]]
            for eid in ids_to_remove:
                self._conn.execute("DELETE FROM experiences WHERE id=?", (eid,))
                removed += 1

        if removed:
            self._conn.commit()
        return removed

    def consolidate(self, llm_generate=None, extract_json_fn=None, max_cluster_size: int = 5) -> int:
        """Merge similar experiences and decay low-value ones.

        Three-phase process:
        1. Exact-summary dedup (cheap, always runs)
        2. Confidence decay on old, never-applied experiences
        3. LLM-powered semantic merge of similar experiences (if LLM provided)
        """
        merged = 0

        merged += self.deduplicate()

        merged += self._decay_stale_experiences()

        merged += self.remove_low_confidence(threshold=0.15)

        if llm_generate and extract_json_fn:
            merged += self._llm_merge_similar(llm_generate, extract_json_fn, max_cluster_size)

        return merged

    def _decay_stale_experiences(self, age_days: int = 30, decay_factor: float = 0.9) -> int:
        """Reduce confidence of old experiences that were never applied."""
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE experiences
                   SET confidence = confidence * ?
                   WHERE created_at < ? AND applied_count = 0 AND confidence > 0.15""",
                (decay_factor, cutoff),
            )
            self._conn.commit()
            return cursor.rowcount

    def _llm_merge_similar(self, llm_generate, extract_json_fn, max_cluster_size: int) -> int:
        """Use LLM to merge experiences with similar summaries into higher-quality entries."""
        all_exps = self.get_recent(limit=100)
        if len(all_exps) < 4:
            return 0

        clusters: dict[str, list[Experience]] = {}
        for exp in all_exps:
            key_words = sorted(set(exp.summary.lower().split()))[:3]
            cluster_key = " ".join(key_words)
            clusters.setdefault(cluster_key, []).append(exp)

        merged_count = 0
        for cluster_key, cluster in clusters.items():
            if len(cluster) < 2 or len(cluster) > max_cluster_size:
                continue

            summaries = "\n".join(f"- [{e.category}] {e.summary}" for e in cluster)
            prompt = (
                "You are consolidating an agent's experience memory.\n"
                "Merge these similar learnings into ONE better learning.\n\n"
                f"## Learnings to merge\n{summaries}\n\n"
                "## Output (strict JSON)\n"
                '{"summary": "merged one-sentence takeaway", '
                '"detail": "supporting explanation", '
                '"category": "pattern|pitfall|insight|technique", '
                '"confidence": 0.8}'
            )

            try:
                raw = llm_generate(prompt)
                parsed = extract_json_fn(raw)
                if not parsed or "summary" not in parsed:
                    continue

                best = max(cluster, key=lambda e: e.confidence)
                new_id = hashlib.sha256(f"merged:{parsed['summary']}".encode()).hexdigest()[:12]
                merged_exp = Experience(
                    id=new_id,
                    task_id=best.task_id,
                    category=str(parsed.get("category", best.category)),
                    summary=str(parsed["summary"]),
                    detail=str(parsed.get("detail", "")),
                    tags=best.tags,
                    confidence=min(1.0, max(0.0, float(parsed.get("confidence", 0.8)))),
                    source_outcome=best.source_outcome,
                )

                with self._lock:
                    for exp in cluster:
                        self._conn.execute("DELETE FROM experiences WHERE id=?", (exp.id,))
                    self._conn.commit()

                self.add(merged_exp)
                merged_count += len(cluster) - 1

            except Exception:
                logger.debug("LLM merge failed for cluster %s", cluster_key, exc_info=True)
                continue

        return merged_count

    def close(self) -> None:
        self._conn.close()


def _row_to_exp(row: sqlite3.Row) -> Experience:
    d = dict(row)
    return Experience(
        id=d["id"],
        task_id=d["task_id"],
        category=d["category"],
        summary=d["summary"],
        detail=d.get("detail", ""),
        tags=d.get("tags", ""),
        confidence=d.get("confidence", 0.5),
        created_at=d.get("created_at", ""),
        applied_count=d.get("applied_count", 0),
        source_outcome=d.get("source_outcome", ""),
    )


# ── Experience extraction (LLM-powered) ──

def extract_learnings(
    task_title: str,
    task_source: str,
    task_id: str,
    execution_log: str,
    verification_result: str,
    error_message: str,
    outcome: str,
    llm_generate,
    extract_json_fn,
) -> List[Experience]:
    """Ask LLM to reflect on a completed/failed task and extract learnings."""
    outcome_label = "succeeded" if outcome == "completed" else "failed"

    prompt = render_prompt(
        "extract_learnings",
        outcome_label=outcome_label,
        task_title=task_title,
        task_source=task_source,
        execution_log=execution_log[:2000],
        verification_section=f"## Verification Result\n{verification_result[:500]}" if verification_result else "",
        error_section=f"## Error Details\n{error_message[:500]}" if error_message else "",
    )

    try:
        raw = llm_generate(prompt)
    except Exception:
        logger.exception("Failed to extract learnings for task %s", task_id)
        return []

    parsed = extract_json_fn(raw)
    if not parsed or not isinstance(parsed.get("learnings"), list):
        return []

    results: List[Experience] = []
    for item in parsed["learnings"][:3]:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary", "")).strip()
        if not summary:
            continue

        exp_id = hashlib.sha256(f"{task_id}:{summary}".encode()).hexdigest()[:12]
        results.append(Experience(
            id=exp_id,
            task_id=task_id,
            category=str(item.get("category", "insight")),
            summary=summary,
            detail=str(item.get("detail", "")),
            tags=str(item.get("tags", "")),
            confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
            source_outcome=outcome,
        ))

    return results


def format_experiences_for_prompt(experiences: List[Experience], max_items: int = 5) -> str:
    """Render past experiences as context for LLM planning prompts."""
    if not experiences:
        return ""

    lines = ["## Past Experiences (lessons from previous tasks)"]
    for exp in experiences[:max_items]:
        icon = {"pattern": "✅", "pitfall": "⚠️", "insight": "💡", "technique": "🔧"}.get(exp.category, "📝")
        lines.append(f"- {icon} [{exp.category}] {exp.summary}")
        if exp.detail:
            lines.append(f"  {exp.detail[:150]}")
    return "\n".join(lines)


def format_whats_learned(experiences: List[Experience]) -> str:
    """Format learnings for storing in task.whats_learned field."""
    if not experiences:
        return ""
    return "\n".join(
        f"[{e.category}] {e.summary}" + (f" — {e.detail[:100]}" if e.detail else "")
        for e in experiences
    )
