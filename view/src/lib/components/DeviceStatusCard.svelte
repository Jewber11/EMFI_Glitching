<script lang="ts">
  export let device: {
    name: string;
    available: boolean;
    connected: boolean;
    port: string | null;
    label: string | null;
    last_error: string | null;
    busy: boolean;
  };

  $: status = device.connected ? 'ok' : device.last_error ? 'err' : 'off';
</script>

<div class="device" title={device.last_error ?? ''}>
  <span class="dot {status}"></span>
  <span class="name">{device.name}</span>
  {#if device.connected}
    <span class="port">{device.port ?? ''}</span>
  {/if}
  {#if device.busy}
    <span class="busy">busy</span>
  {/if}
</div>

<style>
  .device {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.5rem;
    background: var(--panel-2);
    border-radius: 4px;
    font-size: 11px;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .dot.ok { background: var(--ok); box-shadow: 0 0 4px var(--ok); }
  .dot.err { background: var(--err); box-shadow: 0 0 4px var(--err); }
  .dot.off { background: var(--muted); }
  .name { font-weight: 600; }
  .port { color: var(--muted); font-family: var(--mono); font-size: 10px; }
  .busy { color: var(--warn); font-size: 10px; }
</style>
