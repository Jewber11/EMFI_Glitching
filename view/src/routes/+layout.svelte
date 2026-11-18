<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { armStore } from '$lib/stores/arm';
  import { devicesStore, KNOWN_DEVICES, placeholderStatus, type DeviceStatus } from '$lib/stores/devices';
  import { activeCampaign } from '$lib/stores/campaign';
  import Toast from '$lib/components/Toast.svelte';
  import EStopOverlay from '$lib/components/EStopOverlay.svelte';
  import { stopCampaign, disarm } from '$lib/api/control';
  import { DEVELOP_SITE_URL } from '$lib/config';
  import { connect } from '$lib/ws/control_ws';
  import { toasts } from '$lib/stores/toast';

  let estopEngaged = false;

  const labels: Record<string, string> = {
    chipshover: 'Ender 3',
    chipshouter: 'FaultyCat',
    scaffold: 'Scaffold',
    xds110: 'XDS110',
    ad2: 'AD2',
  };

  $: statusLights = KNOWN_DEVICES.map((n) => $devicesStore.get(n) ?? placeholderStatus(n));
  $: currentPath = $page.url.pathname;

  onMount(() => {
    connect();
  });

  function deviceState(device: DeviceStatus) {
    if (estopEngaged) return 'offline';
    if (device.last_error || device.busy) return 'warn';
    if (device.connected) return 'online';
    return 'offline';
  }

  async function handleEstop() {
    estopEngaged = true;
    try {
      const camp = $activeCampaign;
      if (camp?.active) await stopCampaign(camp.campaign_id);
      await disarm();
      toasts.warn('E-STOP engaged: outputs disarmed');
    } catch {
      toasts.error('E-STOP command failed');
    }
  }

  function clearEstop() {
    estopEngaged = false;
    toasts.info('E-STOP overlay cleared');
  }
</script>

<div class="app-shell">
  <header class="topbar">
    <a href="/" class="brand" aria-label="EMFI Control Mission">
      <span class="brand-mark"></span>
      <span>EMFI<b>Control</b></span>
    </a>

    <nav aria-label="Primary">
      <a href="/" class:active={currentPath === '/'}>Mission</a>
      <a href="/calibrate" class:active={currentPath === '/calibrate'}>Calibrate</a>
      <a href="/runs" class:active={currentPath === '/runs'}>Run History</a>
      <a href="/heatmap" class:active={currentPath === '/heatmap'}>Heatmap</a>
      <a href="/firmware" class:active={currentPath === '/firmware'}>Firmware</a>
      <a href={DEVELOP_SITE_URL} target="_blank" rel="noreferrer">Develop ↗</a>
    </nav>

    <div class="status-strip" aria-label="Device status">
      {#each statusLights as device (device.name)}
        <div class="status-light" class:online={deviceState(device) === 'online'} class:warn={deviceState(device) === 'warn'} title={`${labels[device.name] ?? device.name}: ${deviceState(device)}`}>
          <span></span>
          <em>{labels[device.name] ?? device.name}</em>
        </div>
      {/each}
    </div>

    <div class="safe-state" class:armed={$armStore.armed}>
      {#if $armStore.armed}
        ARMED
        {#if $armStore.seconds_until_auto_disarm != null}
          <small>{Math.ceil($armStore.seconds_until_auto_disarm)}s</small>
        {/if}
      {:else}
        SAFE
      {/if}
    </div>

    <button class="estop" class:active={estopEngaged} on:click={handleEstop}>
      <span></span>
      E-STOP
    </button>
  </header>

  <main>
    <slot />
  </main>
</div>

{#if estopEngaged}
  <EStopOverlay onClear={clearEstop} />
{/if}

<Toast />

<style>
  .app-shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
    background: var(--ink-1);
  }

  .topbar {
    height: 54px;
    flex-shrink: 0;
    display: flex;
    align-items: stretch;
    background: rgba(6, 7, 8, 0.86);
    border-bottom: 1px solid var(--line);
    backdrop-filter: blur(10px);
    z-index: 30;
  }

  .brand {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0 1rem;
    color: var(--fg-1);
    border-right: 1px solid var(--line);
    text-decoration: none;
    font-size: 14px;
    font-weight: 700;
  }

  .brand:hover {
    text-decoration: none;
  }

  .brand b {
    color: var(--gold);
    font-weight: 700;
  }

  .brand-mark {
    width: 23px;
    height: 23px;
    display: inline-block;
    border: 2px solid var(--gold);
    border-radius: 50%;
    box-shadow: inset 0 0 0 5px var(--ink-0), 0 0 14px rgba(240, 188, 44, 0.18);
  }

  nav {
    display: flex;
    align-items: stretch;
    min-width: 0;
  }

  nav a {
    display: flex;
    align-items: center;
    padding: 0 1rem;
    color: var(--fg-3);
    border-bottom: 2px solid transparent;
    text-decoration: none;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
  }

  nav a:hover {
    color: var(--fg-1);
    background: var(--ink-2);
    text-decoration: none;
  }

  nav a.active {
    color: var(--fg-1);
    background: var(--ink-2);
    border-bottom-color: var(--gold);
  }

  .status-strip {
    margin-left: auto;
    display: flex;
    align-items: stretch;
    min-width: 0;
  }

  .status-light {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0 0.7rem;
    border-left: 1px solid var(--line-faint);
    color: var(--fg-4);
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .status-light span {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--fg-4);
    flex-shrink: 0;
  }

  .status-light.online {
    color: var(--fg-2);
  }

  .status-light.online span {
    background: var(--scope-green);
    box-shadow: 0 0 7px var(--scope-green);
  }

  .status-light.warn {
    color: var(--gold);
  }

  .status-light.warn span {
    background: var(--gold);
    box-shadow: 0 0 7px var(--gold);
    animation: ff-pulse-red 1.4s infinite;
  }

  .safe-state {
    min-width: 68px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.25rem;
    padding: 0 0.7rem;
    color: var(--fg-3);
    border-left: 1px solid var(--line);
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
  }

  .safe-state.armed {
    color: #fff;
    background: var(--red);
    animation: ff-pulse-red 1s steps(1) infinite;
  }

  .safe-state small {
    font-size: 9px;
    letter-spacing: 0;
  }

  .estop {
    height: 100%;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0 1.25rem;
    color: #fff;
    background: var(--red);
    border: 0;
    border-left: 1px solid var(--line);
    border-radius: 0;
    font-weight: 800;
    letter-spacing: 0.08em;
  }

  .estop:hover {
    background: var(--red-bright);
    box-shadow: var(--glow-red);
  }

  .estop.active {
    background: var(--red-deep);
  }

  .estop span {
    width: 16px;
    height: 16px;
    display: inline-block;
    border: 3px solid #fff;
    border-radius: 50%;
    box-shadow: inset 0 0 0 3px var(--red);
  }

  main {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }

  @media (max-width: 1120px) {
    .status-light em {
      display: none;
    }

    nav a {
      padding: 0 0.7rem;
    }
  }

  @media (max-width: 780px) {
    .topbar {
      height: auto;
      min-height: 54px;
      flex-wrap: wrap;
    }

    .brand {
      order: 1;
      height: 54px;
    }

    .status-strip {
      order: 2;
      height: 54px;
      margin-left: auto;
    }

    .safe-state {
      order: 3;
      height: 54px;
      min-width: 60px;
    }

    .estop {
      order: 4;
      height: 54px;
      padding: 0 1rem;
    }

    nav {
      order: 10;
      width: 100%;
      overflow-x: auto;
      border-top: 1px solid var(--line);
    }

    nav a {
      height: 42px;
    }

    main {
      min-height: 0;
    }
  }
</style>
