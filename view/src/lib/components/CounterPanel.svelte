<script lang="ts">
  import { countersStore } from '$lib/stores/counters';

  $: pct = $countersStore.attempts > 0
    ? (($countersStore.glitches / $countersStore.attempts) * 100).toFixed(1)
    : '0.0';
</script>

<div class="counters">
  <div class="row"><span class="lbl">Attempts</span><span class="val">{$countersStore.attempts}</span></div>
  <div class="row ok"><span class="lbl">Faults</span><span class="val">{$countersStore.glitches}</span></div>
  <div class="row hang"><span class="lbl">Hangs</span><span class="val">{$countersStore.hangs}</span></div>
  <div class="row crash"><span class="lbl">Crashes</span><span class="val">{$countersStore.crashes}</span></div>
  <div class="row nothing"><span class="lbl">Nothing</span><span class="val">{$countersStore.nothings}</span></div>
  <div class="row campaigns"><span class="lbl">Campaigns</span><span class="val">{$countersStore.campaigns}</span></div>
  <div class="row success"><span class="lbl">Success</span><span class="val">{pct}%</span></div>
</div>

<style>
  .counters { display: flex; flex-direction: column; gap: 0.25rem; }
  .row {
    display: flex;
    justify-content: space-between;
    font-family: var(--mono);
    font-size: 13px;
    padding: 0.15rem 0;
  }
  .lbl { color: var(--muted); }
  .val { font-weight: 600; }
  .ok .val { color: var(--ok); }
  .hang .val { color: var(--err); }
  .crash .val { color: var(--warn); }
  .nothing .val { color: var(--muted); }
  .success .val { color: var(--accent); font-size: 18px; font-weight: 700; }
  .success .lbl { font-size: 14px; }
</style>
