<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  type AttemptRow = Record<string, unknown>;

  export let attempts: AttemptRow[] = [];
  export let loading = false;
  export let title = 'Cell attempts';
  export let replayEnabled = true;

  const dispatch = createEventDispatcher<{ replay: string }>();

  function value(row: AttemptRow, keys: string[]): unknown {
    for (const key of keys) {
      const candidate = row[key];
      if (candidate !== undefined && candidate !== null && candidate !== '') return candidate;
    }
    return null;
  }

  function runId(row: AttemptRow): string {
    return String(value(row, ['id', 'run_id']) ?? '');
  }

  function shortId(id: string): string {
    return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
  }

  function numeric(row: AttemptRow, keys: string[]): number | null {
    const raw = value(row, keys);
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }

  function displayNumber(row: AttemptRow, keys: string[], digits = 3): string {
    const n = numeric(row, keys);
    if (n === null) return '—';
    return Number.isInteger(n) ? String(n) : n.toFixed(digits).replace(/\.?0+$/, '');
  }

  function displayText(row: AttemptRow, keys: string[]): string {
    const raw = value(row, keys);
    return raw === null ? '—' : String(raw);
  }

  function displayPc(row: AttemptRow): string {
    const n = numeric(row, ['target_pc']);
    return n === null ? '—' : `0x${n.toString(16).toUpperCase()}`;
  }

  function replay(row: AttemptRow) {
    const id = runId(row);
    if (id) dispatch('replay', id);
  }
</script>

<section class="panel drilldown">
  <div class="header">
    <h3>{title}</h3>
    <span>{loading ? 'Loading…' : `${attempts.length} rows`}</span>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Run</th>
          <th>Outcome</th>
          <th>Delay us</th>
          <th>Width ns</th>
          <th>Voltage</th>
          <th>Target PC</th>
          <th>Elapsed ms</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each attempts as row}
          <tr class={displayText(row, ['outcome'])}>
            <td title={runId(row)}>{shortId(runId(row)) || '—'}</td>
            <td class="outcome">{displayText(row, ['outcome'])}</td>
            <td>{displayNumber(row, ['delay_us', 'glitch_delay_us'])}</td>
            <td>{displayNumber(row, ['pulse_width_ns', 'shouter_pulse_width_ns'])}</td>
            <td>{displayNumber(row, ['voltage', 'shouter_voltage'])}</td>
            <td>{displayPc(row)}</td>
            <td>{displayNumber(row, ['elapsed_ms'], 1)}</td>
            <td>
              {#if replayEnabled && runId(row)}
                <button class="replay" on:click={() => replay(row)}>Replay</button>
              {/if}
            </td>
          </tr>
        {/each}
        {#if attempts.length === 0 && !loading}
          <tr><td colspan="8" class="empty">No attempts</td></tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>

<style>
  .drilldown { min-height: 0; }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.5rem;
  }
  .header h3 { margin-bottom: 0; }
  .header span {
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
  }
  .table-wrap {
    max-height: 340px;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 11px;
  }
  thead {
    position: sticky;
    top: 0;
    background: var(--panel-2);
    z-index: 1;
  }
  th {
    text-align: left;
    padding: 0.35rem 0.45rem;
    color: var(--muted);
    font-size: 10px;
    text-transform: uppercase;
  }
  td {
    border-top: 1px solid var(--border);
    padding: 0.25rem 0.45rem;
    white-space: nowrap;
  }
  tr.glitch .outcome { color: var(--ok); }
  tr.hang .outcome { color: var(--err); }
  tr.crash .outcome { color: var(--warn); }
  tr.nothing .outcome { color: var(--muted); }
  .replay {
    border-color: var(--accent);
    color: var(--accent);
    font-size: 10px;
    padding: 0.12rem 0.45rem;
  }
  .empty {
    color: var(--muted);
    padding: 1rem;
    text-align: center;
  }
</style>
