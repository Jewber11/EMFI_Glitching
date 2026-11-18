"""Rebuild the SQLite index from JSONL logbook files.

Usage:
    python -m control.tools.reindex [--data-dir DIR]

Scans all logbook-*.jsonl files under the sessions directory and
rebuilds index.sqlite from scratch.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from control.logbook import SQLITE_SCHEMA, default_log_dir


def reindex(data_dir: Path) -> int:
    if not data_dir.exists():
        print(f"Data dir does not exist: {data_dir}", file=sys.stderr)
        return 1

    db_path = data_dir / "index.sqlite"
    if db_path.exists():
        db_path.unlink()

    db = sqlite3.connect(str(db_path))
    db.executescript(SQLITE_SCHEMA)

    count = 0
    for jsonl in sorted(data_dir.glob("logbook-*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
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
            count += 1

    db.commit()
    db.close()
    print(f"Reindexed {count} entries into {db_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild SQLite index from JSONL logbook files")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Sessions directory (default: ~/.local/share/emfi-control/sessions)",
    )
    args = parser.parse_args()
    data_dir = args.data_dir or default_log_dir()
    sys.exit(reindex(data_dir))


if __name__ == "__main__":
    main()
