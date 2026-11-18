"""Append-only JSONL log of glitch attempts + SQLite query mirror.

JSONL stays canonical. SQLite is rebuildable from the JSONL files.

Carry-forward from old-em-setup/glitchweb/backend/app/logbook.py, extended
with the SQLite index per the new spec.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    session TEXT NOT NULL,
    ts TEXT NOT NULL,
    campaign_id TEXT,
    x REAL, y REAL, z REAL,
    delay_us REAL,
    pulse_width_ns REAL,
    voltage_v INTEGER,
    outcome TEXT NOT NULL,
    build_sha TEXT,
    target_pc INTEGER
);
CREATE INDEX IF NOT EXISTS idx_runs_campaign ON runs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_runs_outcome ON runs(outcome);
CREATE INDEX IF NOT EXISTS idx_runs_xy ON runs(x, y);
CREATE INDEX IF NOT EXISTS idx_runs_xyz ON runs(x, y, z);
"""


class Logbook:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self._sqlite_path = self.log_dir / "index.sqlite"
        self._db_lock = threading.Lock()
        with self._db() as db:
            db.executescript(SQLITE_SCHEMA)
        LOGGER.info("Logbook opened: session=%s dir=%s", self._session_id, self.log_dir)

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._sqlite_path), isolation_level=None)

    def _path_for_today(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.log_dir / f"logbook-{day}.jsonl"

    def add_listener(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        self._listeners.append(fn)

    def append(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        entry = dict(entry)
        entry.setdefault(
            "ts", datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        )
        entry.setdefault("session", self._session_id)

        line = json.dumps(entry, separators=(",", ":")) + "\n"
        with self._lock:
            path = self._path_for_today()
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

        self._mirror_to_sqlite(entry)

        LOGGER.debug("Logbook append: id=%s outcome=%s", entry.get("id"), entry.get("outcome"))
        for fn in list(self._listeners):
            try:
                fn(entry)
            except Exception:
                LOGGER.exception("Logbook listener error")
        return entry

    def _mirror_to_sqlite(self, entry: Dict[str, Any]) -> None:
        with self._db_lock, self._db() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO runs
                (id, session, ts, campaign_id, x, y, z,
                 delay_us, pulse_width_ns, voltage_v, outcome,
                 build_sha, target_pc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.get("id"),
                    entry.get("session"),
                    entry.get("ts"),
                    entry.get("campaign_id"),
                    entry.get("x"),
                    entry.get("y"),
                    entry.get("z"),
                    entry.get("glitch_delay_us"),
                    entry.get("pulse_width_ns"),
                    entry.get("shouter_voltage"),
                    entry.get("outcome"),
                    entry.get("build_sha"),
                    entry.get("target_pc"),
                ),
            )

    def read(
        self,
        since: Optional[str] = None,
        limit: int = 500,
        campaign_id: Optional[str] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        outcome: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for path in sorted(self.log_dir.glob("logbook-*.jsonl"), reverse=True):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if campaign_id and obj.get("campaign_id") != campaign_id:
                    continue
                if x is not None and obj.get("x") != x:
                    continue
                if y is not None and obj.get("y") != y:
                    continue
                if z is not None and obj.get("z") != z:
                    continue
                if outcome and obj.get("outcome") != outcome:
                    continue
                if since and obj.get("ts", "") <= since:
                    continue
                out.append(obj)
                if len(out) >= limit:
                    return list(reversed(out))
        return list(reversed(out))

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        for path in sorted(self.log_dir.glob("logbook-*.jsonl"), reverse=True):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get("id") == run_id:
                        return obj
            except OSError:
                continue
        return None

    # All outcome buckets a cell can report (mirrors emfi_protocol.Outcome).
    _OUTCOMES = ("glitch", "hang", "crash", "nothing", "unobserved")

    def heatmap(
        self,
        campaign_id: Optional[str] = None,
        z: Optional[float] = None,
        outcome: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fault density grouped by (x, y).

        Returns one entry per cell with per-outcome counts so View can
        color-code without re-querying:

            [{"x": 1.0, "y": 2.0,
              "counts": {"glitch": 2, "hang": 5, "crash": 0, "nothing": 8}}]

        ``outcome`` filters to a single bucket only when explicitly set
        (default None = include every outcome). ``campaign_id`` and ``z``
        narrow the rows as before.
        """
        query = "SELECT x, y, outcome, COUNT(*) FROM runs WHERE 1=1"
        params: List[Any] = []
        if outcome is not None:
            query += " AND outcome = ?"
            params.append(outcome)
        if campaign_id:
            query += " AND campaign_id = ?"
            params.append(campaign_id)
        if z is not None:
            query += " AND z = ?"
            params.append(z)
        query += " GROUP BY x, y, outcome"
        with self._db_lock, self._db() as db:
            rows = db.execute(query, params).fetchall()

        cells: Dict[Any, Dict[str, Any]] = {}
        for x, y, oc, count in rows:
            key = (x, y)
            cell = cells.get(key)
            if cell is None:
                cell = {"x": x, "y": y, "counts": {o: 0 for o in self._OUTCOMES}}
                cells[key] = cell
            # Tolerate unexpected/legacy outcome strings by adding the key.
            cell["counts"][oc] = cell["counts"].get(oc, 0) + count
        return list(cells.values())

    def iter_csv_rows(
        self,
        since: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> Iterable[Dict[str, Any]]:
        for path in sorted(self.log_dir.glob("logbook-*.jsonl")):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if outcome and obj.get("outcome") != outcome:
                        continue
                    if since and obj.get("ts", "") <= since:
                        continue
                    yield obj
            except OSError:
                continue


def default_log_dir() -> Path:
    state = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "share"))
    return state / "emfi-control" / "sessions"
