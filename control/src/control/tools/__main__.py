"""Allow `python -m control.tools` to list available tools."""

from __future__ import annotations

import sys

print("Available tools:", file=sys.stderr)
print("  python -m control.tools.reindex  — rebuild SQLite index from JSONL", file=sys.stderr)
