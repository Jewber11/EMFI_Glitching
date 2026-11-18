<script lang="ts">
  export let value = 0;
  export let max = 100;
  $: pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
</script>

<div class="progress">
  <div class="track">
    <div class="fill" style="width: {pct}%"></div>
  </div>
  <span class="label">{value} / {max}</span>
</div>

<style>
  .progress { display: flex; align-items: center; gap: 0.5rem; }
  .track {
    flex: 1;
    height: 8px;
    background: var(--panel-2);
    border-radius: 4px;
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--accent);
    border-radius: 4px;
    transition: width 0.3s ease;
  }
  .label {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
  }
</style>
