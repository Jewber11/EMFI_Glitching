<script lang="ts">
  import { afterUpdate } from 'svelte';

  export let lines: string[] = [];

  let pre: HTMLPreElement;
  let autoScroll = true;

  const ANSI_RE = /\[[0-9;]*m/g;
  const MAX_LINES = 10000;

  function strip(line: string): string {
    return line.replace(ANSI_RE, '');
  }

  afterUpdate(() => {
    if (autoScroll && pre) {
      pre.scrollTop = pre.scrollHeight;
    }
  });

  $: trimmed = lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines;
</script>

<div class="log-container">
  <div class="log-header">
    <span>Build Log ({lines.length} lines)</span>
    <label>
      <input type="checkbox" bind:checked={autoScroll} /> Auto-scroll
    </label>
  </div>
  <pre bind:this={pre}>{#each trimmed as line}{strip(line)}
{/each}</pre>
</div>

<style>
  .log-container { display: flex; flex-direction: column; height: 100%; }
  .log-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 4px 8px; background: #1a1a1a; color: #aaa; font-size: 0.75rem;
  }
  .log-header label { cursor: pointer; }
  pre {
    flex: 1;
    background: #111;
    color: #eee;
    padding: 0.5rem;
    margin: 0;
    overflow-y: auto;
    font-size: 0.8rem;
    line-height: 1.4;
  }
</style>
