"""Versioned artifact persistence for Refract v2."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ArtifactStoreError(ValueError):
    pass


class V2ArtifactStore:
    """Persist schema-versioned JSON beside existing processed entries.

    Layout:
        processed/<entry_id>/v2/analysis.json
        processed/<entry_id>/v2/edit-plan.json
        processed/<entry_id>/v2/candidates/<candidate_id>.json
        processed/<entry_id>/v2/judgment.json
    """

    def __init__(self, repo_root: Path | str) -> None:
        self.repo_root = Path(repo_root)
        self.processed_root = self.repo_root / "processed"

    def _safe_component(self, value: str, label: str) -> str:
        if not _SAFE_NAME.fullmatch(value):
            raise ArtifactStoreError(f"Unsafe {label}: {value!r}")
        return value

    def entry_root(self, entry_id: str) -> Path:
        entry_id = self._safe_component(entry_id, "entry_id")
        return self.processed_root / entry_id / "v2"

    def artifact_path(self, entry_id: str, artifact_name: str) -> Path:
        artifact_name = self._safe_component(artifact_name, "artifact_name")
        return self.entry_root(entry_id) / f"{artifact_name}.json"

    def candidate_path(self, entry_id: str, candidate_id: str) -> Path:
        candidate_id = self._safe_component(candidate_id, "candidate_id")
        return self.entry_root(entry_id) / "candidates" / f"{candidate_id}.json"

    def write_model(
        self,
        entry_id: str,
        artifact_name: str,
        model: BaseModel,
    ) -> Path:
        return self.write_json(
            self.artifact_path(entry_id, artifact_name),
            model.model_dump(mode="json"),
        )

    def write_candidate(self, entry_id: str, candidate_id: str, model: BaseModel) -> Path:
        return self.write_json(
            self.candidate_path(entry_id, candidate_id),
            model.model_dump(mode="json"),
        )

    def write_json(self, path: Path, data: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

        return path

    def read_model(self, path: Path, model_type: type[T]) -> T:
        with path.open("r", encoding="utf-8") as handle:
            return model_type.model_validate(json.load(handle))
