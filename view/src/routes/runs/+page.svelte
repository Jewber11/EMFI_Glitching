<script lang="ts">
  import { onMount } from 'svelte';
  import {
    ApiError,
    exportRunsUrl,
    getCampaignMetadata,
    listRuns,
    putCampaignMetadata,
    replay,
    type CampaignMetadata
  } from '$lib/api/control';
  import { toasts } from '$lib/stores/toast';

  let runs: any[] = [];
  let loading = false;
  let filterOutcome = '';
  let filterCampaign = '';
  let filterTag = '';
  let selectedRun: any = null;
  let selectedCampaign = '';
  let metadataByCampaign: Record<string, CampaignMetadata | null> = {};
  let metadataLoading = false;
  let metadataSaving = false;
  let metadataAvailable = true;
  let notesDraft = '';
  let tagsDraft = '';
  let metadataMessage = '';
  let metadataFetchSeq = 0;

  onMount(() => { fetchRuns(); });

  async function fetchRuns() {
    loading = true;
    try {
      const params: Record<string, string> = {};
      if (filterOutcome) params.outcome = filterOutcome;
      if (filterCampaign) params.campaign = filterCampaign;
      const result = await listRuns(params);
      runs = Array.isArray(result) ? result : result?.entries ?? result?.runs ?? [];
      const ids = campaignIdsFromRuns(runs);
      if (!selectedCampaign || !ids.includes(selectedCampaign)) {
        selectedCampaign = ids[0] ?? '';
      }
      void loadMetadataForCampaigns(ids);
    } catch {
      toasts.warn('Could not load runs — is Control running?');
      runs = [];
    } finally {
      loading = false;
    }
  }

  async function doReplay(runId: string) {
    try {
      await replay(runId);
      toasts.info('Replay started');
    } catch {
      toasts.error('Replay failed');
    }
  }

  async function loadMetadataForCampaigns(ids: string[]) {
    const missing = ids.filter((id) => metadataByCampaign[id] === undefined);
    if (missing.length === 0) return;
    const seq = ++metadataFetchSeq;
    metadataLoading = true;
    metadataMessage = '';
    try {
      const results = await Promise.all(
        missing.map(async (id) => {
          try {
            return [id, await getCampaignMetadata(id)] as const;
          } catch (err) {
            if (err instanceof ApiError && [404, 405, 501].includes(err.status)) {
              metadataAvailable = false;
              return [id, null] as const;
            }
            throw err;
          }
        })
      );
      for (const [id, metadata] of results) metadataByCampaign[id] = metadata;
      metadataByCampaign = { ...metadataByCampaign };
      if (missing.includes(selectedCampaign)) syncDrafts();
    } catch {
      metadataMessage = 'Campaign metadata unavailable';
    } finally {
      if (seq === metadataFetchSeq) metadataLoading = false;
    }
  }

  async function loadSelectedMetadata(id: string) {
    if (!id) return;
    await loadMetadataForCampaigns([id]);
    syncDrafts();
  }

  async function saveMetadata() {
    if (!selectedCampaign || metadataSaving || !metadataAvailable) return;
    metadataSaving = true;
    metadataMessage = '';
    const tags = parseTags(tagsDraft);
    try {
      const saved = await putCampaignMetadata(selectedCampaign, {
        notes: notesDraft.trim(),
        tags
      });
      metadataByCampaign[selectedCampaign] = saved;
      metadataByCampaign = { ...metadataByCampaign };
      notesDraft = saved.notes ?? '';
      tagsDraft = (saved.tags ?? []).join(', ');
      toasts.info('Campaign metadata saved');
    } catch (err) {
      if (err instanceof ApiError && [404, 405, 501].includes(err.status)) {
        metadataAvailable = false;
        metadataMessage = 'Control does not expose campaign metadata endpoints yet';
      } else {
        metadataMessage = 'Could not save campaign metadata';
      }
    } finally {
      metadataSaving = false;
    }
  }

  function getCampaignId(run: any): string {
    return String(run?.campaign_id ?? run?.campaign ?? run?.campaignId ?? '').trim();
  }

  function campaignIdsFromRuns(source: any[]): string[] {
    return Array.from(new Set(source.map(getCampaignId).filter(Boolean))).sort();
  }

  function parseTags(value: string): string[] {
    const seen = new Set<string>();
    return value
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean)
      .filter((tag) => {
        const key = tag.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }

  function tagsForCampaign(campaignId: string): string[] {
    return metadataByCampaign[campaignId]?.tags ?? [];
  }

  function syncDrafts() {
    const metadata = selectedCampaign ? metadataByCampaign[selectedCampaign] : null;
    notesDraft = metadata?.notes ?? '';
    tagsDraft = (metadata?.tags ?? []).join(', ');
  }

  function formatTime(ts: string): string {
    try {
      return new Date(ts).toLocaleString('en-GB', { hour12: false });
    } catch { return ts; }
  }

  function formatUpdated(ts?: string): string {
    if (!ts) return 'not saved';
    return formatTime(ts);
  }

  $: exportParams = {
    ...(filterOutcome ? { outcome: filterOutcome } : {}),
    ...(filterCampaign ? { campaign: filterCampaign } : {})
  };
  $: csvExportHref = exportRunsUrl(exportParams);
  $: campaignIds = campaignIdsFromRuns(runs);
  $: if (!selectedCampaign && campaignIds.length > 0) selectedCampaign = campaignIds[0];
  $: tagOptions = Array.from(
    new Set(
      campaignIds
        .flatMap(tagsForCampaign)
        .filter(Boolean)
    )
  ).sort((a, b) => a.localeCompare(b));
  $: if (filterTag && !tagOptions.includes(filterTag)) filterTag = '';
  $: displayedRuns = filterTag
    ? runs.filter((run) => tagsForCampaign(getCampaignId(run)).includes(filterTag))
    : runs;
  $: selectedCampaign, syncDrafts();
</script>

<div class="page">
  <h2>Runs</h2>

  <div class="filters">
    <select bind:value={filterOutcome} on:change={fetchRuns}>
      <option value="">All outcomes</option>
      <option value="glitch">Glitch</option>
      <option value="hang">Hang</option>
      <option value="crash">Crash</option>
      <option value="nothing">Nothing</option>
      <option value="unobserved">Unobserved</option>
    </select>
    <input type="text" bind:value={filterCampaign} placeholder="Campaign ID" list="campaign-options" />
    <datalist id="campaign-options">
      {#each campaignIds as id}
        <option value={id}></option>
      {/each}
    </datalist>
    <select bind:value={filterTag}>
      <option value="">All tags</option>
      {#each tagOptions as tag}
        <option value={tag}>{tag}</option>
      {/each}
    </select>
    <button on:click={fetchRuns}>Filter</button>
    <a class="export-btn" href={csvExportHref} download>Export CSV</a>
    {#if loading}<span class="loading">Loading…</span>{/if}
  </div>

  {#if campaignIds.length > 0}
    <section class="metadata-strip" aria-label="Campaign notes and tags">
      <div class="metadata-head">
        <label>
          Campaign
          <select bind:value={selectedCampaign} on:change={() => loadSelectedMetadata(selectedCampaign)}>
            {#each campaignIds as id}
              <option value={id}>{id}</option>
            {/each}
          </select>
        </label>
        <span class="meta-state">
          {#if metadataLoading}
            Loading metadata…
          {:else if !metadataAvailable}
            Metadata API unavailable
          {:else}
            Updated {formatUpdated(metadataByCampaign[selectedCampaign]?.updated_at)}
          {/if}
        </span>
        {#if selectedCampaign && tagsForCampaign(selectedCampaign).length > 0}
          <div class="tag-row">
            {#each tagsForCampaign(selectedCampaign) as tag}
              <button
                class="tag"
                class:active={filterTag === tag}
                on:click={() => (filterTag = filterTag === tag ? '' : tag)}
                type="button"
              >
                {tag}
              </button>
            {/each}
          </div>
        {/if}
      </div>
      <div class="metadata-editor">
        <textarea
          bind:value={notesDraft}
          placeholder="Campaign notes"
          disabled={!metadataAvailable || !selectedCampaign}
          rows="2"
        ></textarea>
        <input
          bind:value={tagsDraft}
          placeholder="tags, comma separated"
          disabled={!metadataAvailable || !selectedCampaign}
        />
        <button
          on:click={saveMetadata}
          disabled={!metadataAvailable || !selectedCampaign || metadataSaving}
        >
          {metadataSaving ? 'Saving…' : 'Save'}
        </button>
      </div>
      {#if metadataMessage}
        <p class="metadata-message">{metadataMessage}</p>
      {/if}
    </section>
  {/if}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Campaign</th>
          <th>Outcome</th>
          <th>X</th>
          <th>Y</th>
          <th>Z</th>
          <th>Delay (us)</th>
          <th>Width (ns)</th>
          <th>Voltage</th>
          <th>ms</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each displayedRuns as r}
          <tr
            class={r.outcome}
            class:selected={selectedRun?.id === r.id}
            on:click={() => {
              selectedRun = r;
              selectedCampaign = getCampaignId(r) || selectedCampaign;
              void loadSelectedMetadata(selectedCampaign);
            }}
          >
            <td>{formatTime(r.ts)}</td>
            <td class="campaign-id">{getCampaignId(r) || '—'}</td>
            <td class="outcome">{r.outcome}</td>
            <td>{r.x?.toFixed(2) ?? '—'}</td>
            <td>{r.y?.toFixed(2) ?? '—'}</td>
            <td>{r.z?.toFixed(2) ?? '—'}</td>
            <td>{r.glitch_delay_us ?? '—'}</td>
            <td>{r.pulse_width_ns ?? '—'}</td>
            <td>{r.shouter_voltage ?? '—'}</td>
            <td>{r.elapsed_ms ?? '—'}</td>
            <td><button class="replay-btn" on:click|stopPropagation={() => doReplay(r.id)}>Replay</button></td>
          </tr>
        {/each}
        {#if displayedRuns.length === 0 && !loading}
          <tr><td colspan="11" class="empty">No runs found</td></tr>
        {/if}
      </tbody>
    </table>
  </div>

  {#if selectedRun}
    <div class="panel detail">
      <h3>Details</h3>
      <pre>{JSON.stringify(selectedRun, null, 2)}</pre>
    </div>
  {/if}
</div>

<style>
  .page { padding: 1rem 1.5rem; height: 100%; display: flex; flex-direction: column; }
  h2 { margin-bottom: 0.75rem; }
  .filters { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
  .filters select, .filters input { font-size: 12px; }
  button:disabled, input:disabled, textarea:disabled { opacity: 0.55; cursor: not-allowed; }
  .export-btn {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--fg);
    font-size: 12px;
    padding: 0.25rem 0.6rem;
    text-decoration: none;
  }
  .export-btn:hover { border-color: var(--accent); color: var(--accent); }
  .loading { color: var(--muted); font-size: 11px; }
  .metadata-strip {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 0.75rem;
    padding: 0.55rem;
    display: grid;
    gap: 0.45rem;
    background: var(--panel);
  }
  .metadata-head, .metadata-editor {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    min-width: 0;
  }
  .metadata-head label {
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 11px;
    text-transform: uppercase;
  }
  .metadata-head select { max-width: 260px; font-size: 12px; }
  .meta-state, .metadata-message {
    color: var(--muted);
    font-size: 11px;
  }
  .tag-row {
    display: flex;
    gap: 0.25rem;
    flex-wrap: wrap;
    min-width: 0;
  }
  .tag {
    border-color: var(--border);
    color: var(--muted);
    font-size: 10px;
    padding: 0.12rem 0.4rem;
  }
  .tag.active, .tag:hover { border-color: var(--accent); color: var(--accent); }
  .metadata-editor textarea {
    flex: 1 1 360px;
    min-width: 220px;
    resize: vertical;
    font-size: 12px;
  }
  .metadata-editor input {
    flex: 0 1 240px;
    min-width: 160px;
    font-size: 12px;
  }
  .metadata-editor button {
    flex: 0 0 auto;
  }
  .table-wrap { flex: 1; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius); }
  table { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 11px; }
  thead { position: sticky; top: 0; background: var(--panel-2); z-index: 1; }
  th {
    text-align: left;
    padding: 0.35rem 0.5rem;
    font-size: 10px;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }
  td { padding: 0.25rem 0.5rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
  tr { cursor: pointer; transition: background 0.1s; }
  tr:hover { background: var(--panel-2); }
  tr.selected { background: var(--panel-2); outline: 1px solid var(--accent); }
  tr.glitch .outcome { color: var(--ok); }
  tr.hang .outcome { color: var(--err); }
  tr.crash .outcome { color: var(--warn); }
  tr.nothing .outcome { color: var(--muted); }
  .campaign-id { color: var(--muted); max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
  .empty { text-align: center; color: var(--muted); padding: 2rem; }
  .replay-btn {
    font-size: 10px;
    padding: 0.15rem 0.5rem;
    border-color: var(--accent);
    color: var(--accent);
  }
  .detail { margin-top: 0.75rem; max-height: 200px; overflow: auto; }
  .detail pre { font-size: 11px; color: var(--muted); white-space: pre-wrap; }
  @media (max-width: 760px) {
    .metadata-head, .metadata-editor { align-items: stretch; flex-direction: column; }
    .metadata-head label, .metadata-head select, .metadata-editor textarea, .metadata-editor input, .metadata-editor button {
      width: 100%;
      max-width: none;
    }
  }
</style>
