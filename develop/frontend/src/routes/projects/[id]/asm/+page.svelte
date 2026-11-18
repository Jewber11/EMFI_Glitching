<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import AssemblyView from '$lib/components/AssemblyView.svelte';
  import { listBuilds, getDisassembly, listTargets, addTarget, removeTarget } from '$lib/api';
  import type { AssemblyListing, BuildArtifact, GlitchTarget } from '$lib/types';

  $: id = $page.params.id as string;

  let builds: BuildArtifact[] = [];
  let selectedSha = '';
  let listing: AssemblyListing | null = null;
  let targets: GlitchTarget[] = [];
  let loading = false;
  let error = '';

  let showDialog = false;
  let dialogPc = 0;
  let dialogMnemonic = '';
  let dialogFn = '';
  let targetName = '';
  let targetNotes = '';
  let targetCycles: number | undefined;

  onMount(async () => {
    try {
      [builds, targets] = await Promise.all([listBuilds(id), listTargets(id)]);
      if (builds.length > 0) {
        selectedSha = builds[0].sha;
        await loadDisassembly();
      }
    } catch (e: any) { error = e.message; }
  });

  async function loadDisassembly() {
    if (!selectedSha) return;
    loading = true;
    error = '';
    try {
      listing = await getDisassembly(id, selectedSha);
    } catch (e: any) { error = e.message; }
    loading = false;
  }

  function onSelect(ev: CustomEvent<{ pc: number; mnemonic: string; function: string | null }>) {
    dialogPc = ev.detail.pc;
    dialogMnemonic = ev.detail.mnemonic;
    dialogFn = ev.detail.function ?? '';
    targetName = dialogFn ? `${dialogFn}+0x${dialogPc.toString(16)}` : `0x${dialogPc.toString(16)}`;
    targetNotes = '';
    targetCycles = undefined;
    showDialog = true;
  }

  async function doAddTarget() {
    try {
      await addTarget(id, {
        pc_address: dialogPc,
        name: targetName,
        expected_delay_cycles: targetCycles,
        notes: targetNotes || undefined,
        created_at: new Date().toISOString(),
      });
      targets = await listTargets(id);
      showDialog = false;
    } catch (e: any) { error = e.message; }
  }

  async function doRemoveTarget(pc: number) {
    if (!confirm(`Remove target at 0x${pc.toString(16)}?`)) return;
    try {
      await removeTarget(id, pc);
      targets = await listTargets(id);
    } catch (e: any) { error = e.message; }
  }

  function hex(n: number): string { return '0x' + n.toString(16).padStart(8, '0'); }
</script>

<div class="asm-page">
  <!-- Top bar -->
  <div class="top-bar">
    <div class="controls">
      <label>
        Build:
        <select bind:value={selectedSha} on:change={loadDisassembly}>
          {#each builds as b}
            <option value={b.sha}>{b.sha} ({b.success ? 'ok' : 'fail'}) — {new Date(b.built_at).toLocaleString()}</option>
          {/each}
        </select>
      </label>
      {#if loading}
        <span class="muted">Loading…</span>
      {/if}
    </div>
    {#if listing}
      <span class="muted">{listing.instructions.length} instructions | {listing.cpu_mhz} MHz</span>
    {/if}
  </div>

  {#if error}
    <div class="error">{error}</div>
  {/if}

  <div class="asm-layout">
    <!-- Main: assembly listing -->
    <div class="listing-panel">
      <AssemblyView {listing} {targets} on:select-instruction={onSelect} />
    </div>

    <!-- Sidebar: targets -->
    <div class="targets-panel">
      <div class="targets-header">Targets ({targets.length})</div>
      <div class="targets-list">
        {#each targets as t}
          <div class="target-card">
            <div class="target-top">
              <strong>{t.name}</strong>
              <button class="btn-x" on:click={() => doRemoveTarget(t.pc_address)}>✕</button>
            </div>
            <div class="target-meta">{hex(t.pc_address)}</div>
            {#if t.expected_delay_cycles}
              <div class="target-meta">{t.expected_delay_cycles} cycles</div>
            {/if}
            {#if t.notes}
              <div class="target-notes">{t.notes}</div>
            {/if}
          </div>
        {/each}
        {#if targets.length === 0}
          <p class="muted">Click an instruction to add a target.</p>
        {/if}
      </div>
    </div>
  </div>

  <!-- Add target dialog -->
  {#if showDialog}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="overlay" on:click|self={() => showDialog = false}>
      <div class="dialog">
        <h3>Add Glitch Target</h3>
        <p class="dialog-meta">Address: {hex(dialogPc)} — <code>{dialogMnemonic}</code></p>
        <label>
          Name
          <input type="text" bind:value={targetName} />
        </label>
        <label>
          Expected delay (cycles)
          <input type="number" bind:value={targetCycles} placeholder="Optional" />
        </label>
        <label>
          Notes
          <textarea bind:value={targetNotes} rows={2} placeholder="Optional"></textarea>
        </label>
        <div class="dialog-actions">
          <button class="btn" on:click={() => showDialog = false}>Cancel</button>
          <button class="btn primary" on:click={doAddTarget} disabled={!targetName.trim()}>Add Target</button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .asm-page { display: flex; flex-direction: column; height: 100%; }
  .top-bar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 12px; background: #f5f5f5; border-bottom: 1px solid #ddd;
  }
  .controls { display: flex; align-items: center; gap: 0.75rem; }
  .controls label { font-size: 0.85rem; display: flex; align-items: center; gap: 0.4rem; }
  .controls select { padding: 4px 8px; border: 1px solid #ccc; border-radius: 3px; font-size: 0.82rem; }
  .error { background: #fee; color: #c00; padding: 4px 12px; font-size: 0.85rem; }
  .muted { color: #999; font-size: 0.8rem; }

  .asm-layout { display: grid; grid-template-columns: 1fr 260px; flex: 1; overflow: hidden; }
  .listing-panel { overflow: auto; }
  .targets-panel {
    border-left: 1px solid #ddd; display: flex; flex-direction: column; overflow: hidden;
  }
  .targets-header {
    padding: 8px 12px; font-weight: 600; font-size: 0.85rem;
    background: #f5f5f5; border-bottom: 1px solid #ddd;
  }
  .targets-list { flex: 1; overflow-y: auto; padding: 8px; }
  .target-card {
    padding: 8px; margin-bottom: 6px;
    background: #fff8e0; border: 1px solid #e8d88c; border-radius: 4px;
  }
  .target-top { display: flex; justify-content: space-between; align-items: flex-start; }
  .target-top strong { font-size: 0.85rem; }
  .target-meta { font-size: 0.75rem; color: #666; font-family: monospace; }
  .target-notes { font-size: 0.78rem; color: #555; margin-top: 4px; }
  .btn-x { all: unset; cursor: pointer; color: #999; font-size: 0.8rem; padding: 0 4px; }
  .btn-x:hover { color: #c00; }

  .overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 100;
    display: flex; align-items: center; justify-content: center;
  }
  .dialog {
    background: #fff; border-radius: 8px; padding: 1.5rem; width: 380px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  }
  .dialog h3 { margin: 0 0 0.5rem; font-size: 1.1rem; }
  .dialog-meta { font-size: 0.85rem; color: #666; margin-bottom: 1rem; }
  .dialog label { display: flex; flex-direction: column; gap: 4px; font-size: 0.82rem; color: #555; margin-bottom: 0.75rem; }
  .dialog input, .dialog textarea {
    padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem;
  }
  .dialog-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem; }
  .btn {
    padding: 6px 14px; border: 1px solid #ccc; border-radius: 4px;
    background: #fff; cursor: pointer; font-size: 0.85rem;
  }
  .btn:hover { background: #f5f5f5; }
  .btn.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
  .btn.primary:hover { background: #1d4ed8; }
  .btn.primary:disabled { opacity: 0.5; cursor: default; }
</style>
