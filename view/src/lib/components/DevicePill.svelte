<script lang="ts">
  import type { DeviceStatus } from '$lib/stores/devices';
  import DeviceStatusCard from './DeviceStatusCard.svelte';

  export let device: DeviceStatus;

  // Status priority: error > busy > connected > unavailable
  $: status =
    device.last_error
      ? 'err'
      : device.busy
      ? 'busy'
      : device.connected
      ? 'ok'
      : device.available
      ? 'off'
      : 'unavailable';

  $: hasFaults = Array.isArray(device.faults) && device.faults.length > 0;
  $: showVoltage =
    device.name === 'chipshouter' &&
    (device.voltage_v != null || device.voltage_measured_v != null);
</script>

<div class="pill-wrap">
  <div class="pill" class:err={status === 'err'} class:busy={status === 'busy'}>
    <span class="dot {status}"></span>
    <span class="name">{device.name}</span>

    {#if showVoltage}
      <span class="voltage">
        {#if device.voltage_measured_v != null && device.voltage_v != null}
          {Math.round(device.voltage_measured_v)}/{device.voltage_v}V
        {:else if device.voltage_v != null}
          {device.voltage_v}V
        {:else if device.voltage_measured_v != null}
          {Math.round(device.voltage_measured_v)}V
        {/if}
      </span>
    {/if}

    {#if hasFaults}
      <span class="faults" title={device.faults?.join(', ')}>⚠ {device.faults?.length}</span>
    {/if}
  </div>

  <div class="tooltip">
    <DeviceStatusCard {device} />
    {#if hasFaults}
      <div class="tooltip-faults">
        <div class="tooltip-label">Faults</div>
        <ul>
          {#each device.faults ?? [] as f}<li>{f}</li>{/each}
        </ul>
      </div>
    {/if}
    {#if showVoltage}
      <div class="tooltip-voltage">
        {#if device.voltage_v != null}<div><span class="tooltip-label">Set</span> {device.voltage_v} V</div>{/if}
        {#if device.voltage_measured_v != null}<div><span class="tooltip-label">Measured</span> {device.voltage_measured_v.toFixed(1)} V</div>{/if}
        {#if device.state}<div><span class="tooltip-label">State</span> {device.state}</div>{/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .pill-wrap {
    position: relative;
    display: inline-block;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.55rem;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 11px;
    cursor: default;
    line-height: 1;
  }
  .pill.err { border-color: rgba(255, 82, 82, 0.5); }
  .pill.busy { border-color: rgba(249, 168, 37, 0.5); }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .dot.ok { background: var(--ok); box-shadow: 0 0 5px var(--ok); }
  .dot.err { background: var(--err); box-shadow: 0 0 5px var(--err); animation: pulse 1.2s ease-in-out infinite; }
  .dot.busy { background: var(--warn); box-shadow: 0 0 5px var(--warn); }
  .dot.off { background: var(--muted); }
  .dot.unavailable { background: #444; border: 1px dashed #666; }
  .name { font-weight: 600; }
  .voltage {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--accent);
    padding-left: 0.2rem;
    border-left: 1px solid var(--border);
    margin-left: 0.1rem;
    padding-left: 0.4rem;
  }
  .faults {
    color: var(--err);
    font-size: 10px;
    font-weight: 700;
  }

  .tooltip {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.5rem;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5);
    min-width: 220px;
    z-index: 100;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.1s;
  }
  .pill-wrap:hover .tooltip {
    opacity: 1;
  }
  .tooltip-label {
    font-size: 9px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-right: 0.4rem;
  }
  .tooltip-faults, .tooltip-voltage {
    margin-top: 0.4rem;
    padding-top: 0.4rem;
    border-top: 1px solid var(--border);
    font-size: 11px;
    font-family: var(--mono);
  }
  .tooltip-faults ul { list-style: none; padding: 0; margin: 0.2rem 0 0; }
  .tooltip-faults li {
    color: var(--err);
    padding: 0.1rem 0;
  }
  .tooltip-voltage div { padding: 0.1rem 0; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
</style>
