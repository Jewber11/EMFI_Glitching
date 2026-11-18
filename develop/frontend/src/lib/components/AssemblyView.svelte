<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { AssemblyListing, GlitchTarget } from '$lib/types';

  export let listing: AssemblyListing | null = null;
  export let targets: GlitchTarget[] = [];

  const dispatch = createEventDispatcher<{ 'select-instruction': { pc: number; mnemonic: string; function: string | null } }>();

  let targetPcs: Set<number>;
  $: targetPcs = new Set(targets.map(t => t.pc_address));

  function hex(n: number): string {
    return n.toString(16).padStart(8, '0');
  }

  function onRowClick(pc: number, mnemonic: string, fn: string | null | undefined) {
    dispatch('select-instruction', { pc, mnemonic, function: fn ?? null });
  }
</script>

{#if listing}
  <div class="asm-container">
    <table>
      <thead>
        <tr>
          <th class="col-pc">Address</th>
          <th class="col-bytes">Bytes</th>
          <th class="col-inst">Instruction</th>
          <th class="col-src">Source</th>
        </tr>
      </thead>
      <tbody>
        {#each listing.instructions as ins}
          <tr
            class:target={targetPcs.has(ins.pc)}
            on:click={() => onRowClick(ins.pc, ins.mnemonic, ins.function)}
          >
            <td class="col-pc">{hex(ins.pc)}</td>
            <td class="col-bytes">{ins.bytes_hex}</td>
            <td class="col-inst">
              <span class="mnemonic">{ins.mnemonic}</span>
              {#if ins.operands}
                <span class="operands">{ins.operands}</span>
              {/if}
            </td>
            <td class="col-src">
              {#if ins.source_file}
                {ins.source_file}:{ins.source_line ?? ''}
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{:else}
  <p class="muted">No listing loaded. Select a build to view disassembly.</p>
{/if}

<style>
  .asm-container { overflow: auto; height: 100%; }
  table { border-collapse: collapse; font-family: monospace; font-size: 0.82rem; width: 100%; }
  thead { position: sticky; top: 0; background: #f5f5f5; z-index: 1; }
  th { text-align: left; padding: 4px 8px; border-bottom: 2px solid #ccc; font-size: 0.75rem; }
  td { padding: 2px 8px; border-bottom: 1px solid #eee; white-space: nowrap; }
  tr { cursor: pointer; }
  tr:hover { background: #f0f0ff; }
  tr.target { background: #fff3cd; }
  tr.target:hover { background: #ffe69c; }
  .col-pc { color: #666; }
  .col-bytes { color: #999; }
  .mnemonic { color: #0066cc; font-weight: 600; margin-right: 0.5em; }
  .operands { color: #333; }
  .col-src { color: #888; font-size: 0.75rem; }
  .muted { color: #999; padding: 1rem; }
</style>
