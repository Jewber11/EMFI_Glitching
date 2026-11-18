<script lang="ts">
  import { onMount } from 'svelte';
  import { devices, connectDevice } from '$lib/api/control';
  import { devicesStore } from '$lib/stores/devices';
  import { toasts } from '$lib/stores/toast';

  let ports: { device: string; label: string }[] = [];
  let printerPort = '';
  let catPort = '';
  let busy = false;

  async function refresh() {
    try {
      const result = await devices();
      ports = result.ports ?? [];
    } catch (err) { toasts.error(`Port scan failed: ${err}`); }
  }

  async function connect(name: string, port: string) {
    busy = true;
    try {
      await connectDevice(name, port || undefined);
      toasts.info(`${name === 'chipshover' ? 'Ender 3' : 'FaultyCat'} connected`);
      await refresh();
    } catch (err) { toasts.error(`Connection failed: ${err}`); }
    finally { busy = false; }
  }
  onMount(refresh);
</script>

<div class="rig">
  <div class="head"><strong>Devices</strong><button on:click={refresh} disabled={busy}>Refresh ports</button></div>
  <label>Ender 3 — {$devicesStore.get('chipshover')?.connected ? 'connected' : 'offline'}
    <select bind:value={printerPort} aria-label="Ender 3 serial port">
      <option value="">Auto-detect</option>
      {#each ports as port}<option value={port.device}>{port.label}</option>{/each}
    </select>
  </label>
  <button on:click={() => connect('chipshover', printerPort)} disabled={busy}>Connect printer</button>
  <label>FaultyCat — {$devicesStore.get('chipshouter')?.connected ? 'connected' : 'offline'}
    <select bind:value={catPort} aria-label="FaultyCat EMFI serial port">
      <option value="">Auto-detect EMFI interface</option>
      {#each ports as port}<option value={port.device}>{port.label}</option>{/each}
    </select>
  </label>
  <button on:click={() => connect('chipshouter', catPort)} disabled={busy}>Connect FaultyCat</button>
</div>

<style>
  .rig { display: flex; flex-direction: column; gap: .4rem; }
  .head { display: flex; justify-content: space-between; align-items: center; }
  label { display: flex; flex-direction: column; gap: .25rem; font-size: 12px; }
  select { width: 100%; }
</style>
