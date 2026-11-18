<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import SweepConfig from '$lib/components/SweepConfig.svelte';
  import GridConfig from '$lib/components/GridConfig.svelte';
  import { listPresets, listProjects } from '$lib/api/develop';
  import { applyFixture, getFixture, startCampaign, preflightCampaign, ApiError, type FixtureGrid } from '$lib/api/control';
  import { toasts } from '$lib/stores/toast';
  import { onMount } from 'svelte';

  type PreflightState = 'idle' | 'running' | 'pass' | 'warn' | 'fail' | 'unavailable';

  interface DisplayCheck {
    label: string;
    status: 'pass' | 'warn' | 'fail' | 'unknown';
    message: string;
  }

  let projects: any[] = [];
  let presets: any[] = [];
  let selectedProject = '';
  let selectedVersion = '';
  let selectedPreset = '';
  let campaignName = '';
  let loading = false;
  let presetsLoading = false;
  let showAdvanced = false;
  let showPreview = false;
  let fixtureName = '';
  let applyingFixture = false;
  let preflightState: PreflightState = 'idle';
  let preflightMessage = 'Run preflight before start to check Control readiness.';
  let preflightChecks: DisplayCheck[] = [];
  let lastPreflightKey = '';

  let triggerMode = 'software';
  let shouterVoltage = 250;
  let shouterPulseWidth = 1000;
  let verdictTimeout = 500;
  let targetPort = "";
  let targetBaud = 115200;
  let targetNormal = "normal";
  let targetGlitch = "ESCAPED";
  let shouterMute = true;
  let shouterAutoArm = true;
  let stopMaxGlitches: number | null = null;
  let stopOnFirstCrash = false;
  let stopMaxRuntimeMinutes: number | null = null;

  let sweep = {
    delay_us: null as { start: number; stop: number; step: number } | null,
    pulse_width_ns: null as { start: number; stop: number; step: number } | null,
    voltage_v: null as { start: number; stop: number; step: number } | null,
    attempts_per_point: 1
  };

  let grid = {
    origin: [0, 0] as [number, number],
    top_right: [10, 10] as [number, number],
    step_size_mm: 1.0,
    z_min_mm: 0.0,
    z_max_mm: 0.5,
    z_step_mm: 0.1
  };

  onMount(async () => {
    // Pre-populate grid from calibration wizard query params, if present.
    const qp = $page.url.searchParams;
    const ox = qp.get('origin_x');
    const oy = qp.get('origin_y');
    const tx = qp.get('top_right_x');
    const ty = qp.get('top_right_y');
    if (ox != null && oy != null && tx != null && ty != null) {
      grid = {
        ...grid,
        origin: [parseFloat(ox), parseFloat(oy)],
        top_right: [parseFloat(tx), parseFloat(ty)],
      };
      toasts.info('Grid pre-populated from calibration');
    } else {
      await loadDefaultFixture(true);
    }

    try {
      const result = await listProjects();
      projects = Array.isArray(result) ? result : result?.projects ?? [];
    } catch {
      toasts.warn('Could not load projects from Develop');
    }
  });

  function useFixtureGrid(fixture: FixtureGrid) {
    grid = {
      ...grid,
      origin: fixture.origin,
      top_right: fixture.top_right,
      step_size_mm: fixture.step_size_mm,
      z_min_mm: fixture.z_min_mm,
      z_max_mm: fixture.z_max_mm,
      z_step_mm: fixture.z_step_mm,
    };
    fixtureName = fixture.name;
  }

  async function loadDefaultFixture(applyOrigin = false) {
    try {
      const result = await getFixture();
      if (!result.fixture) return;
      useFixtureGrid(result.fixture);
      toasts.info(`Grid loaded from fixture ${result.fixture.name}`);
      if (applyOrigin) await applyDefaultFixture();
    } catch {
      toasts.warn('Could not load fixture default');
    }
  }

  async function applyDefaultFixture() {
    applyingFixture = true;
    try {
      const result = await applyFixture();
      useFixtureGrid(result.fixture);
      toasts.info(`Fixture ${result.fixture.name} applied`);
    } catch {
      toasts.error('Apply fixture failed');
    } finally {
      applyingFixture = false;
    }
  }

  $: versions = projects.find((p: any) => p.id === selectedProject)?.versions ?? [];
  let presetProject = '';
  $: if (selectedProject !== presetProject) {
    presetProject = selectedProject;
    selectedPreset = '';
    presets = [];
    if (selectedProject) void fetchPresets(selectedProject);
  }

  // ── Pre-flight estimate (read-only, computed before submit) ──
  function spanSteps(a: number, b: number, step: number): number {
    const span = Math.abs(b - a);
    if (!Number.isFinite(span) || !Number.isFinite(step) || step <= 0) return 1;
    return Math.max(1, Math.round(span / step) + 1);
  }

  function rangeLen(r: { start: number; stop: number; step: number } | null): number {
    if (!r || !Number.isFinite(r.step) || r.step <= 0) return 1;
    return Math.max(1, Math.floor((r.stop - r.start) / r.step) + 1);
  }

  $: xSteps = spanSteps(grid.origin[0], grid.top_right[0], grid.step_size_mm);
  $: ySteps = spanSteps(grid.origin[1], grid.top_right[1], grid.step_size_mm);
  $: zSteps = spanSteps(grid.z_min_mm, grid.z_max_mm, grid.z_step_mm);
  $: gridPts = xSteps * ySteps * zSteps;
  $: sweepCount =
    rangeLen(sweep.delay_us) * rangeLen(sweep.pulse_width_ns) * rangeLen(sweep.voltage_v);
  $: attempts = Math.max(1, sweep.attempts_per_point || 1);
  $: totalAttempts = gridPts * sweepCount * attempts;
  $: estSeconds = Math.round(totalAttempts / 2);

  $: smallGridWarning = gridPts < 4;
  $: reversedGridWarning = grid.top_right[0] < grid.origin[0] || grid.top_right[1] < grid.origin[1];
  $: collapsedGridWarning = grid.top_right[0] === grid.origin[0] || grid.top_right[1] === grid.origin[1];

  $: formComplete = campaignName.trim() !== '';
  $: canSubmit = formComplete && preflightState !== 'fail';

  async function fetchPresets(projectId: string) {
    presetsLoading = true;
    try {
      const result = await listPresets(projectId);
      if (presetProject === projectId) {
        presets = Array.isArray(result) ? result : result?.presets ?? [];
      }
    } catch {
      if (presetProject === projectId) presets = [];
    } finally {
      if (presetProject === projectId) presetsLoading = false;
    }
  }

  function cloneRange(value: any) {
    if (!value) return null;
    return {
      start: Number(value.start),
      stop: Number(value.stop),
      step: Number(value.step)
    };
  }

  function applyPreset(presetId: string) {
    const preset = presets.find((p: any) => p.id === presetId);
    const config = preset?.config;
    if (!preset || !config) return;

    campaignName = String(config.name ?? preset.name ?? campaignName);
    selectedVersion = config.project_version ?? '';
    if (config.grid) {
      grid = {
        origin: [Number(config.grid.origin?.[0] ?? 0), Number(config.grid.origin?.[1] ?? 0)],
        top_right: [
          Number(config.grid.top_right?.[0] ?? 0),
          Number(config.grid.top_right?.[1] ?? 0)
        ],
        step_size_mm: Number(config.grid.step_size_mm ?? 1),
        z_min_mm: Number(config.grid.z_min_mm ?? 0),
        z_max_mm: Number(config.grid.z_max_mm ?? 0),
        z_step_mm: Number(config.grid.z_step_mm ?? 0.1)
      };
    }
    if (config.sweep) {
      sweep = {
        delay_us: cloneRange(config.sweep.delay_us),
        pulse_width_ns: cloneRange(config.sweep.pulse_width_ns),
        voltage_v: cloneRange(config.sweep.voltage_v),
        attempts_per_point: Number(config.sweep.attempts_per_point ?? 1)
      };
    }
    triggerMode = String(config.trigger_mode ?? triggerMode);
    shouterVoltage = Number(config.shouter_voltage ?? shouterVoltage);
    shouterPulseWidth = Number(config.shouter_pulse_width_ns ?? shouterPulseWidth);
    verdictTimeout = Number(config.verdict_timeout_ms ?? verdictTimeout);
    shouterMute = Boolean(config.shouter_mute ?? shouterMute);
    shouterAutoArm = Boolean(config.shouter_auto_arm ?? shouterAutoArm);
    const stops = config.stop_conditions ?? config;
    stopMaxGlitches =
      stops.max_glitches == null ? null : Math.max(1, Math.trunc(Number(stops.max_glitches)));
    stopOnFirstCrash = Boolean(stops.stop_on_first_crash ?? false);
    const maxRuntimeSeconds = stops.max_runtime_seconds ?? stops.max_runtime_s;
    stopMaxRuntimeMinutes =
      maxRuntimeSeconds == null ? null : Math.max(1, Math.ceil(Number(maxRuntimeSeconds) / 60));
    preflightState = 'idle';
    preflightMessage = 'Preset loaded. Run preflight before start.';
    preflightChecks = [];
    lastPreflightKey = '';
    toasts.info(`Loaded preset ${preset.name}`);
  }

  function optionalPositiveInt(value: number | null): number | null {
    if (value == null || value === 0 || value === undefined) return null;
    const parsed = Math.trunc(Number(value));
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }

  function buildStopConditions(): Record<string, unknown> | null {
    const conditions: Record<string, unknown> = {};
    const maxGlitches = optionalPositiveInt(stopMaxGlitches);
    const maxRuntimeMinutes = optionalPositiveInt(stopMaxRuntimeMinutes);

    if (maxGlitches !== null) conditions.max_glitches = maxGlitches;
    if (stopOnFirstCrash) conditions.stop_on_first_crash = true;
    if (maxRuntimeMinutes !== null) conditions.max_runtime_seconds = maxRuntimeMinutes * 60;

    return Object.keys(conditions).length > 0 ? conditions : null;
  }

  function buildBody(): Record<string, unknown> {
    const body: Record<string, unknown> = {
      name: campaignName.trim(),
      project_id: selectedProject || "_standalone",
      grid: {
        origin: grid.origin,
        top_right: grid.top_right,
        step_size_mm: grid.step_size_mm,
        z_min_mm: grid.z_min_mm,
        z_max_mm: grid.z_max_mm,
        z_step_mm: grid.z_step_mm,
      },
      sweep: {
        delay_us: sweep.delay_us,
        pulse_width_ns: sweep.pulse_width_ns,
        voltage_v: sweep.voltage_v,
        attempts_per_point: sweep.attempts_per_point,
      },
      trigger_mode: triggerMode,
      shouter_voltage: shouterVoltage,
      shouter_pulse_width_ns: shouterPulseWidth,
      verdict_timeout_ms: verdictTimeout,
      target_serial_port: targetPort.trim() || null,
      target_serial_baud: targetBaud,
      target_normal_text: targetNormal,
      target_glitch_text: targetGlitch,
      shouter_mute: shouterMute,
      shouter_auto_arm: shouterAutoArm,
    };
    const stopConditions = buildStopConditions();
    if (stopConditions) body.stop_conditions = stopConditions;
    if (selectedVersion) body.project_version = selectedVersion;
    return body;
  }

  $: previewJson = formComplete ? JSON.stringify(buildBody(), null, 2) : '{}';
  $: preflightKey = formComplete ? JSON.stringify(buildBody()) : '';
  $: if (
    lastPreflightKey &&
    preflightKey !== lastPreflightKey &&
    preflightState !== 'running'
  ) {
    preflightState = 'idle';
    preflightMessage = 'Campaign inputs changed. Run preflight again before start.';
    preflightChecks = [];
    lastPreflightKey = '';
  }

  function textList(value: unknown): string[] {
    if (Array.isArray(value)) return value.map((v) => String(v));
    if (typeof value === 'string') return [value];
    return [];
  }

  function detailText(detail: unknown): string {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((entry: any) => {
          const loc = Array.isArray(entry?.loc)
            ? entry.loc.filter((s: unknown) => s !== 'body').join('.')
            : '';
          const msg = entry?.msg ?? entry?.message ?? String(entry);
          return loc ? `${loc}: ${msg}` : String(msg);
        })
        .join('; ');
    }
    if (detail && typeof detail === 'object') {
      const maybeMessage = (detail as any).message ?? (detail as any).msg;
      if (maybeMessage) return String(maybeMessage);
    }
    return '';
  }

  function checkStatus(check: any): DisplayCheck['status'] {
    const raw = String(check?.status ?? check?.severity ?? '').toLowerCase();
    if (check?.ok === false || ['fail', 'failed', 'error', 'blocked'].includes(raw)) return 'fail';
    if (['warn', 'warning'].includes(raw)) return 'warn';
    if (check?.ok === true || ['pass', 'passed', 'ok', 'success'].includes(raw)) return 'pass';
    return 'unknown';
  }

  function normalizeChecks(result: any): DisplayCheck[] {
    const checks = Array.isArray(result?.checks) ? result.checks : [];
    const normalized = checks.slice(0, 6).map((check: any) => ({
      label: String(check?.label ?? check?.name ?? 'Check'),
      status: checkStatus(check),
      message: String(check?.message ?? check?.summary ?? check?.status ?? '')
    }));

    if (normalized.length > 0) return normalized;

    const blockers = textList(result?.blockers);
    const warnings = textList(result?.warnings);
    const generated: DisplayCheck[] = [
      ...blockers.map((message) => ({ label: 'Blocker', status: 'fail' as const, message })),
      ...warnings.map((message) => ({ label: 'Warning', status: 'warn' as const, message }))
    ];

    if (typeof result?.grid_points === 'number') {
      generated.push({
        label: 'Grid points',
        status: 'pass',
        message: String(result.grid_points)
      });
    }
    if (typeof result?.sweep_points === 'number') {
      generated.push({
        label: 'Sweep points',
        status: 'pass',
        message: String(result.sweep_points)
      });
    }

    return generated.slice(0, 8);
  }

  function applyPreflightResult(result: any): PreflightState {
    const status = String(result?.status ?? '').toLowerCase();
    const warnings = textList(result?.warnings);
    const blockers = textList(result?.blockers);
    const errors = [...textList(result?.errors), ...blockers];
    const checks = normalizeChecks(result);
    const hasFailedCheck = checks.some((check) => check.status === 'fail');
    const hasWarnCheck = checks.some((check) => check.status === 'warn');
    let nextState: PreflightState;

    if (
      result?.ok === false ||
      errors.length > 0 ||
      hasFailedCheck ||
      ['fail', 'failed', 'error', 'blocked'].includes(status)
    ) {
      nextState = 'fail';
    } else if (warnings.length > 0 || hasWarnCheck || ['warn', 'warning'].includes(status)) {
      nextState = 'warn';
    } else {
      nextState = 'pass';
    }

    preflightState = nextState;
    const estimateSeconds =
      typeof result?.estimated_seconds === 'number'
        ? result.estimated_seconds
        : result?.estimates?.min_runtime_seconds_at_rate_limit;
    const estimate =
      typeof result?.total_attempts === 'number'
        ? ` ${result.total_attempts} attempts${typeof estimateSeconds === 'number' ? `, ~${Math.ceil(estimateSeconds)}s minimum` : ''}.`
        : '';
    preflightMessage =
      String(result?.summary ?? result?.message ?? errors[0] ?? warnings[0] ?? 'Control preflight passed.') +
      estimate;
    preflightChecks = checks;
    lastPreflightKey = preflightKey;
    return nextState;
  }

  function applyPreflightError(err: unknown) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 501)) {
      preflightState = 'unavailable';
      preflightMessage = 'Control does not expose POST /campaigns/preflight yet.';
      preflightChecks = [];
      lastPreflightKey = preflightKey;
      return true;
    }

    if (err instanceof ApiError) {
      preflightState = 'fail';
      preflightMessage = detailText(err.body?.detail) || `Control preflight failed: ${err.status}`;
      preflightChecks = [];
      lastPreflightKey = preflightKey;
      return false;
    }

    preflightState = 'unavailable';
    preflightMessage = 'Could not reach Control preflight.';
    preflightChecks = [];
    lastPreflightKey = preflightKey;
    return true;
  }

  async function runPreflight(): Promise<boolean> {
    if (!formComplete) {
      preflightState = 'fail';
      preflightMessage = 'Enter a campaign name before preflight.';
      preflightChecks = [];
      return false;
    }

    preflightState = 'running';
    preflightMessage = 'Checking Control preflight...';
    preflightChecks = [];
    try {
      const result = await preflightCampaign(buildBody());
      const resultState = applyPreflightResult(result);
      return resultState !== 'fail';
    } catch (err) {
      return applyPreflightError(err);
    }
  }

  async function submit() {
    if (!canSubmit) return;
    loading = true;
    try {
      const preflightOk = await runPreflight();
      if (!preflightOk) {
        toasts.error('Resolve preflight before starting campaign');
        return;
      }
      const result = await startCampaign(buildBody());
      toasts.info('Campaign started');
      const campaignId = result?.campaign_id ?? result?.id;
      if (campaignId) goto(`/campaign/${campaignId}`);
    } catch (err) {
      if (err instanceof ApiError && err.body?.detail) {
        if (Array.isArray(err.body.detail)) {
          for (const e of err.body.detail) {
            const loc = Array.isArray(e.loc)
              ? e.loc.filter((s: unknown) => s !== 'body').join('.')
              : '?';
            toasts.error(`${loc}: ${e.msg}`, { where: 'validation' });
          }
        } else {
          toasts.error(String(err.body.detail));
        }
      } else {
        toasts.error('Failed to start campaign');
      }
    } finally {
      loading = false;
    }
  }
</script>

<div class="page">
  <h2>New Campaign</h2>

  <div class="form-grid">
    <div class="col">
      <div class="panel">
        <h3>Campaign</h3>
        <div class="field">
          <label for="camp-name">Name</label>
          <input id="camp-name" type="text" bind:value={campaignName} placeholder="my-scan-01" />
        </div>
        <div class="field">
          <label for="camp-project">Project</label>
          <select id="camp-project" bind:value={selectedProject}>
            <option value="">Standalone target</option>
            {#each projects as p}
              <option value={p.id}>{p.name} ({p.language})</option>
            {/each}
          </select>
        </div>
        {#if versions.length > 0}
          <div class="field">
            <label for="camp-version">Version</label>
            <select id="camp-version" bind:value={selectedVersion}>
              <option value="">latest (HEAD)</option>
              {#each versions as v}
                <option value={v}>{v}</option>
              {/each}
            </select>
          </div>
        {/if}
        {#if selectedProject}
          <div class="field">
            <label for="camp-preset">Preset</label>
            <select
              id="camp-preset"
              bind:value={selectedPreset}
              disabled={presetsLoading || presets.length === 0}
              on:change={() => applyPreset(selectedPreset)}
            >
              <option value="">
                {presetsLoading ? 'Loading presets...' : presets.length ? 'Select preset' : 'No presets'}
              </option>
              {#each presets as preset}
                <option value={preset.id}>{preset.name}</option>
              {/each}
            </select>
          </div>
        {/if}
      </div>

      <div class="grid-headline">
        <div>
          <h3>Grid</h3>
          {#if fixtureName}<small>fixture {fixtureName}</small>{/if}
        </div>
        <button type="button" on:click={() => applyDefaultFixture()} disabled={applyingFixture}>
          {applyingFixture ? 'Applying...' : 'Apply fixture'}
        </button>
      </div>

      <GridConfig bind:value={grid} />

      <div class="panel preflight" class:warn={smallGridWarning || reversedGridWarning || collapsedGridWarning}>
        <div class="preflight-head">
          <h3>Pre-flight</h3>
          <span class="preflight-pill {preflightState}">
            {preflightState === 'running' ? 'checking' : preflightState}
          </span>
        </div>
        <div class="preflight-lines">
          <div>Grid: {xSteps} × {ySteps} × {zSteps} = <b>{gridPts}</b></div>
          <div>Sweep: {sweepCount} combos × {attempts} attempts</div>
          <div>Total: <b>{totalAttempts}</b> attempts (~{estSeconds}s)</div>
        </div>
        <div class="preflight-status {preflightState}">
          <p>{preflightMessage}</p>
          {#if preflightChecks.length > 0}
            <ul>
              {#each preflightChecks as check}
                <li class={check.status}>
                  <span>{check.label}</span>
                  {#if check.message}<small>{check.message}</small>{/if}
                </li>
              {/each}
            </ul>
          {/if}
          <button
            type="button"
            class="preflight-run"
            on:click={runPreflight}
            disabled={!formComplete || preflightState === 'running' || loading}
          >
            {preflightState === 'running' ? 'Checking...' : 'Run Preflight'}
          </button>
        </div>
        {#if smallGridWarning || reversedGridWarning || collapsedGridWarning}
          <div class="preflight-warn">
            {#if smallGridWarning}
              <p>Grid will only produce {gridPts} point{gridPts === 1 ? '' : 's'}. Start is still allowed.</p>
            {/if}
            {#if reversedGridWarning}
              <p>Opposite corner is left/below origin. Control will scan in the signed direction.</p>
            {/if}
            {#if collapsedGridWarning}
              <p>One axis is zero. This is a row/column scan.</p>
            {/if}
            <button type="button" on:click={() => goto('/calibrate')}>Recalibrate</button>
          </div>
        {/if}
      </div>

      <SweepConfig bind:value={sweep} />
    </div>

    <div class="col">
      <details class="panel" bind:open={showAdvanced}>
        <summary><h3>Advanced</h3></summary>
        <div class="field">
          <label for="camp-trigger">Trigger mode</label>
          <select id="camp-trigger" bind:value={triggerMode}>
            <option value="software">Software</option>
          </select>
        </div>
        <div class="field">
          <label for="camp-pulse">Pulse width (ns)</label>
          <input id="camp-pulse" type="number" bind:value={shouterPulseWidth} min="1000" max="50000" step="1000" />
        </div>
        <div class="field">
          <label for="target-port">Target serial port (optional)</label>
          <input id="target-port" bind:value={targetPort} placeholder="/dev/ttyUSB1" />
          <small>Leave empty to record unobserved pulses or use the project host script.</small>
        </div>
        <div class="field">
          <label for="target-baud">Target baud</label>
          <input id="target-baud" type="number" bind:value={targetBaud} min="300" />
        </div>
        <div class="field"><label for="target-normal">Normal response text</label><input id="target-normal" bind:value={targetNormal} /></div>
        <div class="field"><label for="target-glitch">Glitch response text</label><input id="target-glitch" bind:value={targetGlitch} /></div>
        <div class="field">
          <label for="camp-timeout">Verdict timeout (ms)</label>
          <input id="camp-timeout" type="number" bind:value={verdictTimeout} min="10" />
        </div>
        <div class="field row">
          <label><input type="checkbox" bind:checked={shouterAutoArm} /> Auto-arm</label>
        </div>
        <div class="stop-grid">
          <div class="field">
            <label for="camp-stop-glitches">Max glitches</label>
            <input
              id="camp-stop-glitches"
              type="number"
              bind:value={stopMaxGlitches}
              min="1"
              placeholder="unlimited"
            />
          </div>
          <div class="field">
            <label for="camp-stop-runtime">Max runtime (min)</label>
            <input
              id="camp-stop-runtime"
              type="number"
              bind:value={stopMaxRuntimeMinutes}
              min="1"
              placeholder="unlimited"
            />
          </div>
        </div>
        <div class="field row">
          <label><input type="checkbox" bind:checked={stopOnFirstCrash} /> Stop on first crash</label>
        </div>
      </details>

      <details class="panel" bind:open={showPreview}>
        <summary><h3>Request preview</h3></summary>
        <pre class="preview">{previewJson}</pre>
      </details>

      <button class="start-btn" on:click={submit} disabled={!canSubmit || loading}>
        {loading ? 'Starting…' : 'Start Campaign'}
      </button>
      {#if !formComplete}
        <p class="hint">Enter a campaign name to enable submit.</p>
      {/if}
    </div>
  </div>
</div>

<style>
  .page { padding: 1rem 1.5rem; max-width: 960px; }
  h2 { margin-bottom: 1rem; }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; align-items: start; }
  .col { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.2rem; margin-bottom: 0.4rem; }
  .field input[type="text"], .field input[type="number"], .field select { width: 100%; }
  .field.row { flex-direction: row; gap: 1rem; }
  .stop-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
  .grid-headline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.35rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .grid-headline h3 { margin: 0; }
  .grid-headline small {
    color: var(--muted);
    font-family: var(--mono);
    font-size: 10px;
  }

  details.panel { cursor: default; }
  details.panel summary {
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  details.panel summary::before {
    content: '▶';
    font-size: 9px;
    color: var(--muted);
    transition: transform 0.15s;
  }
  details[open].panel summary::before { transform: rotate(90deg); }
  details.panel summary h3 { margin: 0; }
  details.panel > :not(summary) { margin-top: 0.5rem; }

  .preview {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    background: var(--panel-2);
    border-radius: var(--radius);
    padding: 0.5rem;
    max-height: 300px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .start-btn {
    padding: 0.6rem 1.5rem;
    background: var(--accent);
    color: var(--bg);
    border: none;
    font-weight: 700;
    font-size: 14px;
    border-radius: var(--radius);
    cursor: pointer;
    margin-top: 0.5rem;
  }
  .start-btn:hover:not(:disabled) { filter: brightness(1.1); }
  .start-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .hint { color: var(--muted); font-size: 11px; margin-top: 0.25rem; }

  .preflight.warn { border: 1px solid var(--warn); }
  .preflight-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.45rem;
  }
  .preflight-head h3 { margin: 0; }
  .preflight-pill {
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
    font-family: var(--mono);
    font-size: 10px;
    line-height: 1;
    padding: 0.25rem 0.45rem;
    text-transform: uppercase;
  }
  .preflight-pill.pass { border-color: var(--ok); color: var(--ok); }
  .preflight-pill.warn,
  .preflight-pill.unavailable { border-color: var(--warn); color: var(--warn); }
  .preflight-pill.fail { border-color: var(--err); color: var(--err); }
  .preflight-lines {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--fg);
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .preflight-lines b { color: var(--accent); }
  .preflight-status {
    margin-top: 0.65rem;
    border-top: 1px solid var(--border);
    padding-top: 0.55rem;
  }
  .preflight-status p {
    color: var(--muted);
    font-size: 12px;
    margin: 0 0 0.5rem;
  }
  .preflight-status.pass p { color: var(--ok); }
  .preflight-status.warn p,
  .preflight-status.unavailable p { color: var(--warn); }
  .preflight-status.fail p { color: var(--err); }
  .preflight-status ul {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    margin: 0 0 0.55rem;
    padding: 0;
    list-style: none;
  }
  .preflight-status li {
    display: grid;
    grid-template-columns: minmax(8rem, 0.8fr) 1fr;
    gap: 0.5rem;
    font-size: 11px;
    color: var(--muted);
  }
  .preflight-status li.pass span { color: var(--ok); }
  .preflight-status li.warn span { color: var(--warn); }
  .preflight-status li.fail span { color: var(--err); }
  .preflight-status li small {
    color: var(--muted);
    font-size: 11px;
  }
  .preflight-run {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--fg);
    cursor: pointer;
    font-size: 12px;
    padding: 0.35rem 0.6rem;
  }
  .preflight-run:hover:not(:disabled) { border-color: var(--accent); }
  .preflight-run:disabled { cursor: not-allowed; opacity: 0.45; }
  .preflight-warn {
    margin-top: 0.6rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
  }
  .preflight-warn p { color: var(--warn); font-size: 12px; margin: 0 0 0.4rem; }
  .preflight-actions { display: flex; gap: 0.5rem; }
  .preflight-actions .ack {
    background: var(--warn);
    color: var(--bg);
    border-color: var(--warn);
    font-weight: 600;
  }
</style>
