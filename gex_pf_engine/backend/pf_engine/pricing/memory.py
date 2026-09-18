"""Project-scoped calibration memory."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any


class ProjectCalibrationMemory:
    """JSON-per-project calibration audit store."""

    def __init__(self, data_dir: str | None = None):
        base = data_dir or os.getenv("PF_ENGINE_DATA_DIR")
        self.data_dir = Path(base or tempfile.gettempdir()) / "gex_pf_engine" / "pricing_memory"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def latest_params(self, project_id: str) -> dict[str, float] | None:
        history = self.history(project_id)
        if not history:
            return None
        return dict(history[-1]["params"])

    def latest_config(self, project_id: str) -> dict[str, Any] | None:
        history = self.history(project_id)
        for record in reversed(history):
            config = record.get("config")
            if isinstance(config, dict):
                return dict(config)
        return None

    def history(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            payload = self._read(project_id)
            return list(payload.get("history", []))

    def append(self, project_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            payload = self._read(project_id)
            row = {"project_id": project_id, **record}
            payload.setdefault("project_id", project_id)
            payload.setdefault("history", []).append(row)
            self._write(project_id, payload)

    def _read(self, project_id: str) -> dict[str, Any]:
        path = self._path(project_id)
        if not path.exists():
            return {"project_id": project_id, "history": []}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"project_id": project_id, "history": []}

    def _write(self, project_id: str, payload: dict[str, Any]) -> None:
        path = self._path(project_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(path)

    def _path(self, project_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", project_id).strip("._") or "default"
        return self.data_dir / f"{safe}.json"
