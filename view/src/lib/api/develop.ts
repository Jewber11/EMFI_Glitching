import { createLogger } from '../logger';
import { DEVELOP_URL } from '../config';

const log = createLogger('develop-api');

async function request(method: string, path: string, body?: unknown) {
  const url = `${DEVELOP_URL}${path}`;
  log.info(`${method} ${path}`);
  try {
    const opts: RequestInit = { method };
    if (body !== undefined) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(url, opts);
    if (!r.ok) {
      const text = await r.text().catch(() => '');
      log.error(`${method} ${path} => ${r.status}`, text);
      throw new Error(`Develop ${method} ${path} failed: ${r.status}`);
    }
    const data = await r.json();
    log.debug(`${method} ${path} => 200`, data);
    return data;
  } catch (err) {
    if (err instanceof TypeError) {
      log.error(`${method} ${path} network error — is Develop running on ${DEVELOP_URL}?`, err.message);
    }
    throw err;
  }
}

export async function listProjects() {
  return request('GET', '/projects');
}

export async function getProject(id: string) {
  return request('GET', `/projects/${id}`);
}

export async function listBuilds(id: string) {
  return request('GET', `/projects/${id}/builds`);
}

export async function disassembly(id: string, sha: string) {
  return request('GET', `/projects/${id}/builds/${sha}/disassembly`);
}

export async function listTargets(id: string) {
  return request('GET', `/projects/${id}/targets`);
}

export interface GlitchTargetInput {
  pc_address: number;
  pc_end?: number | null;
  name: string;
  expected_delay_cycles?: number | null;
  expected_delay_cycles_end?: number | null;
  notes?: string | null;
  created_at: string;
}

export async function addTarget(id: string, target: GlitchTargetInput) {
  return request('POST', `/projects/${id}/targets`, target);
}

export async function removeTarget(id: string, pcAddress: number) {
  return request('DELETE', `/projects/${id}/targets/${pcAddress}`);
}

export async function listPresets(id: string) {
  return request('GET', `/projects/${id}/presets`);
}
