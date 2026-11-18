<script lang="ts">
  import JogPad from './JogPad.svelte';
  import RigConnections from './RigConnections.svelte';
  import ShouterArmToggle from './ShouterArmToggle.svelte';
  import { positionStore } from '$lib/stores/position';
  import { CONTROL_URL } from '$lib/config';

  let collapsed = false;
  $: healthHref = `${CONTROL_URL.replace(/\/$/, '')}/readyz`;
</script>

{#if collapsed}
  <aside class="rail">
    <button class="rail-btn" on:click={() => (collapsed = false)} aria-label="Expand stage control">
      <span>▸</span>
    </button>
    <div class="rail-label">Stage control</div>
  </aside>
{:else}
  <aside class="panel-shell">
    <div class="panel-head">
      <div>
        <div class="section-label">// mission control</div>
        <h2>Stage control</h2>
      </div>
      <button class="collapse" on:click={() => (collapsed = true)} aria-label="Collapse stage control">◂</button>
    </div>

    <section><RigConnections /></section>

    <section>
      <div class="section-label">// position · Ender 3</div>
      <div class="coords">
        <div class="coord gold">
          <span>X</span>
          <strong>{$positionStore.x.toFixed(3)}</strong>
          <em>mm</em>
        </div>
        <div class="coord cyan">
          <span>Y</span>
          <strong>{$positionStore.y.toFixed(3)}</strong>
          <em>mm</em>
        </div>
        <div class="coord red">
          <span>Z</span>
          <strong>{$positionStore.z.toFixed(3)}</strong>
          <em>mm</em>
        </div>
      </div>
    </section>

    <section>
      <div class="section-label">// jog</div>
      <JogPad />
    </section>

    <section>
      <div class="section-label">// pulse source</div>
      <ShouterArmToggle />
    </section>

    <div class="spacer"></div>

    <a class="health-link" href={healthHref} target="_blank" rel="noreferrer">
      <span class="health-icon">+</span>
      <span>
        <b>Health & status</b>
        <small>Control readiness JSON</small>
      </span>
      <em>↗</em>
    </a>
  </aside>
{/if}

<style>
  .panel-shell {
    width: 286px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
    background: var(--ink-0);
    border-right: 1px solid var(--line);
  }

  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1rem 0.8rem;
    border-bottom: 1px solid var(--line);
  }

  h2 {
    margin: 0.25rem 0 0;
    font-size: 15px;
    letter-spacing: 0;
  }

  .collapse,
  .rail-btn {
    width: 32px;
    height: 32px;
    padding: 0;
    display: grid;
    place-items: center;
    background: var(--ink-2);
    color: var(--fg-2);
    border-color: var(--line);
  }

  section {
    padding: 0 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }

  .coords {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.4rem;
  }

  .coord {
    min-width: 0;
    padding: 0.55rem 0.6rem;
    background: var(--ink-1);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    font-family: var(--mono);
  }

  .coord span {
    display: block;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
  }

  .coord strong {
    display: block;
    margin-top: 0.15rem;
    font-size: 14px;
    color: var(--fg-1);
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }

  .coord em {
    display: block;
    margin-top: 0.1rem;
    font-size: 9px;
    color: var(--fg-4);
    font-style: normal;
  }

  .coord.gold span { color: var(--gold); }
  .coord.cyan span { color: var(--scope-cyan); }
  .coord.red span { color: var(--red-bright); }

  .spacer {
    flex: 1;
    min-height: 0.5rem;
  }

  .health-link {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin: 0 1rem 1rem;
    padding: 0.75rem;
    background: var(--ink-2);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    color: var(--fg-1);
    text-decoration: none;
  }

  .health-link:hover {
    border-color: var(--line-strong);
    background: var(--ink-3);
    text-decoration: none;
  }

  .health-icon {
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
    color: var(--scope-green);
    border: 1px solid rgba(43, 213, 118, 0.35);
    border-radius: 50%;
    font-weight: 700;
    flex-shrink: 0;
  }

  .health-link span:nth-child(2) {
    flex: 1;
    display: flex;
    flex-direction: column;
    line-height: 1.15;
  }

  .health-link b {
    font-size: 12px;
  }

  .health-link small {
    margin-top: 0.2rem;
    color: var(--fg-4);
    font-family: var(--mono);
    font-size: 10px;
  }

  .health-link em {
    color: var(--fg-3);
    font-style: normal;
  }

  .rail {
    width: 44px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding-top: 1rem;
    background: var(--ink-0);
    border-right: 1px solid var(--line);
  }

  .rail-label {
    writing-mode: vertical-rl;
    color: var(--fg-4);
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  @media (max-width: 980px) {
    .panel-shell {
      width: 100%;
      max-height: 52vh;
      border-right: none;
      border-bottom: 1px solid var(--line);
    }

    .rail {
      display: none;
    }
  }
</style>
