<script lang="ts">
  import { armStore } from '$lib/stores/arm';
  import { arm, disarm } from '$lib/api/control';
  import { toasts } from '$lib/stores/toast';

  export let holdMs = 1000;

  let pressing = false;
  let progress = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let progressInterval: ReturnType<typeof setInterval> | null = null;

  function start() {
    if ($armStore.armed) {
      disarm().catch(() => toasts.error('Disarm failed'));
      return;
    }
    pressing = true;
    progress = 0;
    progressInterval = setInterval(() => {
      progress = Math.min(progress + 100 / (holdMs / 50), 100);
    }, 50);
    timer = setTimeout(async () => {
      if (pressing) {
        try { await arm(); } catch { toasts.error('Arm failed'); }
      }
      end();
    }, holdMs);
  }

  function end() {
    pressing = false;
    progress = 0;
    if (timer) { clearTimeout(timer); timer = null; }
    if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }
  }
</script>

<button
  class="arm-btn"
  class:armed={$armStore.armed}
  class:pressing
  on:mousedown={start} on:mouseup={end} on:mouseleave={end}
  on:touchstart|preventDefault={start} on:touchend={end}
>
  {#if pressing}
    <div class="progress-ring" style="--pct: {progress}%"></div>
  {/if}
  <span class="label">{$armStore.armed ? 'DISARM' : 'Hold to ARM'}</span>
</button>

<style>
  .arm-btn {
    position: relative;
    padding: 0.5rem 1.2rem;
    font-weight: 700;
    font-size: 13px;
    border-radius: var(--radius);
    border: 2px solid var(--warn);
    background: transparent;
    color: var(--warn);
    cursor: pointer;
    overflow: hidden;
    min-width: 8rem;
  }
  .arm-btn.armed {
    background: var(--err);
    color: #fff;
    border-color: var(--err);
    animation: pulse-border 1.5s ease-in-out infinite;
  }
  .arm-btn.pressing {
    border-color: var(--accent);
  }
  .progress-ring {
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, var(--accent) var(--pct), transparent var(--pct));
    opacity: 0.15;
  }
  .label { position: relative; z-index: 1; }
  @keyframes pulse-border {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255, 82, 82, 0.4); }
    50% { box-shadow: 0 0 0 6px rgba(255, 82, 82, 0); }
  }
</style>
