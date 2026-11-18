<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';

  type Outcome = 'glitch' | 'hang' | 'crash' | 'nothing' | 'unobserved';
  type Filter = 'all' | Outcome;

  interface HeatCell {
    x: number;
    y: number;
    counts: { glitch: number; hang: number; crash: number; nothing: number; unobserved: number };
  }

  export let cells: HeatCell[] = [];
  export let width = 600;
  export let height = 400;
  export let selectedCell: HeatCell | null = null;

  const dispatch = createEventDispatcher<{ select: HeatCell }>();

  // Matches OUTCOME_COLORS in Scene3D so the 3D view and heatmap agree.
  const OUTCOME_COLORS: Record<Outcome, string> = {
    glitch: '#00c853',
    hang: '#ff5252',
    crash: '#f9a825',
    nothing: '#607d8b',
    unobserved: '#aaa7be',
  };
  const OUTCOMES: Outcome[] = ['glitch', 'hang', 'crash', 'nothing', 'unobserved'];
  const CHIPS: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'glitch', label: 'Glitch' },
    { key: 'hang', label: 'Hang' },
    { key: 'crash', label: 'Crash' },
    { key: 'nothing', label: 'Nothing' },
    { key: 'unobserved', label: 'Unobserved' },
  ];

  let filter: Filter = 'all';
  let canvas: HTMLCanvasElement;

  function cellTotal(c: HeatCell): number {
    return c.counts.glitch + c.counts.hang + c.counts.crash + c.counts.nothing + (c.counts.unobserved ?? 0);
  }

  // The count that drives a cell's intensity under the current filter:
  // total attempts for "all", or the single outcome's count for a specific filter.
  function cellValue(c: HeatCell, f: Filter): number {
    return f === 'all' ? cellTotal(c) : c.counts[f] ?? 0;
  }

  function dominantOutcome(c: HeatCell): Outcome {
    let best: Outcome = 'nothing';
    let bestN = -1;
    for (const o of OUTCOMES) {
      if (c.counts[o] > bestN) {
        bestN = c.counts[o];
        best = o;
      }
    }
    return best;
  }

  function rgba(hex: string, alpha: number): string {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha.toFixed(3)})`;
  }

  // Redraw whenever the data, active filter, or selection changes.
  $: if (canvas) draw(cells, filter, selectedCell);

  function draw(data: HeatCell[], f: Filter, activeCell: HeatCell | null) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#111';
    ctx.fillRect(0, 0, width, height);

    if (data.length === 0) {
      emptyMessage(ctx, 'No campaigns run yet');
      return;
    }

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, maxC = 0;
    for (const c of data) {
      if (c.x < minX) minX = c.x;
      if (c.x > maxX) maxX = c.x;
      if (c.y < minY) minY = c.y;
      if (c.y > maxY) maxY = c.y;
      const v = cellValue(c, f);
      if (v > maxC) maxC = v;
    }

    // Rows exist, but none match the chosen filter — a helpful empty state
    // distinct from "no campaigns at all".
    if (maxC === 0) {
      const label = f === 'all' ? 'No attempts recorded yet' : `No ${f} outcomes recorded`;
      emptyMessage(ctx, label);
      return;
    }

    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;
    const pad = 30;
    const drawW = width - pad * 2;
    const drawH = height - pad * 2;

    const xSteps = new Set(data.map((c) => c.x)).size;
    const ySteps = new Set(data.map((c) => c.y)).size;
    const cellW = Math.max(2, drawW / xSteps);
    const cellH = Math.max(2, drawH / ySteps);

    for (const c of data) {
      const v = cellValue(c, f);
      if (v === 0) continue; // nothing of the chosen outcome here — leave it dark
      const px = pad + ((c.x - minX) / rangeX) * drawW;
      const py = pad + ((c.y - minY) / rangeY) * drawH;
      const base = f === 'all' ? OUTCOME_COLORS[dominantOutcome(c)] : OUTCOME_COLORS[f];
      // Floor the alpha so single-attempt cells stay visible.
      const alpha = 0.2 + 0.8 * (v / maxC);
      ctx.fillStyle = rgba(base, alpha);
      ctx.fillRect(px - cellW / 2, py - cellH / 2, cellW, cellH);
    }

    if (activeCell) {
      const px = pad + ((activeCell.x - minX) / rangeX) * drawW;
      const py = pad + ((activeCell.y - minY) / rangeY) * drawH;
      ctx.strokeStyle = '#e4e6ed';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(px - cellW / 2 - 2, py - cellH / 2 - 2, cellW + 4, cellH + 4);
    }

    ctx.fillStyle = '#8b91a3';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(minX.toFixed(1), pad, height - 8);
    ctx.fillText(maxX.toFixed(1), width - pad, height - 8);
    ctx.textAlign = 'right';
    ctx.fillText(minY.toFixed(1), pad - 4, pad + 4);
    ctx.fillText(maxY.toFixed(1), pad - 4, height - pad + 4);
  }

  function emptyMessage(ctx: CanvasRenderingContext2D, text: string) {
    ctx.fillStyle = '#8b91a3';
    ctx.font = '13px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(text, width / 2, height / 2);
  }

  let tooltipText = '';
  let tooltipX = 0;
  let tooltipY = 0;
  let showTooltip = false;

  function nearestCell(mx: number, my: number, maxDistance = 20): HeatCell | null {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const c of cells) {
      if (c.x < minX) minX = c.x;
      if (c.x > maxX) maxX = c.x;
      if (c.y < minY) minY = c.y;
      if (c.y > maxY) maxY = c.y;
    }
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;
    const pad = 30;
    const drawW = width - pad * 2;
    const drawH = height - pad * 2;

    let closest: HeatCell | null = null;
    let bestDist = maxDistance;
    for (const c of cells) {
      const px = pad + ((c.x - minX) / rangeX) * drawW;
      const py = pad + ((c.y - minY) / rangeY) * drawH;
      const d = Math.hypot(mx - px, my - py);
      if (d < bestDist) { bestDist = d; closest = c; }
    }
    return closest;
  }

  function onMouseMove(ev: MouseEvent) {
    if (cells.length === 0) { showTooltip = false; return; }
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;
    const closest = nearestCell(mx, my);
    if (closest) {
      tooltipText =
        filter === 'all'
          ? `(${closest.x}, ${closest.y}) g${closest.counts.glitch} h${closest.counts.hang} c${closest.counts.crash} n${closest.counts.nothing} u${closest.counts.unobserved ?? 0} · ${cellTotal(closest)} total`
          : `(${closest.x}, ${closest.y}) ${filter} = ${closest.counts[filter] ?? 0}`;
      tooltipX = ev.clientX;
      tooltipY = ev.clientY;
      showTooltip = true;
    } else {
      showTooltip = false;
    }
  }

  function onClick(ev: MouseEvent) {
    if (cells.length === 0) return;
    const rect = canvas.getBoundingClientRect();
    const closest = nearestCell(ev.clientX - rect.left, ev.clientY - rect.top);
    if (closest) dispatch('select', closest);
  }

  function onKeydown(ev: KeyboardEvent) {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      const firstCell = selectedCell ?? cells[0];
      if (firstCell) dispatch('select', firstCell);
    }
  }

  onMount(() => { draw(cells, filter, selectedCell); });
</script>

<div class="heatmap-wrap">
  <div class="chips">
    {#each CHIPS as chip}
      <button
        class="chip"
        class:active={filter === chip.key}
        style={chip.key === 'all' ? '' : `--chip-color: ${OUTCOME_COLORS[chip.key]}`}
        on:click={() => (filter = chip.key)}
      >
        {chip.label}
      </button>
    {/each}
  </div>

  <canvas
    bind:this={canvas}
    {width}
    {height}
    role="button"
    tabindex="0"
    aria-label="Campaign heatmap"
    on:click={onClick}
    on:keydown={onKeydown}
    on:mousemove={onMouseMove}
    on:mouseleave={() => (showTooltip = false)}
  ></canvas>
  {#if showTooltip}
    <div class="tooltip" style="left: {tooltipX + 12}px; top: {tooltipY - 10}px;">
      {tooltipText}
    </div>
  {/if}
</div>

<style>
  .heatmap-wrap { position: relative; display: inline-block; }
  canvas { background: #111; border-radius: var(--radius); display: block; }
  canvas:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }

  .chips { display: flex; gap: 0.35rem; margin-bottom: 0.5rem; }
  .chip {
    font-size: 11px;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    color: var(--muted);
    cursor: pointer;
  }
  .chip:hover { color: var(--fg); }
  .chip.active {
    color: var(--bg);
    background: var(--chip-color, var(--accent));
    border-color: var(--chip-color, var(--accent));
    font-weight: 600;
  }

  .tooltip {
    position: fixed;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.2rem 0.5rem;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--fg);
    pointer-events: none;
    z-index: 100;
    white-space: nowrap;
  }
</style>
