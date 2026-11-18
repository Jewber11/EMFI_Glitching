"""Disassembly: arm-none-eabi-objdump -d → AssemblyListing.

Parser strategy:
1. Run `arm-none-eabi-objdump -d -S <elf>` and capture stdout.
2. Parse the output line-by-line:
   - Function header: `00001234 <function_name>:`
   - Instruction line: `    1234: aabb  mnemonic operands`
   - Source line (with -S): `path/to/file.c:42`
3. Optionally cross-reference with `pyelftools` for symbol info, or
   `capstone` for richer per-instruction metadata.

Output is an `emfi_protocol.AssemblyListing`.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from emfi_protocol.projects import AssemblyInstruction, AssemblyListing

from develop.config import arm_objdump_bin

log = logging.getLogger(__name__)

FUNC_RE = re.compile(r"^([0-9a-f]+)\s+<(.+)>:\s*$")
INST_RE = re.compile(r"^\s+([0-9a-f]+):\s+([0-9a-f ]+?)\s{2,}(\w[\w.]*)\s*(.*)")
SOURCE_RE = re.compile(r"^(/?\S+\.(?:c|h|rs|s|S|ld)):(\d+)")


class DisassemblyError(Exception):
    pass


def disassemble(elf_path: Path, project_id: str, build_sha: str) -> AssemblyListing:
    """Parse objdump output into an AssemblyListing."""
    log.info("Disassembling %s (project=%s sha=%s)", elf_path, project_id, build_sha)

    if not elf_path.exists():
        raise FileNotFoundError(f"ELF not found: {elf_path}")

    objdump = arm_objdump_bin()
    if not shutil.which(objdump):
        raise DisassemblyError(
            f"{objdump} not found on PATH. Install: apt install binutils-arm-none-eabi"
        )

    result = subprocess.run(
        [objdump, "-d", "-S", str(elf_path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise DisassemblyError(f"objdump failed: {result.stderr[:500]}")

    instructions = _parse_objdump(result.stdout)
    log.info("Parsed %d instructions from %s", len(instructions), elf_path.name)

    return AssemblyListing(
        project_id=project_id,
        build_sha=build_sha,
        instructions=instructions,
    )


def disassemble_cached(
    build_dir: Path, project_id: str, build_sha: str
) -> AssemblyListing:
    """Return cached disassembly or parse from ELF."""
    cache = build_dir / "disassembly.json"
    if cache.exists():
        log.debug("Using cached disassembly for %s", build_sha)
        return AssemblyListing(**json.loads(cache.read_text()))

    elf = build_dir / "firmware.elf"
    listing = disassemble(elf, project_id, build_sha)

    cache.write_text(listing.model_dump_json(indent=2))
    return listing


def _parse_objdump(output: str) -> list[AssemblyInstruction]:
    instructions: list[AssemblyInstruction] = []
    current_function: str | None = None
    current_source_file: str | None = None
    current_source_line: int | None = None

    for line in output.splitlines():
        m = FUNC_RE.match(line)
        if m:
            current_function = m.group(2)
            current_source_file = None
            current_source_line = None
            continue

        m = SOURCE_RE.match(line)
        if m:
            current_source_file = m.group(1)
            current_source_line = int(m.group(2))
            continue

        m = INST_RE.match(line)
        if m:
            instructions.append(
                AssemblyInstruction(
                    pc=int(m.group(1), 16),
                    bytes_hex=m.group(2).strip(),
                    mnemonic=m.group(3),
                    operands=m.group(4).strip(),
                    function=current_function,
                    source_file=current_source_file,
                    source_line=current_source_line,
                )
            )

    return instructions
