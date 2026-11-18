<script lang="ts">
  import { goto } from '$app/navigation';
  import { browser } from '$app/environment';
  import { positionStore } from '$lib/stores/position';
  import { armStore } from '$lib/stores/arm';
  import { home, moveAbs, saveCurrentFixture, setOrigin, setTopRight } from '$lib/api/control';
  import { toasts } from '$lib/stores/toast';
  import JogPad from '$lib/components/JogPad.svelte';
  import Scene3D from '$lib/components/Scene3D.svelte';

  type Step = 1 | 2 | 3 | 4;
  let step: Step = 1;

  let originX: number | null = null;
  let originY: number | null = null;
  let originZ: number | null = null;
  let topRightX: number | null = null;
  let topRightY: number | null = null;

  let busy = false;
  let savingFixture = false;
  let homed = false;

  // Smallest meaningful jog — below this we treat the probe as "still at origin".
  const EPS = 0.01;

  // Step 2 gate: after set_origin the logical frame is reset to (0,0,0), so if the
  // user hasn't jogged, both logical X and Y are within EPS of zero. Block "Set as
  // top-right" in that case — otherwise top_right == origin and grids collapse to Z-only.
  $: atOrigin =
    Math.abs($positionStore.x ?? 0) < EPS && Math.abs($positionStore.y ?? 0) < EPS;

  $: scanBox =
    step === 4 && originX != null && originY != null && topRightX != null && topRightY != null
      ? {
          width: Math.max(Math.abs(topRightX - originX), 0.1),
          height: Math.max(Math.abs(topRightY - originY), 0.1),
          depth: 0.5,
        }
      : step >= 2 && originX != null && originY != null
      ? {
          width: Math.max(Math.abs(($positionStore.x ?? 0) - originX), 0.1),
          height: Math.max(Math.abs(($positionStore.y ?? 0) - originY), 0.1),
          depth: 0.5,
        }
      : null;

  // Signed scan dimensions (opposite corner minus origin). Negative spans are valid
  // for backside/reversed setups; campaigns will scan in that signed direction.
  $: width = originX != null && topRightX != null ? topRightX - originX : null;
  $: height = originY != null && topRightY != null ? topRightY - originY : null;
  $: absWidth = width == null ? null : Math.abs(width);
  $: absHeight = height == null ? null : Math.abs(height);

  $: collapsed = absWidth != null && absHeight != null && (absWidth < 0.01 || absHeight < 0.01);
  $: smallAreaWarning =
    absWidth != null && absHeight != null && !collapsed && (absWidth < 5 || absHeight < 5);
  $: reversedWarning = width != null && height != null && (width < 0 || height < 0);

  // Implied grid-point count at the campaign default 1 mm step, for the "looks good" badge.
  $: nXY =
    absWidth != null && absHeight != null
      ? (Math.ceil(absWidth / 1) + 1) * (Math.ceil(absHeight / 1) + 1)
      : null;

  function gotoStep(s: Step) {
    // Allow stepping back; only forward through buttons (which gate on data presence).
    if (s <= step) step = s;
  }

  async function homeAndAdvance() {
    busy = true;
    try {
      await home();
      homed = true;
      originX = originY = originZ = topRightX = topRightY = null;
      toasts.info('Ender 3 homed; choose die origin');
      step = 2;
    } catch {
      toasts.error('home failed');
    } finally {
      busy = false;
    }
  }

  async function setOriginAndAdvance() {
    if (!homed) {
      toasts.warn('Home before assigning die endpoints');
      step = 1;
      return;
    }
    busy = true;
    try {
      await setOrigin();
      originX = $positionStore.x ?? 0;
      originY = $positionStore.y ?? 0;
      originZ = $positionStore.z ?? 0;
      toasts.info(`Die origin set at (${originX.toFixed(2)}, ${originY.toFixed(2)})`);
      step = 3;
    } catch {
      toasts.error('set_origin failed');
    } finally {
      busy = false;
    }
  }

  async function setTopRightAndAdvance() {
    busy = true;
    try {
      const x = $positionStore.x ?? 0;
      const y = $positionStore.y ?? 0;
      await setTopRight(x, y);
      topRightX = x;
      topRightY = y;
      toasts.info(`Die opposite corner set at (${x.toFixed(2)}, ${y.toFixed(2)})`);
      step = 4;
    } catch {
      toasts.error('set_top_right failed');
    } finally {
      busy = false;
    }
  }

  async function jogToOrigin() {
    if (originX == null || originY == null) return;
    try {
      await moveAbs(originX, originY, originZ ?? $positionStore.z ?? 0);
      toasts.info('Jogging to origin…');
    } catch {
      toasts.error('Jog to origin failed');
    }
  }

  function clearStaleCalibration() {
    // Drop any persisted calibration from a previous session so the campaign form
    // can't silently inherit yesterday's origin/top-right. Scoped to calibration
    // keys only — never a blanket localStorage.clear().
    if (!browser) return;
    try {
      for (const k of Object.keys(localStorage)) {
        if (k === 'calibration' || k.startsWith('emfi.calibration') || k.startsWith('calib.')) {
          localStorage.removeItem(k);
        }
      }
    } catch {
      /* localStorage unavailable (private mode / disabled) — non-fatal */
    }
  }

  async function finish() {
    if (originX == null || originY == null || topRightX == null || topRightY == null) return;
    await saveDefaultFixture();
    clearStaleCalibration();
    const qs = new URLSearchParams({
      origin_x: String(originX),
      origin_y: String(originY),
      top_right_x: String(topRightX),
      top_right_y: String(topRightY),
    });
    goto(`/campaign?${qs.toString()}`);
  }

  async function saveDefaultFixture() {
    savingFixture = true;
    try {
      await saveCurrentFixture({
        name: 'default-chip',
        step_size_mm: 1.0,
        z_min_mm: 0.0,
        z_max_mm: 0.5,
        z_step_mm: 0.1,
        notes: 'Default die map saved from calibration wizard',
      });
      toasts.info('Default die map saved');
    } catch {
      toasts.error('Save die map failed');
    } finally {
      savingFixture = false;
    }
  }
</script>

<div class="page">
  <h2>Die map calibration</h2>

  {#if $armStore.armed}
    <div class="arm-warning">
      ⚠ ARM is engaged. Calibration normally runs disarmed — disengage ARM unless you know why you need it hot.
    </div>
  {/if}

  <div class="tabs">
    <button class="tab" class:active={step === 1} on:click={() => gotoStep(1)}>
      1. Home {#if homed}<span class="check">✓</span>{/if}
    </button>
    <button class="tab" class:active={step === 2} on:click={() => gotoStep(2)} disabled={!homed}>
      2. First corner {#if originX != null}<span class="check">✓</span>{/if}
    </button>
    <button class="tab" class:active={step === 3} on:click={() => gotoStep(3)} disabled={originX == null}>
      3. Opposite corner {#if topRightX != null}<span class="check">✓</span>{/if}
    </button>
    <button class="tab" class:active={step === 4} on:click={() => gotoStep(4)} disabled={topRightX == null}>
      4. Confirm
    </button>
  </div>

  <div class="layout">
    <div class="instructions">
      {#if step === 1}
        <h3>Home the stage</h3>
        <p>
          Home Ender 3 before assigning die endpoints. Homing gives the
          bolted-down board a repeatable machine frame; the saved die map can
          be restored after future homes.
        </p>

        <div class="panel">
          <h4>Current position</h4>
          <div class="pos-readout">
            <span>X <b>{$positionStore.x?.toFixed(2) ?? '—'}</b></span>
            <span>Y <b>{$positionStore.y?.toFixed(2) ?? '—'}</b></span>
            <span>Z <b>{$positionStore.z?.toFixed(2) ?? '—'}</b></span>
          </div>
        </div>

        <button class="primary" on:click={homeAndAdvance} disabled={busy}>
          {busy ? 'Homing...' : 'Home stage'}
        </button>
      {:else if step === 2}
        <h3>Set first die corner</h3>
        <p>
          Use the jog pad to position the FaultyCat tip over the
          <strong>first corner</strong> of the chip die map.
        </p>
        <p class="hint">Tip: jog Z up first to avoid crashing into the bed.</p>

        <div class="panel">
          <h4>Current position</h4>
          <div class="pos-readout">
            <span>X <b>{$positionStore.x?.toFixed(2) ?? '—'}</b></span>
            <span>Y <b>{$positionStore.y?.toFixed(2) ?? '—'}</b></span>
            <span>Z <b>{$positionStore.z?.toFixed(2) ?? '—'}</b></span>
          </div>
        </div>

        <div class="panel">
          <h4>Jog</h4>
          <JogPad />
        </div>

        <button class="primary" on:click={setOriginAndAdvance} disabled={busy}>
          {busy ? 'Setting...' : 'Set first corner'}
        </button>
      {:else if step === 3}
        <h3>Set opposite die corner</h3>
        <p>
          Now jog to the <strong>opposite corner</strong> of the die. This
          endpoint defines the default scan box used by autonomous campaigns.
        </p>

        <div class="panel">
          <h4>Current position</h4>
          <div class="pos-readout live">
            <span>X <b>{$positionStore.x?.toFixed(2) ?? '—'}</b></span>
            <span>Y <b>{$positionStore.y?.toFixed(2) ?? '—'}</b></span>
            <span>Z <b>{$positionStore.z?.toFixed(2) ?? '—'}</b></span>
          </div>
          <div class="pos-readout sub">
            <span>First corner: ({originX?.toFixed(2)}, {originY?.toFixed(2)})</span>
            <span>
              Δ from origin: ({(($positionStore.x ?? 0) - (originX ?? 0)).toFixed(2)},
              {(($positionStore.y ?? 0) - (originY ?? 0)).toFixed(2)})
            </span>
          </div>
        </div>

        <div class="panel">
          <h4>Jog</h4>
          <JogPad />
        </div>

        {#if atOrigin}
          <p class="warn-inline">
            ⚠ Still at the first corner (0, 0). Jog to the opposite corner before setting —
            otherwise the scan grid collapses to a single column.
          </p>
        {/if}
        <button
          class="primary"
          on:click={setTopRightAndAdvance}
          disabled={busy || atOrigin}
          title={atOrigin ? 'Jog at least 0.01 mm away from origin first.' : ''}
        >
          {busy ? 'Setting...' : 'Set opposite corner'}
        </button>
      {:else}
        <h3>Confirm</h3>
        <p>Review the die map. Continuing saves it as the default fixture, then opens campaign config.</p>

        <div class="panel">
          <h4>Summary</h4>
          <table class="summary">
            <tr><th>First corner</th><td>({originX?.toFixed(2)}, {originY?.toFixed(2)})</td></tr>
            <tr><th>Opposite corner</th><td>({topRightX?.toFixed(2)}, {topRightY?.toFixed(2)})</td></tr>
            <tr>
              <th>Grid size</th>
              <td>
                {absWidth?.toFixed(2)} mm × {absHeight?.toFixed(2)} mm
                {#if absWidth != null && absHeight != null}
                  <span class="area">= {(absWidth * absHeight).toFixed(2)} mm²</span>
                {/if}
              </td>
            </tr>
          </table>
        </div>

        <div class="panel">
          <h4>Scan area</h4>
          <p class="scan-dims">Scan area: {absWidth?.toFixed(2)} × {absHeight?.toFixed(2)} mm</p>
          {#if collapsed}
            <div class="banner warning">
              One axis is nearly zero. Saving is allowed, but campaigns will collapse to a row or column.
            </div>
          {:else if smallAreaWarning}
            <div class="banner warning">
              Small die map. This is allowed for backside work; confirm the endpoints before launching a campaign.
            </div>
          {:else if reversedWarning}
            <div class="banner warning">
              Opposite corner is in a negative direction. This is allowed; campaigns will scan signed X/Y.
            </div>
          {:else}
            <div class="badge ok">Looks good</div>
          {/if}
          <p class="grid-est">≈ {nXY} grid points at the 1 mm default step</p>
        </div>

        <div class="actions">
          <button on:click={jogToOrigin}>Jog to origin (test)</button>
          <button on:click={saveDefaultFixture} disabled={savingFixture}>
            {savingFixture ? 'Saving...' : 'Save default die map'}
          </button>
          <button class="primary" on:click={finish}>
            Save → Campaign
          </button>
        </div>
      {/if}
    </div>

    <div class="scene-wrap">
      <Scene3D {scanBox} />
    </div>
  </div>
</div>

<style>
  .page { padding: 1rem 1.5rem; height: 100%; display: flex; flex-direction: column; }
  h2 { margin-bottom: 0.5rem; }
  h3 { margin: 0 0 0.5rem; color: var(--accent); }
  h4 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin-bottom: 0.4rem;
    font-weight: 500;
  }

  .arm-warning {
    background: rgba(249, 168, 37, 0.12);
    border: 1px solid var(--warn);
    color: var(--warn);
    padding: 0.5rem 0.75rem;
    border-radius: var(--radius);
    margin-bottom: 0.5rem;
    font-size: 12px;
  }

  .tabs {
    display: flex;
    gap: 0.25rem;
    margin-bottom: 0.75rem;
    border-bottom: 1px solid var(--border);
  }
  .tab {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 0.5rem 1rem;
    color: var(--muted);
    font-size: 12px;
  }
  .tab:hover:not(:disabled) { color: var(--fg); background: var(--panel-2); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab .check { color: var(--ok); margin-left: 0.3rem; }

  .layout {
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: 1rem;
    flex: 1;
    min-height: 0;
  }

  .instructions {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    overflow-y: auto;
  }
  .instructions p { color: var(--fg); font-size: 13px; line-height: 1.5; }
  .instructions p.hint { color: var(--muted); font-size: 11px; font-style: italic; }
  .instructions strong { color: var(--accent); }

  .pos-readout {
    display: flex;
    gap: 1rem;
    font-family: var(--mono);
    font-size: 14px;
  }
  .pos-readout b { color: var(--accent); }
  .pos-readout.live { font-size: 20px; }
  .pos-readout.sub {
    font-size: 11px;
    color: var(--muted);
    margin-top: 0.3rem;
    flex-wrap: wrap;
  }

  .instructions p.warn-inline {
    color: var(--warn);
    font-size: 12px;
    margin: 0;
  }

  .scan-dims {
    font-family: var(--mono);
    font-size: 14px;
    color: var(--fg);
    margin: 0 0 0.5rem;
  }
  .banner.warning {
    background: rgba(249, 168, 37, 0.12);
    border: 1px solid var(--warn);
    color: var(--warn);
    padding: 0.5rem 0.75rem;
    border-radius: var(--radius);
    font-size: 12px;
  }
  .badge.ok {
    display: inline-block;
    background: rgba(0, 200, 83, 0.15);
    border: 1px solid var(--ok);
    color: var(--ok);
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }
  .grid-est {
    color: var(--muted);
    font-size: 11px;
    margin: 0.4rem 0 0;
  }

  .scene-wrap {
    min-height: 400px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .summary { font-family: var(--mono); font-size: 12px; width: 100%; }
  .summary th {
    text-align: left;
    color: var(--muted);
    font-weight: 400;
    padding: 0.25rem 0.75rem 0.25rem 0;
    font-size: 11px;
    text-transform: uppercase;
  }
  .summary td { padding: 0.25rem 0; color: var(--fg); }
  .summary .area { color: var(--muted); font-size: 11px; margin-left: 0.4rem; }

  .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }

  button.primary {
    background: var(--accent);
    color: var(--bg);
    border-color: var(--accent);
    font-weight: 700;
    padding: 0.5rem 1rem;
  }
  button.primary:hover:not(:disabled) { filter: brightness(1.1); }
  button.primary:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
