<script lang="ts">
  import MissionJogPanel from '$lib/components/MissionJogPanel.svelte';
  import MissionProgressPanel from '$lib/components/MissionProgressPanel.svelte';
  import ScopeCapture from '$lib/components/ScopeCapture.svelte';
  import { activeCampaign } from '$lib/stores/campaign';
  import { countersStore } from '$lib/stores/counters';
  import { positionStore } from '$lib/stores/position';
  import { armStore } from '$lib/stores/arm';
</script>

<div class="mission">
  <div class="actionbar">
    <div class="campaign-id">
      <span class="section-label">// campaign</span>
      <strong>{$activeCampaign?.campaign_id ?? 'standby'}</strong>
    </div>

    <div class="quick-links">
      <a href="/campaign">Campaign builder</a>
      <a href="/assembly">Target instructions</a>
      <a href="/runs">Replay runs</a>
    </div>

    <div class="state-tags">
      <span class="tag" class:red={$armStore.armed}>{$armStore.armed ? 'ARMED' : 'SAFE'}</span>
    </div>
  </div>

  <div class="mission-body">
    <MissionJogPanel />
    <MissionProgressPanel />
    <main class="hero">
      <ScopeCapture />
    </main>
  </div>

  <footer class="statusline">
    <span><em>host</em> emfi bench</span>
    <span><em>pos</em> X{$positionStore.x.toFixed(3)} Y{$positionStore.y.toFixed(3)} Z{$positionStore.z.toFixed(3)}</span>
    <span><em>attempts</em> {$countersStore.attempts}</span>
    <span><em>success</em> {$countersStore.glitches}</span>
    <span><em>yield</em> {($countersStore.attempts - ($countersStore.unobserved ?? 0)) > 0 ? (($countersStore.glitches / ($countersStore.attempts - ($countersStore.unobserved ?? 0))) * 100).toFixed(1) : '0.0'}%</span>
  </footer>
</div>

<style>
  .mission {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--ink-1);
  }

  .actionbar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.65rem 1rem;
    background: var(--ink-0);
    border-bottom: 1px solid var(--line);
  }

  .campaign-id {
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 0.7rem;
  }

  .campaign-id strong {
    max-width: 34vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--fg-1);
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 500;
  }

  .quick-links {
    display: flex;
    gap: 0.35rem;
    padding: 0.2rem;
    background: var(--ink-2);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }

  .quick-links a {
    padding: 0.4rem 0.65rem;
    color: var(--fg-2);
    border-radius: 2px;
    font-size: 12px;
    font-weight: 700;
    text-decoration: none;
    white-space: nowrap;
  }

  .quick-links a:hover {
    color: var(--fg-1);
    background: var(--ink-4);
    text-decoration: none;
  }

  .state-tags {
    margin-left: auto;
    display: flex;
    gap: 0.45rem;
    min-width: 0;
  }

  .mission-body {
    flex: 1;
    min-height: 0;
    display: flex;
  }

  .hero {
    flex: 1;
    min-width: 0;
    min-height: 0;
    padding: 0.9rem 1rem;
    display: flex;
  }

  .statusline {
    flex-shrink: 0;
    height: 31px;
    display: flex;
    align-items: center;
    overflow-x: auto;
    background: var(--ink-0);
    border-top: 1px solid var(--line);
    color: var(--fg-3);
    font-family: var(--mono);
    font-size: 10.5px;
    white-space: nowrap;
  }

  .statusline span {
    height: 100%;
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0 0.9rem;
    border-right: 1px solid var(--line-faint);
  }

  .statusline em {
    color: var(--fg-4);
    font-style: normal;
  }

  @media (max-width: 980px) {
    .actionbar {
      align-items: flex-start;
      flex-direction: column;
      gap: 0.65rem;
    }

    .quick-links {
      max-width: 100%;
      overflow-x: auto;
    }

    .campaign-id strong {
      max-width: 84vw;
    }

    .state-tags {
      margin-left: 0;
      flex-wrap: wrap;
    }

    .mission {
      overflow: auto;
    }

    .mission-body {
      flex-direction: column;
      overflow: visible;
    }

    .hero {
      min-height: 520px;
    }
  }
</style>
