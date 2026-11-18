<script lang="ts">
  import { page } from '$app/stores';
  import { base } from '$app/paths';

  $: relativePath = $page.url.pathname.slice(base.length) || '/';
  $: segments = relativePath.split('/').filter(Boolean);
  $: projectId = segments[0] === 'projects' && segments[1] ? segments[1] : null;
</script>

<div class="app">
  <header>
    <div class="brand">
      <a href="{base}/">EMFI Develop</a>
    </div>
    <nav>
      <a href="{base}/" class:active={relativePath === '/'}>Projects</a>
      {#if projectId}
        <span class="sep">/</span>
        <a href="{base}/projects/{projectId}" class:active={segments.length === 2}>{projectId}</a>
        <span class="sep">/</span>
        <a href="{base}/projects/{projectId}/asm" class:active={segments[2] === 'asm'}>Assembly</a>
      {/if}
    </nav>
  </header>

  <main>
    <slot />
  </main>
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #222;
    background: #fafafa;
  }
  .app { display: flex; flex-direction: column; height: 100vh; }
  header {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 0 1rem;
    height: 44px;
    background: #1a1a2e;
    color: #fff;
    flex-shrink: 0;
  }
  .brand a {
    color: #fff;
    text-decoration: none;
    font-weight: 700;
    font-size: 0.95rem;
  }
  nav { display: flex; align-items: center; gap: 0.5rem; }
  nav a {
    color: #aab;
    text-decoration: none;
    font-size: 0.85rem;
    padding: 2px 6px;
    border-radius: 3px;
  }
  nav a:hover { color: #fff; }
  nav a.active { color: #fff; background: rgba(255,255,255,0.15); }
  .sep { color: #555; font-size: 0.8rem; }
  main { flex: 1; overflow: hidden; }
</style>
