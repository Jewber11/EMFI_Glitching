<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { FileTreeNode } from '$lib/types';

  export let node: FileTreeNode | null = null;
  export let depth = 0;

  const dispatch = createEventDispatcher<{ select: string }>();

  let expanded: Record<string, boolean> = {};

  function toggle(name: string) {
    expanded[name] = !expanded[name];
  }

  function selectFile(path: string) {
    dispatch('select', path);
  }
</script>

{#if node}
  {#if node.type === 'dir'}
    {#if depth > 0}
      <button class="dir" on:click={() => toggle(node?.name ?? '')}>
        <span class="icon">{expanded[node.name] ? '▼' : '▶'}</span>
        {node.name}/
      </button>
    {/if}
    {#if depth === 0 || expanded[node.name]}
      <ul class:root={depth === 0}>
        {#each node.children ?? [] as child}
          <li>
            <svelte:self node={child} depth={depth + 1} on:select />
          </li>
        {/each}
      </ul>
    {/if}
  {:else}
    <button class="file" on:click={() => selectFile(node?.path ?? '')}>
      {node.name}
    </button>
  {/if}
{:else}
  <p class="muted">Loading…</p>
{/if}

<style>
  ul { list-style: none; padding-left: 1rem; margin: 0; }
  ul.root { padding-left: 0; }
  li { margin: 0; }
  button {
    all: unset;
    cursor: pointer;
    display: block;
    padding: 2px 4px;
    font-family: monospace;
    font-size: 0.85rem;
    width: 100%;
    border-radius: 3px;
  }
  button:hover { background: #e8e8e8; }
  .dir { font-weight: 600; }
  .icon { display: inline-block; width: 1em; text-align: center; font-size: 0.7em; }
  .file { color: #333; }
  .muted { color: #999; font-size: 0.85rem; }
</style>
