<script lang="ts">
  export let value = {
    delay_us: null as { start: number; stop: number; step: number } | null,
    pulse_width_ns: null as { start: number; stop: number; step: number } | null,
    voltage_v: null as { start: number; stop: number; step: number } | null,
    attempts_per_point: 1
  };


  let pulseEnabled = false;


  let pulseStart = 1000, pulseStop = 10000, pulseStep = 1000;

  $: value.delay_us = null;
  $: value.pulse_width_ns = pulseEnabled ? { start: pulseStart, stop: pulseStop, step: pulseStep } : null;
  $: value.voltage_v = null;
</script>

<fieldset>
  <legend>Sweep Parameters</legend>

  <div class="sweep-row">
    <label class="toggle">
      <input type="checkbox" bind:checked={pulseEnabled} />
      Pulse width (ns)
    </label>
    {#if pulseEnabled}
      <input type="number" bind:value={pulseStart} min="1000" max="50000" step="1000" />
      <span class="sep">-</span>
      <input type="number" bind:value={pulseStop} min="1000" max="50000" step="1000" />
      <span class="sep">step</span>
      <input type="number" bind:value={pulseStep} min="1000" step="1000" />
    {/if}
  </div>

  <div class="sweep-row">
    <label>Attempts / point</label>
    <input type="number" bind:value={value.attempts_per_point} min="1" step="1" />
  </div>
</fieldset>

<style>
  fieldset { display: flex; flex-direction: column; gap: 0.5rem; }
  .sweep-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
  }
  .toggle { display: flex; align-items: center; gap: 0.3rem; min-width: 10rem; cursor: pointer; }
  .sep { color: var(--muted); font-size: 11px; }
  input[type="number"] { width: 4.5rem; }
</style>
