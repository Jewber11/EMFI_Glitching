<script lang="ts">
  import { moveRel, home } from '$lib/api/control';
  import { toasts } from '$lib/stores/toast';

  let step = 1.0;

  async function jog(axis: string, dir: number) {
    try {
      await moveRel(axis, step * dir);
    } catch {
      toasts.error(`Jog ${axis} failed`);
    }
  }

  async function doHome() {
    try {
      await home();
      toasts.info('Homing…');
    } catch {
      toasts.error('Home failed');
    }
  }
</script>

<div class="jog-panel">
  <div class="step-row">
    <label>Step (mm)</label>
    <input type="number" bind:value={step} min="0.01" step="0.1" />
  </div>
  <div class="pad">
    <div class="xy-grid">
      <div></div>
      <button on:click={() => jog('Y', 1)}>Y+</button>
      <div></div>
      <button on:click={() => jog('X', -1)}>X-</button>
      <button class="home-btn" on:click={doHome} title="Home all axes">H</button>
      <button on:click={() => jog('X', 1)}>X+</button>
      <div></div>
      <button on:click={() => jog('Y', -1)}>Y-</button>
      <div></div>
    </div>
    <div class="z-col">
      <button on:click={() => jog('Z', 1)}>Z+</button>
      <button on:click={() => jog('Z', -1)}>Z-</button>
    </div>
  </div>
</div>

<style>
  .jog-panel { display: flex; flex-direction: column; gap: 0.5rem; }
  .step-row { display: flex; align-items: center; gap: 0.5rem; }
  .step-row input { width: 4.5rem; }
  .pad { display: flex; gap: 0.5rem; align-items: center; }
  .xy-grid {
    display: grid;
    grid-template-columns: repeat(3, 2.2rem);
    grid-template-rows: repeat(3, 2.2rem);
    gap: 3px;
  }
  .xy-grid button, .z-col button {
    width: 2.2rem;
    height: 2.2rem;
    padding: 0;
    font-size: 11px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .home-btn {
    background: var(--accent) !important;
    color: var(--bg) !important;
    font-weight: 700;
  }
  .z-col {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
</style>
