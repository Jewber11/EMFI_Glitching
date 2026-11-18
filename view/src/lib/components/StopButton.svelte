<script lang="ts">
  import { onMount } from 'svelte';

  export let onStop: () => void = () => {};

  onMount(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onStop();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });
</script>

<button class="stop-btn" on:click={onStop}>STOP</button>

<style>
  .stop-btn {
    padding: 0.6rem 1.5rem;
    background: var(--err);
    color: #fff;
    border: 2px solid #d32f2f;
    font-weight: 800;
    font-size: 14px;
    border-radius: var(--radius);
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    transition: background 0.15s;
  }
  .stop-btn:hover { background: #d32f2f; }
  .stop-btn:active { background: #b71c1c; }
</style>
