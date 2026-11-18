<script lang="ts">
  import {
    scaffoldPowerGet,
    scaffoldPowerSet,
    scaffoldPowerCycle,
    type ScaffoldRail
  } from '$lib/api/control';
  import { scaffoldPowerStore } from '$lib/stores/scaffold_power';
  import { devicesStore } from '$lib/stores/devices';
  import { toasts } from '$lib/stores/toast';

  let busy: Record<ScaffoldRail, boolean> = { dut: false, platform: false, all: false };
  let wasConnected = false;
  const rails: Array<{ rail: 'dut' | 'platform'; label: string; sublabel: string }> = [
    { rail: 'dut', label: 'DUT', sublabel: 'slot 1' },
    { rail: 'platform', label: 'Platform', sublabel: 'slot 2' },
  ];

  $: scaffoldConnected = $devicesStore.get('scaffold')?.connected ?? false;

  $: {
    if (scaffoldConnected && !wasConnected) {
      wasConnected = true;
      refresh();
    } else if (!scaffoldConnected && wasConnected) {
      wasConnected = false;
      scaffoldPowerStore.set({ dut: false, platform: false });
    }
  }

  async function refresh() {
    try {
      const state = await scaffoldPowerGet();
      scaffoldPowerStore.set(state);
    } catch {
      // Silent — disconnected adapter will surface via the device card already.
    }
  }

  async function toggle(rail: 'dut' | 'platform') {
    if (busy[rail] || !scaffoldConnected) return;
    busy[rail] = true;
    const next = !$scaffoldPowerStore[rail];
    try {
      const state = await scaffoldPowerSet(rail, next);
      scaffoldPowerStore.set(state);
      toasts.info(`${rail.toUpperCase()} ${next ? 'on' : 'off'}`);
    } catch {
      toasts.error(`Failed to set ${rail} power`);
    } finally {
      busy[rail] = false;
    }
  }

  async function cycle(rail: ScaffoldRail) {
    if (busy[rail] || !scaffoldConnected) return;
    busy[rail] = true;
    try {
      const state = await scaffoldPowerCycle(rail);
      scaffoldPowerStore.set(state);
      toasts.info(`${rail === 'all' ? 'Both rails' : rail.toUpperCase()} power-cycled`);
    } catch {
      toasts.error(`Failed to cycle ${rail}`);
    } finally {
      busy[rail] = false;
    }
  }
</script>

<div class="card" class:offline={!scaffoldConnected}>
  {#if !scaffoldConnected}
    <p class="offline-msg">Scaffold offline - connect to control power rails.</p>
  {:else}
    {#each rails as r}
      <div class="rail" class:on={$scaffoldPowerStore[r.rail]}>
        <div class="rail-head">
          <span class="dot" class:on={$scaffoldPowerStore[r.rail]}></span>
          <div class="rail-name">
            <span class="label">{r.label}</span>
            <span class="sub">{r.sublabel}</span>
          </div>
          <span class="state-text">{$scaffoldPowerStore[r.rail] ? 'ON' : 'OFF'}</span>
        </div>

        <div class="rail-actions">
          <button
            class="toggle"
            class:on={$scaffoldPowerStore[r.rail]}
            disabled={busy[r.rail]}
            on:click={() => toggle(r.rail)}
            title={$scaffoldPowerStore[r.rail] ? 'Power off' : 'Power on'}
          >
            <span class="track">
              <span class="thumb"></span>
            </span>
            <span class="toggle-label">{$scaffoldPowerStore[r.rail] ? 'Switch off' : 'Switch on'}</span>
          </button>

          <button
            class="cycle"
            disabled={busy[r.rail] || !$scaffoldPowerStore[r.rail]}
            on:click={() => cycle(r.rail)}
            title="Power off, wait 50 ms, power on"
          >
            Cycle
          </button>
        </div>
      </div>
    {/each}

    <div class="all-row">
      <button
        class="all-btn"
        disabled={busy.all}
        on:click={() => cycle('all')}
      >
        Cycle both rails
      </button>
    </div>
  {/if}
</div>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .offline {
    opacity: 0.7;
  }
  .offline-msg {
    font-size: 11px;
    color: var(--muted);
    font-style: italic;
  }

  .rail {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.55rem 0.65rem;
    transition: border-color 120ms ease, box-shadow 120ms ease;
  }
  .rail.on {
    border-color: rgba(0, 209, 143, 0.45);
    box-shadow: 0 0 0 1px rgba(0, 209, 143, 0.08) inset;
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
    background: var(--ok);
    box-shadow: 0 0 6px var(--ok);
  }
  .rail-name {
    display: flex;
    flex-direction: column;
    line-height: 1.15;
    flex: 1;
  }
  .label {
    font-weight: 700;
    font-size: 12px;
  }
  .sub {
    color: var(--muted);
    font-size: 10px;
    font-family: var(--mono);
  }
  .state-text {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    color: var(--muted);
    letter-spacing: 0.05em;
  }
  .rail.on .state-text { color: var(--ok); }

  .rail-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.3rem 0.5rem;
    color: var(--fg);
    font-size: 11px;
    cursor: pointer;
    flex: 1;
    transition: border-color 120ms ease;
  }
  .toggle:hover:not(:disabled) { border-color: var(--accent); }
  .toggle:disabled { opacity: 0.5; cursor: not-allowed; }

  .track {
    position: relative;
    width: 26px;
    height: 14px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    flex-shrink: 0;
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
    background: rgba(0, 209, 143, 0.18);
    border-color: var(--ok);
  }
  .toggle.on .thumb {
    background: var(--ok);
    transform: translateX(12px);
  }
  .toggle-label {
    font-family: var(--mono);
  }

  .cycle, .all-btn {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.3rem 0.55rem;
    color: var(--muted);
    font-size: 11px;
    font-family: var(--mono);
    cursor: pointer;
    transition: border-color 120ms ease, color 120ms ease;
  }
  .cycle:hover:not(:disabled), .all-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--fg);
  }
  .cycle:disabled, .all-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .all-row {
    display: flex;
    justify-content: stretch;
  }
  .all-btn { width: 100%; padding: 0.4rem; }
</style>
