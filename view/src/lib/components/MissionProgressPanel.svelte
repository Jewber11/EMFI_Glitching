<script lang="ts">
  import { activeCampaign } from '$lib/stores/campaign';
  import { countersStore } from '$lib/stores/counters';
  import { logStore, type AttemptEntry } from '$lib/stores/log';

  const cols = 18;
  const rows = 12;
  const totalCells = cols * rows;

  type Cell = {
    hot: number;
    visited: boolean;
    success: number;
    nothing: number;
    crash: number;
    hang: number;
    attempts: number;
    unobserved: number;
    current: boolean;
  };

  function emptyCells(): Cell[] {
    return Array.from({ length: totalCells }, (_, i) => {
      const c = i % cols;
      const r = Math.floor(i / cols);
      const hot = 0;
      return { hot, visited: false, success: 0, nothing: 0, crash: 0, hang: 0, attempts: 0, unobserved: 0, current: false };
    });
  }

  function bounds(rowsIn: AttemptEntry[]) {
    const xs = rowsIn.map((r) => Number(r.x)).filter(Number.isFinite);
    const ys = rowsIn.map((r) => Number(r.y)).filter(Number.isFinite);
    if (!xs.length || !ys.length) return null;
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }

  function indexFor(x: number, y: number, b: ReturnType<typeof bounds>, fallback = 0) {
    if (!b || b.maxX === b.minX || b.maxY === b.minY) return Math.max(0, Math.min(totalCells - 1, fallback));
    const cx = Math.max(0, Math.min(cols - 1, Math.round(((x - b.minX) / (b.maxX - b.minX)) * (cols - 1))));
    const cy = Math.max(0, Math.min(rows - 1, Math.round(((y - b.minY) / (b.maxY - b.minY)) * (rows - 1))));
    return cy * cols + cx;
  }

  function isSuccess(outcome: string | undefined) {
    return outcome === 'glitch' || outcome === 'success';
  }

  function buildCells(
    logs: AttemptEntry[],
    completed: number,
    currentPos: [number, number, number] | null,
    showCurrent: boolean,
  ): Cell[] {
    const cells = emptyCells();
    const recent = logs.slice(-1200);
    const b = bounds(recent);
    for (const row of recent) {
      const idx = indexFor(Number(row.x), Number(row.y), b);
      const cell = cells[idx];
      cell.visited = true;
      cell.attempts += 1;
      if (isSuccess(row.outcome)) cell.success += 1;
      else if (row.outcome === 'crash') cell.crash += 1;
      else if (row.outcome === 'hang') cell.hang += 1;
      else if (row.outcome === 'unobserved') cell.unobserved += 1;
      else cell.nothing += 1;
      cell.hot = Math.max(cell.hot, cell.success / Math.max(1, cell.attempts - cell.unobserved));
    }

    if (showCurrent) {
      const currentIdx = currentPos
        ? indexFor(currentPos[0], currentPos[1], b, completed % totalCells)
        : Math.max(0, Math.min(totalCells - 1, completed % totalCells));
      cells[currentIdx].current = true;
    }
    return cells;
  }

  function cellTitle(cell: Cell, index: number) {
    const x = index % cols;
    const y = Math.floor(index / cols);
    if (!cell.visited) return `Cell ${x},${y}: not swept yet.`;
    const rate = Math.round((cell.success / Math.max(1, cell.attempts - cell.unobserved)) * 100);
    return `Cell ${x},${y}: ${cell.success}/${cell.attempts} success (${rate}%). crash ${cell.crash}, hang ${cell.hang}, nothing ${cell.nothing}, unobserved ${cell.unobserved}.`;
  }

  function hotFill(cell: Cell) {
    if (cell.current) return 'var(--scope-green)';
    const rate = cell.visited ? cell.success / Math.max(1, cell.attempts - cell.unobserved) : cell.hot;
    if (rate <= 0.02) return 'var(--ink-2)';
    return `rgba(229, 41, 58, ${(0.1 + rate * 0.78).toFixed(3)})`;
  }

  $: completed = $activeCampaign?.completed_attempts ?? 0;
  $: totalAttempts = $activeCampaign?.total_attempts ?? 0;
  $: currentPosition = $activeCampaign?.current_position ?? null;
  $: cells = buildCells($logStore, completed, currentPosition, Boolean($activeCampaign?.active || completed > 0));
  $: progressPct = totalAttempts ? Math.min(100, (completed / totalAttempts) * 100) : 0;
  $: etaAttempts = Math.max(0, totalAttempts - completed);
  $: etaSeconds = Math.round(etaAttempts * 0.1);
  $: eta = `${String(Math.floor(etaSeconds / 60)).padStart(2, '0')}:${String(etaSeconds % 60).padStart(2, '0')}`;
  $: successCount = $countersStore.glitches ?? 0;
  $: nothingCount = $countersStore.nothings ?? 0;
  $: crashCount = $countersStore.crashes ?? 0;
  $: hangCount = $countersStore.hangs ?? 0;
  $: attempts = $countersStore.attempts ?? 0;
</script>

<aside class="progress-shell">
  <div class="panel-head">
    <div class="section-label">// campaign progress</div>
    <h2>{$activeCampaign?.campaign_id ?? 'No active campaign'}</h2>
    <div class="tags">
      <span class="tag">DUT</span>
      <span class="tag cyan">EMFI</span>
    </div>
  </div>

  <section class="map-section">
    <div class="section-row">
      <span class="section-label">// die map</span>
      <span class="map-size">{cols}x{rows}</span>
    </div>
    <div class="chip-grid">
      {#each cells as cell, i}
        <div
          class="chip-cell"
          class:visited={cell.visited}
          class:current={cell.current}
          style:background={hotFill(cell)}
          title={cellTitle(cell, i)}
        ></div>
      {/each}
    </div>
    <div class="legend">
      <span><i class="hot"></i> hotspot</span>
      <span><i class="current"></i> current</span>
      <span><i class="swept"></i> swept</span>
    </div>
  </section>

  <section class="sweep-section">
    <div class="section-row">
      <span class="section-label">// sweep</span>
      <span class="eta">{$activeCampaign?.active ? `ETA ${eta}` : totalAttempts && completed >= totalAttempts ? 'complete' : '-'}</span>
    </div>
    <div class="progress-track">
      <div class="progress-fill" style:width={`${progressPct}%`}></div>
      {#if $activeCampaign?.active}
        <div class="scan"></div>
      {/if}
    </div>
    <div class="progress-meta">
      <span>{completed} / {totalAttempts || '-'} attempts</span>
      <span>{progressPct.toFixed(1)}%</span>
    </div>
  </section>

  <section class="stats">
    <div class="section-label">// outcomes</div>
    <div class="stat-grid">
      <div class="stat green"><strong>{successCount}</strong><span>success</span></div>
      <div class="stat muted"><strong>{nothingCount}</strong><span>nothing</span></div>
      <div class="stat red"><strong>{crashCount}</strong><span>crash</span></div>
      <div class="stat gold"><strong>{hangCount}</strong><span>hangs</span></div>
      <div class="stat"><strong>{attempts}</strong><span>attempts</span></div>
      <div class="stat cyan"><strong>{attempts > ($countersStore.unobserved ?? 0) ? ((successCount / (attempts - ($countersStore.unobserved ?? 0))) * 100).toFixed(1) : '0.0'}%</strong><span>yield</span></div>
    </div>
  </section>
</aside>

<style>
  .progress-shell {
    width: 370px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--ink-1);
    border-right: 1px solid var(--line);
  }

  .panel-head {
    padding: 1rem;
    border-bottom: 1px solid var(--line);
  }

  h2 {
    margin: 0.35rem 0 0;
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 500;
    color: var(--fg-1);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tags {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.6rem;
  }

  .map-section,
  .sweep-section,
  .stats {
    padding: 1rem;
    border-bottom: 1px solid var(--line);
  }

  .section-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.55rem;
  }

  .map-size,
  .eta,
  .progress-meta {
    color: var(--fg-4);
    font-family: var(--mono);
    font-size: 10px;
  }

  .chip-grid {
    display: grid;
    grid-template-columns: repeat(18, minmax(0, 1fr));
    gap: 2px;
    padding: 2px;
    background: var(--ink-0);
    border: 1px solid var(--line);
    border-radius: 6px;
  }

  .chip-cell {
    aspect-ratio: 1;
    min-width: 0;
    border: 1px solid var(--line-faint);
    border-radius: 1px;
    transition: background 120ms ease, box-shadow 120ms ease;
  }

  .chip-cell.visited:not(.current) {
    border-color: var(--gold);
    box-shadow: inset 0 0 4px rgba(240, 188, 44, 0.18);
  }

  .chip-cell.current {
    box-shadow: 0 0 10px var(--scope-green), inset 0 0 0 1px rgba(255, 255, 255, 0.45);
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-top: 0.55rem;
    color: var(--fg-3);
    font-family: var(--mono);
    font-size: 10px;
  }

  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
  }

  .legend i {
    width: 9px;
    height: 9px;
    border-radius: 2px;
    display: inline-block;
  }

  .legend .hot { background: var(--red); }
  .legend .current { background: var(--scope-green); }
  .legend .swept { border: 1px solid var(--gold); }

  .progress-track {
    position: relative;
    height: 9px;
    overflow: hidden;
    background: var(--ink-0);
    border: 1px solid var(--line);
    border-radius: 999px;
  }

  .progress-fill {
    position: absolute;
    inset: 0 auto 0 0;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--gold-deep), var(--gold));
    transition: width 160ms linear;
  }

  .scan {
    position: absolute;
    inset: 0;
    width: 35%;
    background: linear-gradient(90deg, transparent, rgba(46, 211, 198, 0.18), transparent);
    animation: ff-scan 2.2s linear infinite;
  }

  .progress-meta {
    display: flex;
    justify-content: space-between;
    margin-top: 0.45rem;
  }

  .stats {
    margin-top: auto;
    background: var(--ink-0);
  }

  .stat-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-top: 0.55rem;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .stat {
    min-width: 0;
    padding: 0.75rem;
    background: var(--ink-1);
    border-right: 1px solid var(--line-faint);
    border-bottom: 1px solid var(--line-faint);
  }

  .stat strong {
    display: block;
    font-size: 22px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }

  .stat span {
    display: block;
    margin-top: 0.45rem;
    color: var(--fg-3);
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .stat.green strong { color: var(--scope-green); }
  .stat.muted strong { color: var(--fg-3); }
  .stat.red strong { color: var(--red-bright); }
  .stat.gold strong { color: var(--gold); }
  .stat.cyan strong { color: var(--scope-cyan); }

  @media (max-width: 1180px) {
    .progress-shell {
      width: 320px;
    }
  }

  @media (max-width: 980px) {
    .progress-shell {
      width: 100%;
      border-right: none;
      border-bottom: 1px solid var(--line);
    }
  }
</style>
