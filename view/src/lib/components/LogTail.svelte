<script lang="ts">
  import { logStore, type AttemptEntry } from '$lib/stores/log';
  import { createEventDispatcher, afterUpdate } from 'svelte';

  export let limit = 200;
  export let filter: string = 'all';

  const dispatch = createEventDispatcher<{ select: AttemptEntry }>();

  let tableEl: HTMLDivElement;

  $: filtered = filter === 'all'
    ? $logStore.slice(-limit)
    : $logStore.filter((e) => e.outcome === filter).slice(-limit);

  afterUpdate(() => {
    if (tableEl) tableEl.scrollTop = tableEl.scrollHeight;
  });

  function formatTime(ts: string): string {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-GB', { hour12: false });
    } catch { return ts; }
  }
</script>

<div class="log-controls">
  <select bind:value={filter}>
    <option value="all">All</option>
    <option value="glitch">Glitch</option>
    <option value="hang">Hang</option>
    <option value="crash">Crash</option>
    <option value="nothing">Nothing</option>
  </select>
  <span class="count">{filtered.length} entries</span>
</div>

<div class="log-table" bind:this={tableEl}>
  <table>
    <thead>
      <tr>
        <th>Time</th>
        <th>Outcome</th>
        <th>X</th>
        <th>Y</th>
        <th>Z</th>
        <th>ms</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as e (e.id)}
        <tr class={e.outcome} on:click={() => dispatch('select', e)}>
          <td>{formatTime(e.ts)}</td>
          <td class="outcome">{e.outcome}</td>
          <td>{e.x.toFixed(2)}</td>
          <td>{e.y.toFixed(2)}</td>
          <td>{e.z.toFixed(2)}</td>
          <td>{e.elapsed_ms ?? '—'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .log-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
  }
  .log-controls select { font-size: 11px; padding: 0.2rem 0.4rem; }
  .count { color: var(--muted); font-size: 11px; }
  .log-table {
    max-height: 350px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 11px;
  }
  thead { position: sticky; top: 0; background: var(--panel-2); z-index: 1; }
  th {
    text-align: left;
    padding: 0.3rem 0.4rem;
    color: var(--muted);
    font-weight: 500;
    font-size: 10px;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 0.2rem 0.4rem;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  tr { cursor: pointer; transition: background 0.1s; }
  tr:hover { background: var(--panel-2); }
  tr.glitch .outcome { color: var(--ok); }
  tr.hang .outcome { color: var(--err); }
  tr.crash .outcome { color: var(--warn); }
  tr.nothing .outcome { color: var(--muted); }
</style>
