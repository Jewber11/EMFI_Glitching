<script lang="ts">
  export let onClear: () => void;
</script>

<div class="overlay" role="dialog" aria-modal="true" aria-label="Emergency stop engaged">
  <div class="hazard-border"></div>
  <div class="content">
    <div class="octagon">×</div>
    <div class="eyebrow">EMERGENCY STOP ENGAGED</div>
    <h1>System safe.<br /><span>Armed output off.</span></h1>
    <p>
      High-voltage pulse disabled. Stage motion halted. The active campaign has been suspended.
      Confirm the bench is clear before re-enabling hardware.
    </p>
    <div class="safe-row">
      <span><b></b> PULSE OFF</span>
      <span><b></b> MOTION HALTED</span>
      <span><b></b> DUT ISOLATED</span>
    </div>
    <button class="clear" on:click={onClear}>Clear E-stop and re-enable</button>
    <small>requires bench-clear confirmation</small>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 200;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(6, 7, 8, 0.92);
    backdrop-filter: blur(6px);
  }

  .hazard-border {
    position: absolute;
    inset: 0;
    border: 10px solid transparent;
    border-image: repeating-linear-gradient(45deg, var(--red) 0 22px, #1a1300 22px 44px) 10;
    opacity: 0.9;
    pointer-events: none;
  }

  .content {
    position: relative;
    width: min(560px, calc(100vw - 2rem));
    padding: 2rem;
    text-align: center;
  }

  .octagon {
    width: 92px;
    height: 92px;
    margin: 0 auto 1.8rem;
    display: grid;
    place-items: center;
    color: var(--red-bright);
    border: 4px solid var(--red);
    border-radius: 50%;
    box-shadow: var(--glow-red);
    font-size: 56px;
    font-weight: 300;
    line-height: 1;
    animation: ff-pulse-red 1.2s infinite;
  }

  .eyebrow {
    margin-bottom: 0.9rem;
    color: var(--red-bright);
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.28em;
  }

  h1 {
    margin: 0;
    color: var(--fg-1);
    font-size: clamp(38px, 7vw, 56px);
    line-height: 1.02;
    letter-spacing: 0;
  }

  h1 span {
    color: var(--red-bright);
  }

  p {
    margin: 1.2rem auto 0;
    max-width: 500px;
    color: var(--fg-2);
    font-size: 15px;
    line-height: 1.6;
  }

  .safe-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.95rem;
    margin-top: 1.8rem;
    color: var(--fg-3);
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.1em;
  }

  .safe-row span {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }

  .safe-row b {
    width: 8px;
    height: 8px;
    display: inline-block;
    background: var(--red-bright);
  }

  .clear {
    margin-top: 2rem;
    padding: 0.75rem 1.2rem;
    color: #1a1300;
    background: var(--gold);
    border-color: transparent;
    font-weight: 700;
  }

  .clear:hover {
    background: var(--gold-bright);
    box-shadow: var(--glow-gold);
  }

  small {
    display: block;
    margin-top: 0.9rem;
    color: var(--fg-4);
    font-family: var(--mono);
    font-size: 11px;
  }
</style>
