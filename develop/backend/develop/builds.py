"""Firmware build pipeline.

Reads project.toml to determine language, then invokes the right toolchain:
- language=c   →  `make all` in the project root
- language=rust → `cargo build --release --target thumbv6m-none-eabi`

Produces builds/<sha>/ with elf, bin, lst, symbols.json, build.log.
The SHA is computed from source-tree + toolchain versions for determinism.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shlex
import shutil
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, List, Optional

from emfi_protocol.projects import BuildArtifact
from emfi_protocol.ws_events import WsTopic

from develop.broadcaster import broadcaster
from develop.config import arm_gcc_bin, arm_objcopy_bin, arm_objdump_bin, cargo_bin
from develop.projects import project_dir

log = logging.getLogger(__name__)


class ToolchainNotFoundError(Exception):
    pass


def _read_project_toml(proj_dir: Path) -> dict:
    toml_path = proj_dir / "project.toml"
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _read_language(proj_dir: Path) -> str:
    return _read_project_toml(proj_dir).get("language", "c")


def _toolchain_version(binary: str) -> str:
    try:
        r = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip()[:200]
    except FileNotFoundError:
        return "not-found"


_SHA_INCLUDE_SUFFIXES = frozenset({
    ".c", ".h", ".cpp", ".hpp", ".s", ".S", ".asm",
    ".rs", ".ld", ".x", ".syscfg",
})

_SHA_INCLUDE_BASENAMES = frozenset({
    "Makefile", "makefile", "Cargo.toml", "Cargo.lock",
    "linker.ld", "project.toml", ".cproject", "config.toml",
})

_SHA_SKIP_DIRS = frozenset({
    ".git", "builds", "Debug", ".settings", ".clangd",
    "__pycache__", "node_modules", ".svelte-kit", "target", "host",
})


def compute_sha(proj_dir: Path) -> str:
    """Deterministic hash of (source files + toolchain versions).

    Layout-agnostic: hashes any file whose suffix or basename matches
    the include sets, skipping build-output and metadata directories.
    """
    h = hashlib.sha256()

    for f in sorted(proj_dir.rglob("*")):
        if not f.is_file():
            continue

        rel = f.relative_to(proj_dir)
        if any(part in _SHA_SKIP_DIRS for part in rel.parts):
            continue

        if f.suffix in _SHA_INCLUDE_SUFFIXES or f.name in _SHA_INCLUDE_BASENAMES:
            h.update(str(rel).encode())
            h.update(f.read_bytes())

    lang = _read_language(proj_dir)
    if lang == "c":
        h.update(_toolchain_version(arm_gcc_bin()).encode())
    else:
        h.update(_toolchain_version(cargo_bin()).encode())

    return h.hexdigest()[:12]


def list_build_artifacts(project_id: str) -> List[BuildArtifact]:
    builds_dir = project_dir(project_id) / "builds"
    if not builds_dir.exists():
        return []
    artifacts = []
    for entry in sorted(builds_dir.iterdir(), reverse=True):
        meta_path = entry / "build_meta.json"
        if meta_path.exists():
            try:
                artifacts.append(BuildArtifact(**json.loads(meta_path.read_text())))
            except Exception as e:
                log.warning("Skipping build %s: %s", entry.name, e)
    return artifacts


def get_build_artifact(project_id: str, sha: str) -> Optional[BuildArtifact]:
    build_dir = project_dir(project_id) / "builds" / sha
    meta_path = build_dir / "build_meta.json"
    if not meta_path.exists():
        return None
    return BuildArtifact(**json.loads(meta_path.read_text()))


async def build(project_id: str, version: str | None = None, force: bool = False) -> BuildArtifact:
    """Run the project's build and capture artifacts."""
    proj_path = project_dir(project_id)
    if not proj_path.exists():
        raise FileNotFoundError(f"Project {project_id!r} not found")

    toml_data = _read_project_toml(proj_path)
    lang = toml_data.get("language", "c")
    custom_cmd = toml_data.get("build_command")
    sha = compute_sha(proj_path)

    build_dir = proj_path / "builds" / sha
    meta_path = build_dir / "build_meta.json"
    if meta_path.exists():
        cached = BuildArtifact(**json.loads(meta_path.read_text()))
        if cached.success and not force:
            log.info("Build %s already cached (success) for project=%s", sha, project_id)
            await broadcaster.broadcast(WsTopic.BUILD_STATUS, {
                "project_id": project_id, "sha": sha, "phase": "done",
            })
            return cached

    log.info("Starting build for project=%s lang=%s sha=%s", project_id, lang, sha)
    await broadcaster.broadcast(WsTopic.BUILD_STATUS, {
        "project_id": project_id, "sha": sha, "phase": "starting",
    })

    if custom_cmd:
        cmd = shlex.split(custom_cmd)
    elif lang == "c":
        if not shutil.which(arm_gcc_bin()):
            raise ToolchainNotFoundError(
                f"{arm_gcc_bin()} not found on PATH. "
                "Install: apt install gcc-arm-none-eabi"
            )
        cmd = ["make", "all"]
    elif lang == "rust":
        if not shutil.which(cargo_bin()):
            raise ToolchainNotFoundError(
                f"{cargo_bin()} not found on PATH. "
                "Install: rustup + rustup target add thumbv6m-none-eabi"
            )
        cmd = [cargo_bin(), "build", "--release", "--target", "thumbv6m-none-eabi"]
    else:
        raise ValueError(f"Unknown language: {lang}")
    # Phase 2: TI CCS headless eclipse build (eclipse -application
    # org.eclipse.cdt.managedbuilder.core.headlessbuild) — not needed
    # yet; `make -C Debug` via build_command covers CCS projects for V1.

    await broadcaster.broadcast(WsTopic.BUILD_STATUS, {
        "project_id": project_id, "sha": sha, "phase": "compiling",
    })

    log_lines: list[str] = []
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(proj_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
        log_lines.append(line)
        await broadcaster.broadcast(WsTopic.BUILD_LOG, {
            "project_id": project_id, "sha": sha, "line": line,
        })

    await proc.wait()
    success = proc.returncode == 0

    build_dir.mkdir(parents=True, exist_ok=True)

    (build_dir / "build.log").write_text("\n".join(log_lines) + "\n")

    if success:
        await broadcaster.broadcast(WsTopic.BUILD_STATUS, {
            "project_id": project_id, "sha": sha, "phase": "linking",
        })
        artifact_elf = toml_data.get("artifact_elf")
        collected = _collect_artifacts(proj_path, build_dir, lang, project_id, artifact_elf)
        if not collected:
            success = False
            msg = (
                f"Build command succeeded but expected artifact not found: "
                f"{artifact_elf or _default_artifact_elf(lang, project_id)}. "
                f"Check project.toml's artifact_elf or the build_command output paths."
            )
            log_lines.append(msg)
            (build_dir / "build.log").write_text("\n".join(log_lines) + "\n")

    phase = "done" if success else "failed"
    await broadcaster.broadcast(WsTopic.BUILD_STATUS, {
        "project_id": project_id, "sha": sha, "phase": phase,
    })

    host_src = proj_path / "host" / "run.py"
    host_dest = build_dir / "host_script.py"
    if host_src.exists():
        shutil.copy2(host_src, host_dest)

    artifact = BuildArtifact(
        project_id=project_id,
        version=version,
        sha=sha,
        built_at=datetime.now(timezone.utc),
        elf_path=str(build_dir / "firmware.elf"),
        bin_path=str(build_dir / "firmware.bin"),
        listing_path=str(build_dir / "firmware.lst"),
        symbols_path=str(build_dir / "symbols.json"),
        success=success,
        log_tail="\n".join(log_lines[-20:]) if log_lines else None,
        host_script_path=str(host_dest) if host_dest.exists() else None,
    )
    meta_path.write_text(artifact.model_dump_json(indent=2))

    log.info("Build %s for project=%s: %s", sha, project_id, phase)
    return artifact


def _default_artifact_elf(lang: str, project_id: str) -> str:
    if lang == "rust":
        return f"target/thumbv6m-none-eabi/release/{project_id}"
    return "firmware.elf"


def _collect_artifacts(
    proj_path: Path, build_dir: Path, lang: str,
    project_id: str, artifact_elf: str | None,
) -> bool:
    """Copy build outputs into builds/<sha>/. Returns True if the ELF was found."""
    if lang == "rust" and not artifact_elf and (proj_path / "Cargo.toml").is_file():
        with (proj_path / "Cargo.toml").open("rb") as cargo_file:
            package = tomllib.load(cargo_file).get("package", {}).get("name", project_id)
        elf_rel = _default_artifact_elf(lang, package)
    else:
        elf_rel = artifact_elf or _default_artifact_elf(lang, project_id)
    elf_src = proj_path / elf_rel

    if not elf_src.exists():
        log.warning("Expected artifact %s not found in %s", elf_rel, proj_path)
        (build_dir / "symbols.json").write_text("[]")
        return False

    log.info("Collecting artifact %s -> firmware.elf", elf_rel)
    shutil.copy2(elf_src, build_dir / "firmware.elf")

    elf_dest = build_dir / "firmware.elf"

    objcopy = arm_objcopy_bin()
    if shutil.which(objcopy):
        subprocess.run(
            [objcopy, "-O", "binary", str(elf_dest), str(build_dir / "firmware.bin")],
            check=False,
        )

    objdump = arm_objdump_bin()
    if shutil.which(objdump):
        result = subprocess.run(
            [objdump, "-d", "-S", str(elf_dest)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            (build_dir / "firmware.lst").write_text(result.stdout)

    (build_dir / "symbols.json").write_text("[]")
    # TODO: make_clean_first flag — run `make -C Debug clean` before build
    # for CCS projects that want reproducible from-scratch rebuilds.
    return True


async def stream_build_log(project_id: str, sha: str) -> AsyncIterator[str]:
    log_file = project_dir(project_id) / "builds" / sha / "build.log"
    if not log_file.exists():
        return
    for line in log_file.read_text().splitlines():
        yield line
