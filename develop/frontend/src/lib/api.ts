import type {
  Project, BuildArtifact, AssemblyListing, GlitchTarget,
  FileTreeNode, Template, GitLogEntry
} from '$lib/types';
import { base } from '$app/paths';

const API = base;
const CONTROL = import.meta.env.VITE_CONTROL_URL || '/api/control';

export async function flashFirmwareFile(path: string, mode: string, name: string) {
  return json_or_throw(await fetch(`${CONTROL}/target/flash`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ build_sha: `file:${path}`, elf_url: path, mode, name })
  }));
}

async function json_or_throw(r: Response) {
  if (!r.ok) {
    const text = await r.text().catch(() => '');
    throw new Error(`${r.status}: ${text}`);
  }
  return r.json();
}

// ── Projects ───────────────────────────────────────────────
export async function listProjects(): Promise<Project[]> {
  return json_or_throw(await fetch(`${API}/projects`));
}

export async function getProject(id: string): Promise<Project> {
  return json_or_throw(await fetch(`${API}/projects/${id}`));
}

export async function createProject(data: {
  name: string; template: string; language: string; hal: string; description?: string;
}): Promise<Project> {
  return json_or_throw(await fetch(`${API}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }));
}

export async function importProject(data: {
  name: string; source_path: string; language: string; hal: string;
  description?: string; exclude?: string[];
}): Promise<Project> {
  return json_or_throw(await fetch(`${API}/projects/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }));
}

export async function deleteProject(id: string): Promise<void> {
  const r = await fetch(`${API}/projects/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`deleteProject: ${r.status}`);
}

// ── File ops ───────────────────────────────────────────────
export async function getFileTree(id: string): Promise<FileTreeNode> {
  return json_or_throw(await fetch(`${API}/projects/${id}/tree`));
}

export async function getFile(id: string, path: string): Promise<{ path: string; contents: string }> {
  return json_or_throw(await fetch(`${API}/projects/${id}/file?path=${encodeURIComponent(path)}`));
}

export async function putFile(id: string, path: string, contents: string): Promise<void> {
  const r = await fetch(`${API}/projects/${id}/file?path=${encodeURIComponent(path)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents }),
  });
  if (!r.ok) throw new Error(`putFile: ${r.status}`);
}

// ── Git ────────────────────────────────────────────────────
export async function gitCommit(id: string, message: string): Promise<{ sha: string }> {
  return json_or_throw(await fetch(`${API}/projects/${id}/git/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  }));
}

export async function gitTag(id: string, name: string): Promise<void> {
  const r = await fetch(`${API}/projects/${id}/git/tag`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw new Error(`gitTag: ${r.status}`);
}

export async function gitLog(id: string, limit = 20): Promise<GitLogEntry[]> {
  return json_or_throw(await fetch(`${API}/projects/${id}/git/log?limit=${limit}`));
}

// ── Builds ─────────────────────────────────────────────────
export async function triggerBuild(id: string, version?: string, force = false): Promise<BuildArtifact> {
  const qs = force ? '?force=true' : '';
  return json_or_throw(await fetch(`${API}/projects/${id}/build${qs}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version }),
  }));
}

export async function listBuilds(id: string): Promise<BuildArtifact[]> {
  return json_or_throw(await fetch(`${API}/projects/${id}/builds`));
}

export async function getBuild(id: string, sha: string): Promise<BuildArtifact> {
  return json_or_throw(await fetch(`${API}/projects/${id}/builds/${sha}`));
}

export async function getDisassembly(id: string, sha: string): Promise<AssemblyListing> {
  return json_or_throw(await fetch(`${API}/projects/${id}/builds/${sha}/disassembly`));
}

// ── Targets ────────────────────────────────────────────────
export async function listTargets(id: string): Promise<GlitchTarget[]> {
  return json_or_throw(await fetch(`${API}/projects/${id}/targets`));
}

export async function addTarget(
  id: string,
  target: { pc_address: number; name: string; expected_delay_cycles?: number; notes?: string; created_at: string }
): Promise<GlitchTarget> {
  return json_or_throw(await fetch(`${API}/projects/${id}/targets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(target),
  }));
}

export async function removeTarget(id: string, pcAddress: number): Promise<void> {
  const r = await fetch(`${API}/projects/${id}/targets/${pcAddress}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`removeTarget: ${r.status}`);
}

// ── Templates ──────────────────────────────────────────────
export async function listTemplates(): Promise<Template[]> {
  return json_or_throw(await fetch(`${API}/templates`));
}

// ── Agent ──────────────────────────────────────────────────
export async function runAgent(id: string, prompt: string): Promise<{ job_id: string }> {
  return json_or_throw(await fetch(`${API}/projects/${id}/agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  }));
}

// ── Host script ────────────────────────────────────────────
export async function getHostScript(id: string): Promise<{ path: string; contents: string }> {
  return json_or_throw(await fetch(`${API}/projects/${id}/host_script`));
}

export async function putHostScript(id: string, contents: string): Promise<void> {
  const r = await fetch(`${API}/projects/${id}/host_script`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents }),
  });
  if (!r.ok) throw new Error(`putHostScript: ${r.status}`);
}

// ── Prompt ─────────────────────────────────────────────────
export async function getPrompt(id: string): Promise<{ prompt: string }> {
  return json_or_throw(await fetch(`${API}/projects/${id}/prompt`));
}

// ── Flash (calls Control service) ──────────────────────────
export async function flashToTarget(projectId: string, sha: string): Promise<unknown> {
  const elfUrl = `${window.location.origin}${API}/projects/${projectId}/builds/${sha}/firmware.elf`;
  return json_or_throw(await fetch(`${CONTROL}/target/flash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ elf_url: elfUrl, build_sha: sha }),
  }));
}
