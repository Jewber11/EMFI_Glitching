<script lang="ts">
  import { onMount } from 'svelte';
  import { shouterArm, shouterDisarm, shouterStatus, shouterPulse } from '$lib/api/control';
  import { armStore } from '$lib/stores/arm';
  import { devicesStore } from '$lib/stores/devices';
  import { toasts } from '$lib/stores/toast';

  let busy = false;
  let widthUs = 5;
  let armed = false;
  let state = 'unknown';
  let lastError = '';

  $: connected = $devicesStore.get('chipshouter')?.connected ?? false;

  onMount(() => {
    refresh();
  });

  async function refresh() {
    if (!connected) return;
    try {
      const status = await shouterStatus();
      armed = Boolean(status.armed);
      state = String(status.state ?? (armed ? 'armed' : 'disarmed'));
      lastError = String(status.last_error ?? '');
    } catch {
      lastError = 'status unavailable';
    }
  }

  async function fire() {
    busy = true;
    try {
      await shouterPulse(widthUs * 1000);
      toasts.info("FaultyCat pulse fired");
    } catch (err) { toasts.error(`Pulse failed: ${err}`); }
    finally { busy = false; }
  }

  async function toggle() {
    if (busy || !connected) return;
    busy = true;
    lastError = '';
    try {
      const result = armed ? await shouterDisarm() : await shouterArm();
      armed = !armed;
      state = String(result.state ?? (armed ? 'armed' : 'disarmed'));
      toasts.info(`FaultyCat ${armed ? 'armed' : 'disarmed'}`);
      await refresh();
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
      toasts.error(`FaultyCat ${armed ? 'disarm' : 'arm'} failed`);
      await refresh();
    } finally {
      busy = false;
    }
  }
</script>

<div class="card" class:offline={!connected} class:armed>
  <div class="rail-head">
    <span class="dot" class:on={armed}></span>
    <div class="rail-name">
      <span class="label">FaultyCat</span>
      <span class="sub">software enable</span>
    </div>
    <span class="state-text">{armed ? 'ARMED' : state.toUpperCase()}</span>
  </div>

  {#if !connected}
    <p class="offline-msg">FaultyCat offline.</p>
  {:else}
    <button
      class="toggle"
      class:on={armed}
      disabled={busy}
      on:click={toggle}
      title={armed ? 'Disarm FaultyCat' : 'Arm FaultyCat'}
    >
      <span class="track">
        <span class="thumb"></span>
      </span>
      <span class="toggle-label">{armed ? 'Disarm' : 'Arm'}</span>
    </button>
    <label>Pulse width (µs) <input type="number" bind:value={widthUs} min="1" max="50" step="1" /></label>
    <button on:click={fire} disabled={busy || !armed || !$armStore.armed}>Fire pulse</button>
    {#if lastError}
      <p class="error">{lastError}</p>
    {/if}
  {/if}
</div>

<style>
  .card {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.55rem 0.65rem;
    transition: border-color 120ms ease, box-shadow 120ms ease;
  }

  .card.armed {
    border-color: rgba(229, 41, 58, 0.5);
    box-shadow: 0 0 0 1px rgba(229, 41, 58, 0.1) inset;
  }

  .offline {
    opacity: 0.7;
  }

  .rail-head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--muted);
    transition: background 120ms ease, box-shadow 120ms ease;
    flex-shrink: 0;
  }

  .dot.on {
    background: var(--red-bright);
    box-shadow: 0 0 8px var(--red-bright);
  }

  .rail-name {
    display: flex;
    flex: 1;
    flex-direction: column;
    line-height: 1.15;
  }

  .label {
    font-size: 12px;
    font-weight: 700;
  }

  .sub,
  .state-text,
  .toggle-label,
  .offline-msg,
  .error {
    font-family: var(--mono);
  }

  .sub {
    color: var(--muted);
    font-size: 10px;
  }

  .state-text {
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
  }

  .armed .state-text {
    color: var(--red-bright);
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.3rem 0.5rem;
    color: var(--fg);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 11px;
    transition: border-color 120ms ease;
  }

  .toggle:hover:not(:disabled) {
    border-color: var(--red-bright);
  }

  .toggle:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .track {
    position: relative;
    flex-shrink: 0;
    width: 26px;
    height: 14px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    transition: background 140ms ease, border-color 140ms ease;
  }

  .thumb {
    position: absolute;
    top: 1px;
    left: 1px;
    width: 10px;
    height: 10px;
    background: var(--muted);
    border-radius: 50%;
    transition: transform 160ms cubic-bezier(0.4, 0, 0.2, 1), background 140ms ease;
  }

  .toggle.on .track {
    background: rgba(229, 41, 58, 0.16);
    border-color: var(--red-bright);
  }

  .toggle.on .thumb {
    background: var(--red-bright);
    transform: translateX(12px);
  }

  .offline-msg,
  .error {
    margin: 0;
    color: var(--muted);
    font-size: 10px;
  }

  .error {
    margin-top: 0.45rem;
    color: var(--red-bright);
    overflow-wrap: anywhere;
  }
</style>
