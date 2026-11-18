"""Project CRUD over ~/emfi-projects/<id>/."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from emfi_protocol.projects import Project

from develop import git_ops
from develop.config import projects_root, templates_root

log = logging.getLogger(__name__)


class ProjectNotFoundError(Exception):
    pass


class ProjectExistsError(Exception):
    pass


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _parse_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_project(project_path: Path) -> Project:
    toml_path = project_path / "project.toml"
    if not toml_path.exists():
        raise ProjectNotFoundError(f"No project.toml in {project_path}")

    data = _parse_toml(toml_path)

    try:
        versions = git_ops.list_tags(project_path)
    except git_ops.GitError:
        versions = []

    return Project(
        id=project_path.name,
        name=data.get("name", project_path.name),
        language=data.get("language", "c"),
        target=data.get("target", "mspm0l2228"),
        hal=data.get("hal", "ti"),
        created_at=datetime.fromisoformat(data["created_at"])
        if "created_at" in data
        else datetime.now(timezone.utc),
        description=data.get("description"),
        build_command=data.get("build_command"),
        artifact_elf=data.get("artifact_elf"),
        versions=versions,
    )


def project_dir(project_id: str) -> Path:
    return projects_root() / project_id


def list_projects() -> List[Project]:
    """Scan ~/emfi-projects/ for valid projects."""
    root = projects_root()
    log.info("Listing projects in %s", root)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return []

    projects = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        toml_path = entry / "project.toml"
        if not toml_path.exists():
            log.debug("Skipping %s — no project.toml", entry.name)
            continue
        try:
            projects.append(_load_project(entry))
        except Exception as e:
            log.warning("Skipping %s — error loading: %s", entry.name, e)
    return projects


def get_project(project_id: str) -> Project:
    log.info("Loading project %s", project_id)
    p = project_dir(project_id)
    if not p.exists():
        raise ProjectNotFoundError(f"Project {project_id!r} not found")
    return _load_project(p)


def create_project(
    name: str, template: str, language: str, hal: str, description: str = ""
) -> Project:
    """Copy a template into ~/emfi-projects/<slug>/ and git init."""
    slug = _slugify(name)
    dest = project_dir(slug)

    log.info(
        "Creating project name=%s slug=%s template=%s lang=%s hal=%s",
        name, slug, template, language, hal,
    )

    if dest.exists():
        raise ProjectExistsError(f"Project directory {dest} already exists")

    template_dir = templates_root() / template
    if not template_dir.exists():
        raise FileNotFoundError(f"Template {template!r} not found at {template_dir}")

    projects_root().mkdir(parents=True, exist_ok=True)
    shutil.copytree(template_dir, dest)

    # Render project.toml from template
    tmpl_file = dest / "project.toml.template"
    now = datetime.now(timezone.utc).isoformat()
    if tmpl_file.exists():
        content = tmpl_file.read_text()
        content = content.replace("{{ project_name }}", name)
        content = content.replace("{{ created_at }}", now)
        content = content.replace("{{ description }}", description or "")
        (dest / "project.toml").write_text(content)
        tmpl_file.unlink()
    else:
        (dest / "project.toml").write_text(
            f'name = "{name}"\n'
            f'language = "{language}"\n'
            f'target = "mspm0l2228"\n'
            f'hal = "{hal}"\n'
            f'created_at = "{now}"\n'
            f'description = "{description}"\n'
        )

    git_ops.init(dest)
    git_ops.commit(dest, "Initial commit from template")

    return _load_project(dest)


def delete_project(project_id: str) -> None:
    """Soft delete: move to ~/emfi-projects/.trash/<id>-<ts>/."""
    p = project_dir(project_id)
    if not p.exists():
        raise ProjectNotFoundError(f"Project {project_id!r} not found")

    trash = projects_root() / ".trash"
    trash.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest = trash / f"{project_id}-{ts}"

    log.warning("Soft-deleting project %s -> %s", project_id, dest)
    shutil.move(str(p), str(dest))


def file_tree(project_id: str) -> dict:
    """Walk the project directory, return a nested dict tree."""
    root = project_dir(project_id)
    if not root.exists():
        raise ProjectNotFoundError(f"Project {project_id!r} not found")

    skip = {".git", "builds", "__pycache__", "target"}

    def _walk(dirpath: Path) -> dict:
        children = []
        try:
            entries = sorted(dirpath.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        except PermissionError:
            return {"name": dirpath.name, "type": "dir", "path": "", "children": []}

        for entry in entries:
            if entry.name in skip or entry.name.startswith("."):
                continue
            rel = str(entry.relative_to(root))
            if entry.is_dir():
                children.append(_walk(entry))
            else:
                children.append({"name": entry.name, "type": "file", "path": rel})
        return {
            "name": dirpath.name,
            "type": "dir",
            "path": str(dirpath.relative_to(root)) if dirpath != root else "",
            "children": children,
        }

    return _walk(root)


def read_file(project_id: str, relative_path: str) -> str:
    """Read a file's contents, with path-traversal prevention."""
    root = project_dir(project_id)
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise PermissionError("Path traversal denied")
    if not target.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    log.debug("Reading %s in project %s", relative_path, project_id)
    return target.read_text(errors="replace")


def _unique_slug(base: str) -> str:
    """Return a slug that doesn't collide with existing projects."""
    slug = _slugify(base)
    if not project_dir(slug).exists():
        return slug
    n = 2
    while project_dir(f"{slug}_{n}").exists():
        n += 1
    return f"{slug}_{n}"


def _detect_ccs_artifact(src: Path) -> str | None:
    """Detect the .out artifact path for a CCS project.

    Approach: parse .project XML for <name>, fall back to globbing Debug/*.out.
    """
    project_xml = src / ".project"
    if project_xml.exists():
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(project_xml)
            name_el = tree.find("name")
            if name_el is not None and name_el.text:
                candidate = f"Debug/{name_el.text.strip()}.out"
                log.info("CCS .project name=%s → artifact_elf=%s", name_el.text.strip(), candidate)
                return candidate
        except Exception as e:
            log.warning("Failed to parse .project XML: %s", e)

    debug_dir = src / "Debug"
    if debug_dir.exists():
        outs = list(debug_dir.glob("*.out"))
        if len(outs) == 1:
            candidate = f"Debug/{outs[0].name}"
            log.info("CCS Debug/ glob found single .out → artifact_elf=%s", candidate)
            return candidate
        if len(outs) > 1:
            log.warning("Multiple .out files in Debug/: %s — leaving artifact_elf unset", outs)

    log.info("Could not auto-detect CCS artifact; artifact_elf left unset (edit project.toml manually)")
    return None


def import_project(
    name: str,
    source_path: str,
    language: str,
    hal: str,
    description: str = "",
    exclude: list[str] | None = None,
) -> Project:
    """Import an external source directory into ~/emfi-projects/<id>/."""
    import fnmatch

    src = Path(source_path)
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"Source path does not exist or is not a directory: {source_path}")
    if src.resolve().is_relative_to(projects_root().resolve()):
        raise ValueError("Source is already under the projects root")

    slug = _unique_slug(name)
    dest = project_dir(slug)

    is_ccs = any((src / f).exists() for f in (".ccsproject", ".cproject"))

    if exclude is None:
        exclude = [".git/**"] if is_ccs else ["Debug/**", ".git/**"]
    elif is_ccs:
        exclude = [p for p in exclude if not p.startswith("Debug")]

    if is_ccs:
        log.info("Detected CCS project layout in %s", source_path)

    build_command: str | None = None
    artifact_elf: str | None = None
    if is_ccs:
        build_command = "make -C Debug all"
        artifact_elf = _detect_ccs_artifact(src)

    if not description and is_ccs:
        description = "Imported from Code Composer Studio project; build runs make -C Debug."

    log.info("Importing project name=%s from %s -> %s (exclude=%s)", name, source_path, dest, exclude)

    projects_root().mkdir(parents=True, exist_ok=True)
    dest.mkdir()

    def _is_excluded(rel: str) -> bool:
        for pat in exclude:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel + "/", pat):
                return True
            parts = rel.split("/")
            for i in range(len(parts)):
                partial = "/".join(parts[: i + 1])
                if fnmatch.fnmatch(partial, pat) or fnmatch.fnmatch(partial + "/", pat):
                    return True
        return False

    for item in src.rglob("*"):
        rel = str(item.relative_to(src))
        if _is_excluded(rel):
            continue
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    now = datetime.now(timezone.utc).isoformat()
    toml_lines = [
        f'name = "{name}"',
        f'language = "{language}"',
        f'target = "mspm0l2228"',
        f'hal = "{hal}"',
        f'created_at = "{now}"',
        f'description = "{description}"',
    ]
    if build_command:
        toml_lines.append(f'build_command = "{build_command}"')
    if artifact_elf:
        toml_lines.append(f'artifact_elf = "{artifact_elf}"')
    (dest / "project.toml").write_text("\n".join(toml_lines) + "\n")

    if not (dest / "targets.json").exists():
        (dest / "targets.json").write_text("[]\n")

    host_dir = dest / "host"
    if not (host_dir / "run.py").exists():
        host_dir.mkdir(exist_ok=True)
        _write_default_host_script(host_dir / "run.py", language)

    git_ops.init(dest)
    git_ops.commit(dest, f"Import from {source_path}")

    return _load_project(dest)


def default_host_script(language: str = "c") -> str:
    """Return the canonical host/run.py template for a given language.

    Reads from the same template file shipped under
    ``backend/develop/templates/<template>/host/run.py`` so the inline
    fallback (used at import time when the source tree has no
    ``host/run.py``) and the per-template starter stay byte-identical.
    """
    template = "rust_b01lers" if language == "rust" else "c_ti_hal"
    return (templates_root() / template / "host" / "run.py").read_text()


def _write_default_host_script(path: Path, language: str = "c") -> None:
    """Write the canonical host/run.py template."""
    path.write_text(default_host_script(language))


def write_file(project_id: str, relative_path: str, contents: str) -> None:
    """Write file contents, with path-traversal prevention."""
    root = project_dir(project_id)
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise PermissionError("Path traversal denied")
    target.parent.mkdir(parents=True, exist_ok=True)
    log.info("Writing %s in project %s (%d bytes)", relative_path, project_id, len(contents))
    target.write_text(contents)
