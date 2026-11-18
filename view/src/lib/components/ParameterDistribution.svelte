<script lang="ts">
  type AttemptRow = Record<string, unknown>;
  type Outcome = 'glitch' | 'hang' | 'crash' | 'nothing' | 'unobserved';
  type Bin = { min: number; max: number; label: string };
  type MatrixCell = { total: number; counts: Record<Outcome, number> };

  export let attempts: AttemptRow[] = [];
  export let title = 'Parameter distribution';

  const OUTCOMES: Outcome[] = ['glitch', 'hang', 'crash', 'nothing', 'unobserved'];
  const OUTCOME_COLORS: Record<Outcome, string> = {
    glitch: '#00c853',
    hang: '#ff5252',
    crash: '#f9a825',
    nothing: '#607d8b',
    unobserved: '#aaa7be',
  };

  function numeric(row: AttemptRow, keys: string[]): number | null {
    for (const key of keys) {
      const n = Number(row[key]);
      if (Number.isFinite(n)) return n;
    }
    return null;
  }

  function outcome(row: AttemptRow): Outcome {
    const raw = String(row.outcome ?? 'nothing');
    return OUTCOMES.includes(raw as Outcome) ? (raw as Outcome) : 'nothing';
  }

  function formatNumber(n: number): string {
    return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, '');
  }

  function buildBins(values: number[], maxBins = 8): Bin[] {
    if (values.length === 0) return [];
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return [{ min, max, label: formatNumber(min) }];

    const count = Math.min(maxBins, Math.max(1, new Set(values).size));
    const span = max - min;
    return Array.from({ length: count }, (_, index) => {
      const bMin = min + (span * index) / count;
      const bMax = index === count - 1 ? max : min + (span * (index + 1)) / count;
      return { min: bMin, max: bMax, label: `${formatNumber(bMin)}-${formatNumber(bMax)}` };
    });
  }

  function binIndex(value: number | null, bins: Bin[]): number {
    if (value === null || bins.length === 0) return -1;
    const last = bins.length - 1;
    for (let i = 0; i < bins.length; i += 1) {
      const bin = bins[i];
      if (value >= bin.min && (value < bin.max || (i === last && value <= bin.max))) return i;
    }
    return -1;
  }

  function emptyCell(): MatrixCell {
    return { total: 0, counts: { glitch: 0, hang: 0, crash: 0, nothing: 0, unobserved: 0 } };
  }

  function buildMatrix(rows: AttemptRow[], delayBins: Bin[], widthBins: Bin[]): MatrixCell[][] {
    const matrix = delayBins.map(() => widthBins.map(() => emptyCell()));
    for (const row of rows) {
      const delay = binIndex(numeric(row, ['delay_us', 'glitch_delay_us']), delayBins);
      const width = binIndex(numeric(row, ['pulse_width_ns', 'shouter_pulse_width_ns']), widthBins);
      if (delay < 0 || width < 0) continue;
      const cell = matrix[delay][width];
      const oc = outcome(row);
      cell.total += 1;
      cell.counts[oc] += 1;
    }
    return matrix;
  }

  function dominant(cell: MatrixCell): Outcome {
    let best: Outcome = 'nothing';
    let bestCount = -1;
    for (const oc of OUTCOMES) {
      if (cell.counts[oc] > bestCount) {
        best = oc;
        bestCount = cell.counts[oc];
      }
    }
    return best;
  }

  function alpha(cell: MatrixCell, maxCell: number): string {
    if (cell.total === 0) return '0.06';
    return String(0.2 + 0.8 * (cell.total / maxCell));
  }

  function outcomeCounts(rows: AttemptRow[]): Record<Outcome, number> {
    const counts: Record<Outcome, number> = { glitch: 0, hang: 0, crash: 0, nothing: 0, unobserved: 0 };
    for (const row of rows) counts[outcome(row)] += 1;
    return counts;
  }

  $: delayValues = attempts
    .map((row) => numeric(row, ['delay_us', 'glitch_delay_us']))
    .filter((n): n is number => n !== null);
  $: widthValues = attempts
    .map((row) => numeric(row, ['pulse_width_ns', 'shouter_pulse_width_ns']))
    .filter((n): n is number => n !== null);
  $: delayBins = buildBins(delayValues);
  $: widthBins = buildBins(widthValues);
  $: matrix = buildMatrix(attempts, delayBins, widthBins);
  $: counts = outcomeCounts(attempts);
  $: maxOutcome = Math.max(1, ...OUTCOMES.map((oc) => counts[oc]));
  $: maxCell = Math.max(1, ...matrix.flat().map((cell) => cell.total));
</script>

<section class="panel distribution">
  <div class="header">
    <h3>{title}</h3>
    <span>{attempts.length} attempts</span>
  </div>

  <div class="outcomes">
    {#each OUTCOMES as oc}
      <div class="bar-row">
        <span>{oc}</span>
        <div class="bar-track">
          <div
            class="bar"
            style={`width: ${(counts[oc] / maxOutcome) * 100}%; background: ${OUTCOME_COLORS[oc]};`}
          ></div>
        </div>
        <strong>{counts[oc]}</strong>
      </div>
    {/each}
  </div>

  {#if delayBins.length > 0 && widthBins.length > 0}
    <div class="matrix">
      <div class="axis-corner">delay us</div>
      <div class="x-axis" style={`grid-template-columns: repeat(${widthBins.length}, minmax(28px, 1fr));`}>
        {#each widthBins as bin}
          <span title={bin.label}>{bin.label}</span>
        {/each}
      </div>
      <div class="y-axis">
        {#each delayBins as bin}
          <span title={bin.label}>{bin.label}</span>
        {/each}
      </div>
      <div class="grid" style={`grid-template-columns: repeat(${widthBins.length}, minmax(28px, 1fr));`}>
        {#each matrix as row}
          {#each row as cell}
            <div
              class="matrix-cell"
              title={`${cell.total} total · g${cell.counts.glitch} h${cell.counts.hang} c${cell.counts.crash} n${cell.counts.nothing} u${cell.counts.unobserved}`}
              style={`background: ${OUTCOME_COLORS[dominant(cell)]}; opacity: ${alpha(cell, maxCell)};`}
            >
              {cell.total || ''}
            </div>
          {/each}
        {/each}
      </div>
      <div class="x-label">pulse width ns</div>
    </div>
  {:else}
    <div class="empty">No delay/width samples</div>
  {/if}
</section>

<style>
  .distribution { min-width: 280px; }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.6rem;
  }
  .header h3 { margin-bottom: 0; }
  .header span {
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
  }
  .outcomes {
    display: grid;
    gap: 0.3rem;
    margin-bottom: 0.75rem;
  }
  .bar-row {
    display: grid;
    grid-template-columns: 3.7rem 1fr 2.2rem;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--mono);
    font-size: 11px;
  }
  .bar-row span { color: var(--muted); }
  .bar-row strong {
    color: var(--fg);
    font-weight: 500;
    text-align: right;
  }
  .bar-track {
    height: 7px;
    overflow: hidden;
    background: var(--panel-2);
    border-radius: 999px;
  }
  .bar {
    height: 100%;
    min-width: 1px;
  }
  .matrix {
    display: grid;
    grid-template-columns: 4.8rem 1fr;
    grid-template-rows: auto auto auto;
    gap: 0.25rem;
    font-family: var(--mono);
    font-size: 10px;
  }
  .axis-corner,
  .x-label {
    color: var(--muted);
    text-transform: uppercase;
  }
  .axis-corner { align-self: end; }
  .x-label {
    grid-column: 2;
    justify-self: end;
  }
  .x-axis,
  .grid {
    display: grid;
    gap: 2px;
    grid-auto-rows: 24px;
  }
  .x-axis span {
    min-width: 0;
    overflow: hidden;
    color: var(--muted);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .y-axis {
    display: grid;
    gap: 2px;
    grid-auto-rows: 24px;
  }
  .y-axis span {
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .matrix-cell {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 24px;
    border-radius: 3px;
    color: #fff;
    font-weight: 600;
  }
  .empty {
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
    padding: 0.8rem 0;
  }
</style>
