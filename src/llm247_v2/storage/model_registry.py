from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from llm247_v2.core.models import (
    ModelBinding,
    ModelBindingPoint,
    ModelBindingSpec,
    ModelType,
    RegisteredModel,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS registered_models (
    id TEXT PRIMARY KEY,
    model_type TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_path TEXT DEFAULT '',
    model_name TEXT NOT NULL,
    api_key TEXT NOT NULL,
    desc TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_bindings (
    binding_point TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(model_id) REFERENCES registered_models(id)
);

CREATE INDEX IF NOT EXISTS idx_registered_models_type ON registered_models(model_type);
"""

_MIGRATIONS = [
    "ALTER TABLE registered_models ADD COLUMN desc TEXT DEFAULT ''",
    "ALTER TABLE registered_models ADD COLUMN api_path TEXT DEFAULT ''",
    "ALTER TABLE registered_models ADD COLUMN roocode_wrapper INTEGER DEFAULT 0",
]


MODEL_BINDING_SPECS = (
    ModelBindingSpec(
        binding_point=ModelBindingPoint.EXECUTION.value,
        label="Execution",
        description="ReAct tool-calling loop for autonomous task execution.",
        model_type=ModelType.LLM.value,
    ),
    ModelBindingSpec(
        binding_point=ModelBindingPoint.TASK_VALUE.value,
        label="Task Value",
        description="LLM scoring used to rank discovery candidates.",
        model_type=ModelType.LLM.value,
    ),
    ModelBindingSpec(
        binding_point=ModelBindingPoint.DISCOVERY_GENERATION.value,
        label="Discovery Generation",
        description="Stale-area, deep-review, and guided discovery generation.",
        model_type=ModelType.LLM.value,
    ),
    ModelBindingSpec(
        binding_point=ModelBindingPoint.INTEREST_DRIVEN_DISCOVERY.value,
        label="Interest Discovery",
        description="Interest-driven task generation.",
        model_type=ModelType.LLM.value,
    ),
    ModelBindingSpec(
        binding_point=ModelBindingPoint.WEB_SEARCH_DISCOVERY.value,
        label="Web Search Discovery",
        description="LLM-based web-style issue discovery.",
        model_type=ModelType.LLM.value,
    ),
    ModelBindingSpec(
        binding_point=ModelBindingPoint.LEARNING_EXTRACTION.value,
        label="Learning Extraction",
        description="Reflection after task completion or failure.",
        model_type=ModelType.LLM.value,
    ),
    ModelBindingSpec(
        binding_point=ModelBindingPoint.EXPERIENCE_MERGE.value,
        label="Experience Merge",
        description="Experience consolidation across similar learnings.",
        model_type=ModelType.LLM.value,
    ),
)

_BINDING_SPEC_MAP = {spec.binding_point: spec for spec in MODEL_BINDING_SPECS}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_model_fields(
    *,
    model_type: str,
    base_url: str = "",
    api_path: str = "",
    model_name: str,
    api_key: str,
    desc: str = "",
    roocode_wrapper: bool = False,
) -> tuple[str, str, str, str, str, str, bool]:
    """Validate one model payload and return normalized persistence fields."""
    clean_type = str(model_type).strip().lower()
    if clean_type not in {item.value for item in ModelType}:
        raise ValueError(f"unsupported model_type: {model_type}")

    clean_base_url = str(base_url).strip()
    clean_api_path = str(api_path).strip()
    clean_model_name = str(model_name).strip()
    clean_api_key = str(api_key).strip()
    clean_desc = str(desc).strip()

    if not clean_model_name or not clean_api_key:
        raise ValueError("model_name and api_key are required")

    if clean_type == ModelType.LLM.value and not clean_base_url:
        raise ValueError("base_url is required for llm models")
    if clean_type == ModelType.EMBEDDING.value and not clean_api_path:
        raise ValueError("api_path is required for embedding models")
    if clean_type == ModelType.LLM.value:
        clean_api_path = ""
    if clean_type == ModelType.EMBEDDING.value:
        clean_base_url = ""

    return clean_type, clean_base_url, clean_api_path, clean_model_name, clean_api_key, clean_desc, bool(roocode_wrapper)


def _row_to_registered_model(row: sqlite3.Row) -> RegisteredModel:
    """Convert one SQLite row into a registered model record."""
    data = dict(row)
    model_type = data["model_type"]
    api_path = data.get("api_path", "") or ""
    if model_type == ModelType.EMBEDDING.value and not api_path:
        # Backward compatibility for early embedding rows stored in base_url.
        api_path = data["base_url"]
    return RegisteredModel(
        id=data["id"],
        model_type=model_type,
        base_url=data["base_url"],
        api_path=api_path,
        model_name=data["model_name"],
        api_key=data["api_key"],
        desc=data.get("desc", "") or "",
        roocode_wrapper=bool(data.get("roocode_wrapper", 0)),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def _row_to_binding(row: sqlite3.Row) -> ModelBinding:
    """Convert one SQLite row into a model binding record."""
    data = dict(row)
    return ModelBinding(
        binding_point=data["binding_point"],
        model_id=data["model_id"],
        updated_at=data["updated_at"],
    )


class ModelRegistryStore:
    """SQLite-backed registry for models and runtime binding selections."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._run_migrations()

    def _run_migrations(self) -> None:
        """Apply additive schema updates for existing runtime databases."""
        for sql in _MIGRATIONS:
            try:
                self._conn.execute(sql)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass

    def register_model(
        self,
        *,
        model_type: str,
        base_url: str = "",
        api_path: str = "",
        model_name: str,
        api_key: str,
        desc: str = "",
        roocode_wrapper: bool = False,
    ) -> RegisteredModel:
        """Persist one registered model and return the stored record."""
        clean_type, clean_base_url, clean_api_path, clean_model_name, clean_api_key, clean_desc, clean_roocode_wrapper = _normalize_model_fields(
            model_type=model_type,
            base_url=base_url,
            api_path=api_path,
            model_name=model_name,
            api_key=api_key,
            desc=desc,
            roocode_wrapper=roocode_wrapper,
        )

        now = _now_iso()
        endpoint = clean_base_url or clean_api_path
        model_id = hashlib.sha256(f"{clean_type}:{endpoint}:{clean_model_name}:{now}".encode("utf-8")).hexdigest()[:12]
        record = RegisteredModel(
            id=model_id,
            model_type=clean_type,
            model_name=clean_model_name,
            api_key=clean_api_key,
            base_url=clean_base_url,
            api_path=clean_api_path,
            desc=clean_desc,
            roocode_wrapper=clean_roocode_wrapper,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._conn.execute(
                """INSERT INTO registered_models
                   (id, model_type, base_url, api_path, model_name, api_key, desc, roocode_wrapper, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.model_type,
                    record.base_url,
                    record.api_path,
                    record.model_name,
                    record.api_key,
                    record.desc,
                    int(record.roocode_wrapper),
                    record.created_at,
                    record.updated_at,
                ),
            )
            self._conn.commit()
        return record

    def update_model(
        self,
        model_id: str,
        *,
        model_type: str,
        base_url: str = "",
        api_path: str = "",
        model_name: str,
        api_key: str,
        desc: str = "",
        roocode_wrapper: bool = False,
    ) -> RegisteredModel:
        """Update one registered model and return the latest stored record."""
        clean_model_id = str(model_id).strip()
        if not clean_model_id:
            raise ValueError("model_id is required")

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM registered_models WHERE id=?",
                (clean_model_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"unknown model_id: {model_id}")

            existing = _row_to_registered_model(row)
            next_api_key = str(api_key).strip() or existing.api_key
            clean_type, clean_base_url, clean_api_path, clean_model_name, clean_api_key, clean_desc, clean_roocode_wrapper = _normalize_model_fields(
                model_type=model_type,
                base_url=base_url,
                api_path=api_path,
                model_name=model_name,
                api_key=next_api_key,
                desc=desc,
                roocode_wrapper=roocode_wrapper,
            )

            binding_rows = self._conn.execute(
                "SELECT binding_point FROM model_bindings WHERE model_id=?",
                (clean_model_id,),
            ).fetchall()
            for binding_row in binding_rows:
                binding_point = str(binding_row["binding_point"])
                expected_type = _BINDING_SPEC_MAP[binding_point].model_type
                if clean_type != expected_type:
                    raise ValueError(
                        f"cannot change model_type for bound model; {binding_point} requires {expected_type}"
                    )

            updated_at = _now_iso()
            self._conn.execute(
                """UPDATE registered_models
                   SET model_type=?, base_url=?, api_path=?, model_name=?, api_key=?, desc=?, roocode_wrapper=?, updated_at=?
                   WHERE id=?""",
                (
                    clean_type,
                    clean_base_url,
                    clean_api_path,
                    clean_model_name,
                    clean_api_key,
                    clean_desc,
                    int(clean_roocode_wrapper),
                    updated_at,
                    clean_model_id,
                ),
            )
            self._conn.commit()

            return RegisteredModel(
                id=existing.id,
                model_type=clean_type,
                model_name=clean_model_name,
                api_key=clean_api_key,
                base_url=clean_base_url,
                api_path=clean_api_path,
                desc=clean_desc,
                roocode_wrapper=clean_roocode_wrapper,
                created_at=existing.created_at,
                updated_at=updated_at,
            )

    def delete_model(self, model_id: str) -> None:
        """Delete one registered model and clear bindings that pointed to it."""
        clean_model_id = str(model_id).strip()
        if not clean_model_id:
            raise ValueError("model_id is required")

        with self._lock:
            deleted = self._conn.execute(
                "DELETE FROM registered_models WHERE id=?",
                (clean_model_id,),
            ).rowcount
            if deleted == 0:
                raise ValueError(f"unknown model_id: {model_id}")
            self._conn.execute(
                "DELETE FROM model_bindings WHERE model_id=?",
                (clean_model_id,),
            )
            self._conn.commit()

    def list_models(self, *, model_type: str = "") -> list[RegisteredModel]:
        """List registered models, optionally filtered by model type."""
        with self._lock:
            if model_type:
                rows = self._conn.execute(
                    """SELECT * FROM registered_models
                       WHERE model_type=?
                       ORDER BY created_at DESC""",
                    (model_type,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM registered_models ORDER BY created_at DESC"
                ).fetchall()
        return [_row_to_registered_model(row) for row in rows]

    def get_model(self, model_id: str) -> Optional[RegisteredModel]:
        """Fetch one registered model by id."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM registered_models WHERE id=?",
                (model_id,),
            ).fetchone()
        return _row_to_registered_model(row) if row else None

    def get_default_model(self, model_type: str = ModelType.LLM.value) -> Optional[RegisteredModel]:
        """Return the latest registered model for one type."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM registered_models
                   WHERE model_type=?
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (model_type,),
            ).fetchone()
        return _row_to_registered_model(row) if row else None

    def set_binding(self, binding_point: str, model_id: str) -> None:
        """Bind one runtime point to a model, or clear it when model_id is empty."""
        clean_point = str(binding_point).strip()
        if clean_point not in _BINDING_SPEC_MAP:
            raise ValueError(f"unsupported binding_point: {binding_point}")

        clean_model_id = str(model_id).strip()
        with self._lock:
            if not clean_model_id:
                self._conn.execute("DELETE FROM model_bindings WHERE binding_point=?", (clean_point,))
                self._conn.commit()
                return

            model = self._conn.execute(
                "SELECT * FROM registered_models WHERE id=?",
                (clean_model_id,),
            ).fetchone()
            if not model:
                raise ValueError(f"unknown model_id: {model_id}")

            expected_type = _BINDING_SPEC_MAP[clean_point].model_type
            actual_type = str(model["model_type"])
            if actual_type != expected_type:
                raise ValueError(f"binding_point {binding_point} requires model_type {expected_type}")

            self._conn.execute(
                """INSERT INTO model_bindings (binding_point, model_id, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(binding_point) DO UPDATE SET
                     model_id=excluded.model_id,
                     updated_at=excluded.updated_at""",
                (clean_point, clean_model_id, _now_iso()),
            )
            self._conn.commit()

    def get_binding(self, binding_point: str) -> Optional[ModelBinding]:
        """Fetch one binding by point name."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM model_bindings WHERE binding_point=?",
                (binding_point,),
            ).fetchone()
        return _row_to_binding(row) if row else None

    def list_bindings(self) -> dict[str, ModelBinding]:
        """Return all persisted bindings keyed by binding point."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM model_bindings ORDER BY binding_point ASC"
            ).fetchall()
        bindings = [_row_to_binding(row) for row in rows]
        return {binding.binding_point: binding for binding in bindings}

    def close(self) -> None:
        self._conn.close()
