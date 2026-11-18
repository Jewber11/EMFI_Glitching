<script lang="ts">
  import { onMount } from 'svelte';
  import {
    addTarget,
    listProjects,
    listBuilds,
    disassembly,
    listTargets,
    removeTarget
  } from '$lib/api/develop';
  import { toasts } from '$lib/stores/toast';

  type Instruction = {
    pc: number;
    bytes_hex?: string;
    mnemonic?: string;
    operands?: string;
    function?: string | null;
    source_file?: string | null;
    source_line?: number | null;
  };

  type GlitchTarget = {
    pc_address: number;
    pc_end?: number | null;
    name: string;
    expected_delay_cycles?: number | null;
    expected_delay_cycles_end?: number | null;
    notes?: string | null;
  };

  let projects: any[] = [];
  let selectedProject = '';
  let builds: any[] = [];
  let selectedBuild = '';
  let instructions: Instruction[] = [];
  let targets: GlitchTarget[] = [];
  let loading = false;
  let saving = false;
  let filter = '';
  let rangeMode = false;
  let selectedStartPc: number | null = null;
  let selectedEndPc: number | null = null;
  let targetName = '';
  let delayStartCycles: number | null = null;
  let delayEndCycles: number | null = null;
  let notes = '';

  onMount(async () => {
    try {
      projects = await listProjects();
    } catch {
      toasts.warn('Could not load projects — is Develop running?');
    }
  });

  async function onProjectChange() {
    builds = [];
    selectedBuild = '';
    instructions = [];
    targets = [];
    clearSelection();
    if (!selectedProject) return;
    try {
      const result = await listBuilds(selectedProject);
      builds = Array.isArray(result) ? result : result?.builds ?? [];
    } catch {
      toasts.warn('Could not load builds');
    }
  }

  async function loadDisassembly() {
    if (!selectedProject || !selectedBuild) return;
    loading = true;
    try {
      const result = await disassembly(selectedProject, selectedBuild);
      instructions = result?.instructions ?? [];
      targets = await listTargets(selectedProject);
      clearSelection();
    } catch {
      toasts.error('Failed to load disassembly');
      instructions = [];
      targets = [];
    } finally {
      loading = false;
    }
  }

  $: filtered = filter
    ? instructions.filter((i: any) =>
        i.mnemonic?.toLowerCase().includes(filter.toLowerCase()) ||
        i.function?.toLowerCase().includes(filter.toLowerCase()) ||
        ('0x' + i.pc.toString(16)).includes(filter.toLowerCase())
      )
    : instructions;

  $: orderedSelection =
    selectedStartPc == null
      ? null
      : {
          start: Math.min(selectedStartPc, selectedEndPc ?? selectedStartPc),
          end: Math.max(selectedStartPc, selectedEndPc ?? selectedStartPc)
        };
  $: selectedCount =
    orderedSelection == null
      ? 0
      : instructions.filter((inst) => inst.pc >= orderedSelection!.start && inst.pc <= orderedSelection!.end)
          .length;
  $: canSave =
    selectedProject !== '' &&
    selectedStartPc !== null &&
    (!rangeMode || (selectedEndPc !== null && selectedEndPc > selectedStartPc)) &&
    !saving;
  $: if (!rangeMode && selectedEndPc !== null) selectedEndPc = null;

  function formatPC(pc: number): string {
    return '0x' + pc.toString(16).padStart(8, '0');
  }

  function defaultTargetName(pc: number): string {
    return `target_${pc.toString(16).padStart(8, '0')}`;
  }

  function optionalInt(value: number | null): number | null {
    if (value == null || value === undefined || value === 0) return null;
    const parsed = Math.trunc(Number(value));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function clearSelection() {
    selectedStartPc = null;
    selectedEndPc = null;
    targetName = '';
    delayStartCycles = null;
    delayEndCycles = null;
    notes = '';
  }

  function setStart(pc: number) {
    selectedStartPc = pc;
    selectedEndPc = null;
    targetName = defaultTargetName(pc);
  }

  function setEnd(pc: number) {
    if (selectedStartPc == null || pc <= selectedStartPc) {
      setStart(pc);
      return;
    }
    selectedEndPc = pc;
  }

  function onInstructionClick(inst: Instruction, shiftKey = false) {
    if (rangeMode && selectedStartPc !== null && (shiftKey || selectedEndPc === null)) {
      setEnd(inst.pc);
      return;
    }
    setStart(inst.pc);
  }

  function targetForPc(pc: number): GlitchTarget | null {
    return (
      targets.find((target) => {
        const end = target.pc_end ?? target.pc_address;
        return pc >= target.pc_address && pc <= end;
      }) ?? null
    );
  }

  function isSelectedPc(pc: number): boolean {
    return orderedSelection !== null && pc >= orderedSelection.start && pc <= orderedSelection.end;
  }

  function targetRangeLabel(target: GlitchTarget): string {
    return target.pc_end && target.pc_end > target.pc_address
      ? `${formatPC(target.pc_address)}-${formatPC(target.pc_end)}`
      : formatPC(target.pc_address);
  }

  async function refreshTargets() {
    targets = await listTargets(selectedProject);
  }

  async function saveTarget() {
    if (!canSave || selectedStartPc == null) return;
    saving = true;
    try {
      const start = Math.min(selectedStartPc, selectedEndPc ?? selectedStartPc);
      const end = rangeMode && selectedEndPc != null ? Math.max(selectedStartPc, selectedEndPc) : null;
      await addTarget(selectedProject, {
        pc_address: start,
        pc_end: end && end > start ? end : null,
        name: targetName.trim() || defaultTargetName(start),
        expected_delay_cycles: optionalInt(delayStartCycles),
        expected_delay_cycles_end: end && end > start ? optionalInt(delayEndCycles) : null,
        notes: notes.trim() || null,
        created_at: new Date().toISOString()
      });
      await refreshTargets();
      clearSelection();
      toasts.info('Target saved');
    } catch {
      toasts.error('Failed to save target');
    } finally {
      saving = false;
    }
  }

  async function deleteTarget(target: GlitchTarget) {
    try {
      await removeTarget(selectedProject, target.pc_address);
      await refreshTargets();
      toasts.info('Target removed');
    } catch {
      toasts.error('Failed to remove target');
    }
  }
</script>

<div class="page">
  <h2>Assembly</h2>

  <div class="controls">
    <select bind:value={selectedProject} on:change={onProjectChange}>
      <option value="">Select project</option>
      {#each projects as p}
        <option value={p.id}>{p.name} ({p.language})</option>
      {/each}
    </select>
    <select bind:value={selectedBuild} disabled={builds.length === 0}>
      <option value="">Select build</option>
      {#each builds as b}
        <option value={b.sha ?? b}>{b.sha ?? b} {b.built_at ? `(${new Date(b.built_at).toLocaleDateString()})` : ''}</option>
      {/each}
    </select>
    <button on:click={loadDisassembly} disabled={loading || !selectedProject || !selectedBuild}>
      {loading ? 'Loading…' : 'Load'}
    </button>
    {#if instructions.length > 0}
      <input type="text" bind:value={filter} placeholder="Filter mnemonic/function/PC" class="filter" />
    {/if}
  </div>

  {#if instructions.length > 0}
    <div class="workspace">
      <div class="listing">
        <table>
          <thead>
            <tr>
              <th>PC</th>
              <th>Bytes</th>
              <th>Instruction</th>
              <th>Function</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {#each filtered as inst}
              {@const hitTarget = targetForPc(inst.pc)}
              <tr
                class:target={hitTarget !== null}
                class:range={hitTarget?.pc_end}
                class:selected={isSelectedPc(inst.pc)}
                on:click={(event) => onInstructionClick(inst, event.shiftKey)}
              >
                <td class="pc">{formatPC(inst.pc)}</td>
                <td class="bytes">{inst.bytes_hex}</td>
                <td class="asm">
                  <span class="mnemonic">{inst.mnemonic}</span>
                  {#if inst.operands}<span class="operands">{inst.operands}</span>{/if}
                </td>
                <td class="func">{inst.function ?? ''}</td>
                <td class="src">{inst.source_file ? `${inst.source_file}:${inst.source_line}` : ''}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <aside class="target-panel">
        <div class="target-editor">
          <div class="target-editor-head">
            <h3>Target</h3>
            <label><input type="checkbox" bind:checked={rangeMode} /> Range</label>
          </div>
          <div class="target-pcs">
            <span>{selectedStartPc == null ? 'start: -' : `start: ${formatPC(selectedStartPc)}`}</span>
            <span>{selectedEndPc == null ? 'end: -' : `end: ${formatPC(selectedEndPc)}`}</span>
            <span>{selectedCount} inst</span>
          </div>
          <div class="field">
            <label for="target-name">Name</label>
            <input id="target-name" type="text" bind:value={targetName} placeholder="target name" />
          </div>
          <div class="delay-grid">
            <div class="field">
              <label for="delay-start">Cycles</label>
              <input id="delay-start" type="number" bind:value={delayStartCycles} placeholder="auto" />
            </div>
            <div class="field">
              <label for="delay-end">End cycles</label>
              <input
                id="delay-end"
                type="number"
                bind:value={delayEndCycles}
                placeholder="auto"
                disabled={!rangeMode}
              />
            </div>
          </div>
          <div class="field">
            <label for="target-notes">Notes</label>
            <input id="target-notes" type="text" bind:value={notes} placeholder="optional" />
          </div>
          <div class="target-actions">
            <button on:click={saveTarget} disabled={!canSave}>{saving ? 'Saving...' : 'Save'}</button>
            <button on:click={clearSelection} disabled={selectedStartPc == null}>Clear</button>
          </div>
        </div>

        <div class="targets-list">
          <div class="targets-head">Targets ({targets.length})</div>
          {#each targets as target}
            <div class="target-row">
              <div>
                <b>{target.name}</b>
                <span>{targetRangeLabel(target)}</span>
              </div>
              <button on:click={() => deleteTarget(target)}>Remove</button>
            </div>
          {/each}
        </div>
      </aside>
    </div>
    <p class="info">{filtered.length} / {instructions.length} instructions. {targets.length} targets marked.</p>
  {:else if !loading}
    <p class="empty-msg">Select a project and build SHA to view disassembly.</p>
  {/if}
</div>

<style>
  .page { padding: 1rem 1.5rem; height: 100%; display: flex; flex-direction: column; }
  h2 { margin-bottom: 0.75rem; }
  .controls { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
  .filter { flex: 1; min-width: 12rem; }
  .workspace { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 0.75rem; }
  .listing { flex: 1; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius); }
  table { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 11px; }
  thead { position: sticky; top: 0; background: var(--panel-2); z-index: 1; }
  th {
    text-align: left; padding: 0.3rem 0.5rem; font-size: 10px;
    text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--border);
  }
  td { padding: 0.2rem 0.5rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
  .pc { color: var(--accent); }
  .bytes { color: var(--muted); }
  .mnemonic { color: #7ec8e3; font-weight: 600; }
  .operands { color: var(--fg); margin-left: 0.5rem; }
  .func { color: var(--warn); }
  .src { color: var(--muted); font-size: 10px; }
  tr.target { background: rgba(0, 209, 143, 0.08); }
  tr.range { background: rgba(0, 209, 143, 0.12); }
  tr.selected { background: rgba(255, 203, 107, 0.18); }
  tr.target .pc { font-weight: 700; }
  tr:hover { background: var(--panel-2); }
  .target-panel {
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .target-editor,
  .targets-list {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel);
    padding: 0.65rem;
  }
  .target-editor-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  .target-editor-head h3 { margin: 0; font-size: 13px; }
  .target-editor-head label { display: flex; align-items: center; gap: 0.35rem; font-size: 12px; }
  .target-pcs {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.15rem;
    margin-bottom: 0.5rem;
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
  }
  .field { display: flex; flex-direction: column; gap: 0.2rem; margin-bottom: 0.45rem; }
  .field label { color: var(--muted); font-size: 10px; text-transform: uppercase; }
  .field input { width: 100%; }
  .delay-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; }
  .target-actions { display: flex; gap: 0.45rem; }
  .target-actions button,
  .target-row button {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--fg);
    cursor: pointer;
    font-size: 12px;
    padding: 0.3rem 0.5rem;
  }
  .target-actions button:hover:not(:disabled),
  .target-row button:hover { border-color: var(--accent); }
  .target-actions button:disabled { cursor: not-allowed; opacity: 0.45; }
  .targets-list { flex: 1; min-height: 0; overflow: auto; }
  .targets-head {
    color: var(--muted);
    font-size: 10px;
    font-weight: 700;
    margin-bottom: 0.4rem;
    text-transform: uppercase;
  }
  .target-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.5rem;
    align-items: center;
    border-top: 1px solid var(--border);
    padding: 0.45rem 0;
  }
  .target-row b,
  .target-row span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .target-row b { color: var(--fg); font-size: 12px; }
  .target-row span { color: var(--muted); font-family: var(--mono); font-size: 10px; }
  .info { color: var(--muted); font-size: 11px; margin-top: 0.5rem; }
  .empty-msg { color: var(--muted); margin-top: 2rem; }

  @media (max-width: 860px) {
    .workspace { grid-template-columns: 1fr; }
    .target-panel { min-height: 18rem; }
  }
</style>
