<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import Scene3D from '$lib/components/Scene3D.svelte';
  import LogTail from '$lib/components/LogTail.svelte';
  import ProgressBar from '$lib/components/ProgressBar.svelte';
  import { getCampaign, stopCampaign } from '$lib/api/control';
  import { activeCampaign } from '$lib/stores/campaign';
  import { toasts } from '$lib/stores/toast';

  $: id = $page.params.id ?? '';

  let campaign: any = null;

  onMount(async () => {
    if (!id) return;
    try {
      campaign = await getCampaign(id);
    } catch {
      toasts.warn('Could not load campaign details');
    }
  });

  async function stop() {
    if (!id) return;
    try {
      await stopCampaign(id);
      toasts.info('Campaign stopped');
    } catch {
      toasts.error('Stop failed');
    }
  }

  $: progress = $activeCampaign?.campaign_id === id ? $activeCampaign : null;
</script>

<div class="campaign-live">
  <div class="header-row">
    <h2>Campaign: {campaign?.name ?? id}</h2>
    {#if $activeCampaign?.active && $activeCampaign?.campaign_id === id}
      <button class="stop-btn" on:click={stop}>Stop</button>
    {/if}
  </div>

  {#if progress}
    <div class="panel progress-panel">
      <ProgressBar
        value={progress.completed_attempts}
        max={progress.total_attempts}
      />
    </div>
  {/if}

  <div class="split">
    <section class="scene-section">
      <Scene3D bedSize={100} />
    </section>
    <aside class="log-section">
      <div class="panel">
        <h3>Log</h3>
        <LogTail limit={200} />
      </div>
      {#if campaign}
        <div class="panel">
          <h3>Config</h3>
          <pre class="config-dump">{JSON.stringify(campaign, null, 2)}</pre>
        </div>
      {/if}
    </aside>
  </div>
</div>

<style>
  .campaign-live { padding: 0.75rem; height: 100%; display: flex; flex-direction: column; }
  .header-row { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.5rem; }
  .stop-btn {
    padding: 0.3rem 1rem;
    background: var(--err);
    color: #fff;
    border: none;
    font-weight: 700;
    border-radius: var(--radius);
    cursor: pointer;
  }
  .progress-panel { margin-bottom: 0.5rem; }
  .split { display: grid; grid-template-columns: 1fr 340px; gap: 0.5rem; flex: 1; min-height: 0; }
  .scene-section { min-height: 300px; }
  .log-section { display: flex; flex-direction: column; gap: 0.5rem; overflow-y: auto; }
  .config-dump {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    max-height: 200px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }
</style>
