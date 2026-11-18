<script lang="ts">
  import { toasts } from '$lib/stores/toast';
  import { fly } from 'svelte/transition';
</script>

<div class="toast-container">
  {#each $toasts as t (t.id)}
    <button
      class="toast {t.level}"
      transition:fly={{ x: 200, duration: 250 }}
      on:click={() => toasts.dismiss(t.id)}
    >
      {#if t.where}<span class="where">{t.where}</span>{/if}
      <span class="msg">{t.message}</span>
    </button>
  {/each}
</div>

<style>
  .toast-container {
    position: fixed;
    bottom: 5rem;
    right: 1.5rem;
    z-index: 10000;
    display: flex;
    flex-direction: column-reverse;
    gap: 0.4rem;
    max-width: 400px;
    pointer-events: none;
  }
  .toast {
    pointer-events: auto;
    background: var(--panel);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: 0.5rem 0.75rem;
    font-size: 12px;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .toast.warn { border-left-color: var(--warn); }
  .toast.error { border-left-color: var(--err); }
  .where {
    background: var(--panel-2);
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-size: 10px;
    text-transform: uppercase;
    color: var(--muted);
    flex-shrink: 0;
  }
</style>
