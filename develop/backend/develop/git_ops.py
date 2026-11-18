"""Subprocess git wrapper for per-project repos."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)


class GitError(Exception):
    pass


def _run(args: list[str], repo: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args, cwd=repo, capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error("git %s failed in %s: %s", args[1], repo, result.stderr.strip())
        raise GitError(result.stderr.strip())
    return result


def init(repo: Path) -> None:
    log.info("git init %s", repo)
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "emfi@lab.local"], repo)
    _run(["git", "config", "user.name", "EMFI Develop"], repo)


def commit(repo: Path, message: str) -> str:
    """Stage all changes and commit. Returns the commit SHA."""
    log.info("git commit in %s: %s", repo, message[:80])
    _run(["git", "add", "-A"], repo)

    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo, capture_output=True,
    )
    if result.returncode == 0:
        log.info("Nothing to commit in %s", repo)
        r = _run(["git", "rev-parse", "HEAD"], repo)
        return r.stdout.strip()

    _run(["git", "commit", "-m", message], repo)
    r = _run(["git", "rev-parse", "HEAD"], repo)
    return r.stdout.strip()


def tag(repo: Path, name: str) -> None:
    log.info("git tag %s in %s", name, repo)
    _run(["git", "tag", name], repo)


def list_tags(repo: Path) -> List[str]:
    log.debug("git tag -l in %s", repo)
    r = _run(["git", "tag", "-l", "--sort=-creatordate"], repo)
    return [t for t in r.stdout.strip().split("\n") if t]


def log_entries(repo: Path, limit: int = 50) -> List[dict]:
    log.debug("git log -%d in %s", limit, repo)
    r = _run(
        ["git", "log", f"-{limit}", "--format=%H%x00%s%x00%ci%x00%an"],
        repo,
    )
    entries = []
    for line in r.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        entries.append({
            "sha": parts[0],
            "message": parts[1],
            "date": parts[2],
            "author": parts[3],
        })
    return entries
