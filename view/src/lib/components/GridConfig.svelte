<script lang="ts">
  import { positionStore } from '$lib/stores/position';

  export let value = {
    origin: [0, 0] as [number, number],
    top_right: [10, 10] as [number, number],
    step_size_mm: 1.0,
    z_min_mm: 0.0,
    z_max_mm: 0.5,
    z_step_mm: 0.1
  };

  function useCurrentAsOrigin() {
    value.origin = [$positionStore.x, $positionStore.y];
    value = value;
  }

  function useCurrentAsTopRight() {
    value.top_right = [$positionStore.x, $positionStore.y];
    value = value;
  }

  $: xSpan = value.top_right[0] - value.origin[0];
  $: ySpan = value.top_right[1] - value.origin[1];
</script>

<fieldset>
  <legend>Grid</legend>

  <div class="row">
    <label>Origin XY</label>
    <input type="number" bind:value={value.origin[0]} step="0.1" />
    <input type="number" bind:value={value.origin[1]} step="0.1" />
    <button on:click={useCurrentAsOrigin} title="Use current probe position">Use pos</button>
  </div>

  <div class="row">
    <label>Opposite XY</label>
    <input type="number" bind:value={value.top_right[0]} step="0.1" />
    <input type="number" bind:value={value.top_right[1]} step="0.1" />
    <button on:click={useCurrentAsTopRight} title="Use current probe position">Use pos</button>
  </div>

  <div class="row">
    <label>Step (mm)</label>
    <input type="number" bind:value={value.step_size_mm} min="0.01" step="0.1" />
  </div>

  <div class="row">
    <label>Z range</label>
    <input type="number" bind:value={value.z_min_mm} step="0.01" placeholder="min" />
    <span class="sep">-</span>
    <input type="number" bind:value={value.z_max_mm} step="0.01" placeholder="max" />
    <span class="sep">step</span>
    <input type="number" bind:value={value.z_step_mm} min="0.01" step="0.01" />
  </div>

  <div class="area-info">
    {Math.abs(xSpan).toFixed(1)} x {Math.abs(ySpan).toFixed(1)} mm
    {#if xSpan < 0 || ySpan < 0}<span>signed</span>{/if}
  </div>
</fieldset>

<style>
  fieldset { display: flex; flex-direction: column; gap: 0.5rem; }
  .row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
  .row label { min-width: 7rem; }
  .sep { color: var(--muted); font-size: 11px; }
  input[type="number"] { width: 4.5rem; }
  .area-info {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    text-align: right;
  }
  .area-info span { color: var(--warn); margin-left: 0.35rem; }
</style>
