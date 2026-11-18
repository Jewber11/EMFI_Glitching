import { createLogger } from '../logger';
import { CONTROL_URL } from '../config';

const log = createLogger('control-api');

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(message: string, status: number, body: any) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export function errorDetail(err: unknown): string {
  if (err instanceof ApiError && typeof err.body?.detail === 'string') return err.body.detail;
  return err instanceof Error ? err.message : 'Unknown error';
}

async function request(method: string, path: string, body?: unknown) {
  const url = `${CONTROL_URL}${path}`;
  log.info(`${method} ${path}`);
  try {
    const opts: RequestInit = { method };
    if (body !== undefined) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(url, opts);
    if (!r.ok) {
      let parsed: any = null;
      try { parsed = await r.json(); } catch { /* not JSON */ }
      log.error(`${method} ${path} => ${r.status}`, parsed);
      throw new ApiError(`Control ${method} ${path} failed: ${r.status}`, r.status, parsed);
    }
    const data = await r.json();
    log.debug(`${method} ${path} => 200`, data);
    return data;
  } catch (err) {
    if (err instanceof TypeError) {
      log.error(`${method} ${path} network error — is Control running on ${CONTROL_URL}?`, err.message);
    }
    throw err;
  }
}

export async function armState() {
  return request('GET', '/arm_state');
}

export async function arm() {
  return request('POST', '/arm');
}

export async function disarm() {
  return request('POST', '/disarm');
}

export async function moveAbs(x: number, y: number, z: number) {
  return request('POST', '/motion/move_abs', { x, y, z });
}

export async function startCampaign(body: unknown) {
  return request('POST', '/campaigns', body);
}

export interface CampaignPreflightCheck {
  name?: string;
  label?: string;
  status?: string;
  severity?: string;
  ok?: boolean;
  message?: string;
}

export interface CampaignPreflightResult {
  ok?: boolean;
  status?: string;
  summary?: string;
  message?: string;
  detail?: unknown;
  checks?: CampaignPreflightCheck[];
  blockers?: unknown[];
  warnings?: unknown[];
  errors?: unknown[];
  total_attempts?: number;
  grid_points?: number;
  sweep_points?: number;
  required_devices?: string[];
  estimates?: Record<string, unknown>;
  estimated_seconds?: number;
}

export async function preflightCampaign(body: unknown): Promise<CampaignPreflightResult> {
  return request('POST', '/campaigns/preflight', body);
}

export async function listRuns(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return request('GET', `/runs?${qs}`);
}

export function exportRunsUrl(params: Record<string, string> = {}) {
  const qs = new URLSearchParams({ format: 'csv', ...params }).toString();
  return `${CONTROL_URL}/runs/export?${qs}`;
}

export async function heatmap(z?: number, campaign?: string) {
  const qs = new URLSearchParams();
  if (z !== undefined) qs.set('z', String(z));
  if (campaign) qs.set('campaign', campaign);
  return request('GET', `/heatmap?${qs.toString()}`);
}

export async function replay(runId: string) {
  return request('POST', `/replay/${runId}`);
}

export async function devices() {
  return request('GET', '/devices');
}

export async function getCampaign(id: string) {
  return request('GET', `/campaigns/${id}`);
}

export async function stopCampaign(id: string) {
  return request('POST', `/campaigns/${id}/stop`);
}

export async function moveRel(axis: string, distance: number) {
  return request('POST', '/motion/move_rel', { axis, distance });
}

export async function home() {
  return request('POST', '/motion/home');
}

export async function setOrigin() {
  return request('POST', '/motion/set_origin');
}

export async function setTopRight(x: number, y: number) {
  return request('POST', '/motion/set_top_right', { x, y });
}

export interface FixtureGrid {
  name: string;
  origin: [number, number];
  top_right: [number, number];
  machine_origin: [number, number, number];
  machine_top_right?: [number, number, number] | null;
  step_size_mm: number;
  z_min_mm: number;
  z_max_mm: number;
  z_step_mm: number;
  notes?: string;
  updated_at?: string;
}

export async function getFixture(): Promise<{ ok: boolean; fixture: FixtureGrid | null }> {
  return request('GET', '/motion/fixture');
}

export async function saveCurrentFixture(body: {
  name?: string;
  step_size_mm?: number;
  z_min_mm?: number;
  z_max_mm?: number;
  z_step_mm?: number;
  notes?: string;
}): Promise<{ ok: boolean; fixture: FixtureGrid }> {
  return request('POST', '/motion/fixture/save_current', body);
}

export async function applyFixture(): Promise<{ ok: boolean; fixture: FixtureGrid; origin_set: boolean; top_right: [number, number] }> {
  return request('POST', '/motion/fixture/apply');
}

export async function connectDevice(id: string, port?: string) {
  return request('POST', `/devices/${id}/connect`, port ? { port } : undefined);
}

export async function shouterConfig(params: Record<string, unknown>) {
  return request('POST', '/shouter/config', params);
}

export async function shouterStatus() {
  return request('GET', '/shouter/status');
}

export async function shouterPulse(pulseWidthNs?: number) {
  return request('POST', '/shouter/pulse', pulseWidthNs == null ? {} : { pulse_width_ns: pulseWidthNs });
}

export async function shouterArm() {
  return request('POST', '/shouter/arm');
}

export async function shouterDisarm() {
  return request('POST', '/shouter/disarm');
}

export async function listCampaigns() {
  return request('GET', '/campaigns');
}

export interface CampaignMetadata {
  campaign_id: string;
  notes?: string;
  tags?: string[];
  updated_at?: string;
}

export async function getCampaignMetadata(id: string): Promise<CampaignMetadata> {
  return request('GET', `/campaigns/${encodeURIComponent(id)}/metadata`);
}

export async function putCampaignMetadata(
  id: string,
  body: { notes?: string; tags?: string[] }
): Promise<CampaignMetadata> {
  return request('PUT', `/campaigns/${encodeURIComponent(id)}/metadata`, body);
}

export type ScaffoldRail = 'dut' | 'platform' | 'all';
export interface ScaffoldPowerState { dut: boolean; platform: boolean; }

export async function scaffoldPowerGet(): Promise<ScaffoldPowerState> {
  return request('GET', '/devices/scaffold/power');
}

export async function scaffoldPowerSet(rail: ScaffoldRail, on: boolean): Promise<ScaffoldPowerState> {
  return request('POST', '/devices/scaffold/power', { rail, on });
}

export async function scaffoldPowerCycle(rail: ScaffoldRail, off_time = 0.05): Promise<ScaffoldPowerState> {
  return request('POST', '/devices/scaffold/power_cycle', { rail, off_time });
}

export async function ad2Status() {
  return request('GET', '/devices/ad2/status');
}

export async function ad2Connect() {
  return request('POST', '/devices/ad2/connect');
}

export async function ad2Capture() {
  return request('GET', '/devices/ad2/capture');
}

export async function ad2TriggeredCapture(params: {
  sample_rate_hz?: number;
  samples?: number;
  analog_range_v?: number;
  trigger_level_v?: number;
  trigger_hysteresis_v?: number;
  timeout_s?: number;
} = {}) {
  return request('POST', '/devices/ad2/capture_triggered', params);
}

export async function ad2Configure(params: {
  sample_rate_hz?: number;
  samples?: number;
  analog_range_v?: number;
}) {
  return request('POST', '/devices/ad2/configure', params);
}

export async function ad2StartStream(period_s = 0.5) {
  return request('POST', '/devices/ad2/start_stream', { period_s });
}

export async function ad2StopStream() {
  return request('POST', '/devices/ad2/stop_stream');
}
