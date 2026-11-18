<script lang="ts">
  import { onMount } from 'svelte';
  import AttemptDrilldown from '$lib/components/AttemptDrilldown.svelte';
  import Heatmap from '$lib/components/Heatmap.svelte';
  import ParameterDistribution from '$lib/components/ParameterDistribution.svelte';
  import { heatmap as fetchHeatmap, listRuns, replay } from '$lib/api/control';
  import { toasts } from '$lib/stores/toast';

  // New /heatmap shape: per-cell per-outcome counts (Control [fyi] 2026-05-28).
  type HeatCell = {
    x: number;
    y: number;
    counts: { glitch: number; hang: number; crash: number; nothing: number; unobserved: number };
  };

  type AttemptRow = Record<string, unknown>;

  let cells: HeatCell[] = [];
  let attempts: AttemptRow[] = [];
  let selectedCell: HeatCell | null = null;
  let zValue = 0;
  let campaignFilter = '';
  let loading = false;
  let attemptsLoading = false;
  let attemptsFetchSeq = 0;

  onMount(() => { load(); });

  async function load() {
    loading = true;
    attemptsFetchSeq += 1;
    try {
      const result = await fetchHeatmap(zValue, campaignFilter || undefined);
      cells = Array.isArray(result) ? result : result?.cells ?? [];
      selectedCell = null;
      await loadAttempts(null);
    } catch {
      toasts.warn('Could not load heatmap — is Control running?');
      cells = [];
      attempts = [];
      attemptsLoading = false;
    } finally {
      loading = false;
    }
  }

  function rows(result: unknown): AttemptRow[] {
    if (Array.isArray(result)) return result as AttemptRow[];
    if (result && typeof result === 'object') {
      const candidate = result as { entries?: unknown; runs?: unknown };
      if (Array.isArray(candidate.entries)) return candidate.entries as AttemptRow[];
      if (Array.isArray(candidate.runs)) return candidate.runs as AttemptRow[];
    }
    return [];
  }

  function value(row: AttemptRow, keys: string[]): unknown {
    for (const key of keys) {
      const candidate = row[key];
      if (candidate !== undefined && candidate !== null && candidate !== '') return candidate;
    }
    return null;
  }

  function numeric(row: AttemptRow, keys: string[]): number | null {
    const n = Number(value(row, keys));
    return Number.isFinite(n) ? n : null;
  }

  function campaignId(row: AttemptRow): string {
    return String(value(row, ['campaign_id', 'campaign', 'campaignId']) ?? '').trim();
  }

  function sameNumber(a: number | null, b: number): boolean {
    return a !== null && Math.abs(a - b) <= 1e-6;
  }

  function rowMatches(row: AttemptRow, cell: HeatCell | null): boolean {
    if (campaignFilter && campaignId(row) !== campaignFilter) return false;
    if (!sameNumber(numeric(row, ['z']), zValue)) return false;
    if (!cell) return true;
    return sameNumber(numeric(row, ['x']), cell.x) && sameNumber(numeric(row, ['y']), cell.y);
  }

  async function loadAttempts(cell: HeatCell | null) {
    const seq = ++attemptsFetchSeq;
    attemptsLoading = true;
    const params: Record<string, string> = { limit: '10000', z: String(zValue) };
    if (campaignFilter) params.campaign = campaignFilter;
    if (cell) {
      // Control currently ignores x/y/z filters; keep sending them so this
      // route automatically benefits when backend-side filtering lands.
      params.x = String(cell.x);
      params.y = String(cell.y);
    }
    try {
      const result = await listRuns(params);
      if (seq === attemptsFetchSeq) {
        attempts = rows(result).filter((row) => rowMatches(row, cell));
      }
    } catch {
      if (seq === attemptsFetchSeq) {
        toasts.warn('Could not load run attempts');
        attempts = [];
      }
    } finally {
      if (seq === attemptsFetchSeq) attemptsLoading = false;
    }
  }

  async function selectCell(event: CustomEvent<HeatCell>) {
    selectedCell = event.detail;
    await loadAttempts(selectedCell);
  }

  async function doReplay(event: CustomEvent<string>) {
    try {
      await replay(event.detail);
      toasts.info('Replay started');
    } catch {
      toasts.error('Replay failed');
    }
  }

  $: selectedTitle = selectedCell
    ? `Cell x=${selectedCell.x} y=${selectedCell.y} z=${zValue}`
    : campaignFilter
      ? `Campaign ${campaignFilter} at z=${zValue}`
      : `All campaigns at z=${zValue}`;
</script>

<div class="page">
  <h2>Heatmap</h2>

  <div class="controls">
    <label>
      Z plane (mm)
      <input type="number" bind:value={zValue} step="0.01" on:change={load} />
    </label>
    <label>
      Campaign
      <input type="text" bind:value={campaignFilter} placeholder="all" />
    </label>
    <button on:click={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
  </div>

  <div class="content">
    <div class="map-pane">
      <Heatmap
        {cells}
        {selectedCell}
        width={800}
        height={500}
        on:select={selectCell}
      />
      <p class="summary">{cells.length} cells at Z={zValue}</p>
    </div>

    <div class="analytics-pane">
      <ParameterDistribution attempts={attempts} title={selectedTitle} />
      <AttemptDrilldown
        attempts={selectedCell ? attempts : []}
        loading={attemptsLoading}
        title={selectedCell ? selectedTitle : 'Select a cell'}
        on:replay={doReplay}
      />
    </div>
  </div>
</div>

<style>
  .page { padding: 1rem 1.5rem; height: 100%; display: flex; flex-direction: column; min-height: 0; }
  h2 { margin-bottom: 0.75rem; }
  .controls { display: flex; gap: 1rem; align-items: flex-end; margin-bottom: 1rem; }
  .controls label { display: flex; flex-direction: column; gap: 0.2rem; font-size: 11px; }
  .controls input { width: 6rem; }
  .content {
    display: grid;
    grid-template-columns: minmax(520px, max-content) minmax(340px, 1fr);
    gap: 1rem;
    min-height: 0;
  }
  .map-pane { min-width: 0; }
  .analytics-pane {
    display: grid;
    align-content: start;
    gap: 0.75rem;
    min-width: 0;
  }
  .summary { color: var(--muted); font-size: 11px; margin-top: 0.5rem; }
  @media (max-width: 1200px) {
    .content { grid-template-columns: 1fr; }
    .map-pane { overflow-x: auto; }
  }
</style>
