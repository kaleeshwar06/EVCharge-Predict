"""Service for deterministically assigning and persisting canonical station IDs."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
import time
from typing import Dict

from app.core.config import get_settings


class StationMappingService:
    """Manages persistent mapping from source station strings to canonical IDs (ST-001, etc.).

    Thread-safe and persistent across repeated imports.
    """

    _lock = Lock()

    def __init__(self, mapping_file: Path | None = None) -> None:
        settings = get_settings()
        self.mapping_file = mapping_file or settings.station_map_file
        self._mapping: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        """Load existing mapping from disk if present."""
        if self.mapping_file.exists():
            for attempt in range(5):
                try:
                    with open(self.mapping_file, "r", encoding="utf-8") as f:
                        self._mapping = json.load(f)
                    return
                except (PermissionError, json.JSONDecodeError):
                    time.sleep(0.02)
                except Exception:
                    self._mapping = {}
                    return
        else:
            self._mapping = {}

    def save(self) -> None:
        """Save the mapping dictionary to disk atomically with retry on Windows file lock."""
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.mapping_file.with_name(f"{self.mapping_file.stem}_{int(time.time()*1000)}.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(self._mapping, f, indent=2, sort_keys=True)

        for attempt in range(10):
            try:
                tmp_file.replace(self.mapping_file)
                return
            except PermissionError:
                time.sleep(0.02)
        # Fallback if replace is held by a Windows scanner
        with open(self.mapping_file, "w", encoding="utf-8") as f:
            json.dump(self._mapping, f, indent=2, sort_keys=True)
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except Exception:
                pass

    def get_or_create(self, source_station_id: str) -> str:
        """Deterministically return canonical ST-xxx ID under a thread lock."""
        clean_source = source_station_id.strip()
        with self._lock:
            self.load()

            if clean_source in self._mapping:
                return self._mapping[clean_source]

            existing_indices = []
            for val in self._mapping.values():
                if val.startswith("ST-"):
                    try:
                        existing_indices.append(int(val.split("-")[1]))
                    except ValueError:
                        pass

            next_index = (max(existing_indices) + 1) if existing_indices else 1
            canonical_id = f"ST-{next_index:03d}"
            self._mapping[clean_source] = canonical_id
            self.save()
            return canonical_id

    def get_all(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._mapping)
