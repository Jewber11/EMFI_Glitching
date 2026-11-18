<script lang="ts">
  import { base } from '$app/paths';
  import { onMount } from 'svelte';
  import { listProjects, createProject, deleteProject, listTemplates, importProject } from '$lib/api';
  import { goto } from '$app/navigation';
  import type { Project, Template } from '$lib/types';

  let projects: Project[] = [];
  let templates: Template[] = [];
  let loading = true;
  let error = '';

  let showForm = false;
  let form = { name: '', template: 'c_ti_hal', language: 'c', hal: 'ti', description: '' };
  let creating = false;

  let showImport = false;
  let importForm = {
    name: '', source_path: '', language: 'c', hal: 'ti', description: '',
    exclude: 'Debug/**\n.git/**',
  };
  let importing = false;

  onMount(async () => {
    try {
      [projects, templates] = await Promise.all([listProjects(), listTemplates()]);
    } catch (e: any) {
      error = e.message;
    }
    loading = false;
  });

  function onTemplateChange() {
    const t = templates.find(t => t.id === form.template);
    if (t) {
      form.language = t.language;
      form.hal = t.hal;
    }
  }

  async function handleCreate() {
    creating = true;
    error = '';
    try {
      const p = await createProject(form);
      projects = [...projects, p];
      showForm = false;
      form = { name: '', template: 'c_ti_hal', language: 'c', hal: 'ti', description: '' };
    } catch (e: any) {
      error = e.message;
    }
    creating = false;
  }

  async function handleImport() {
    importing = true;
    error = '';
    try {
      const excludeList = importForm.exclude.split('\n').map(s => s.trim()).filter(Boolean);
      const p = await importProject({
        name: importForm.name,
        source_path: importForm.source_path,
        language: importForm.language,
        hal: importForm.hal,
        description: importForm.description || undefined,
        exclude: excludeList.length > 0 ? excludeList : undefined,
      });
      showImport = false;
      goto(`${base}/projects/${p.id}`);
    } catch (e: any) {
      error = e.message;
    }
    importing = false;
  }

  async function handleDelete(id: string) {
    if (!confirm(`Delete project "${id}"? It will be moved to .trash.`)) return;
    try {
      await deleteProject(id);
      projects = projects.filter(p => p.id !== id);
    } catch (e: any) {
      error = e.message;
    }
  }
</script>

<div class="page">
  <div class="top-bar">
    <h2>Projects</h2>
    <div style="display:flex;gap:0.5rem">
      <button class="btn primary" on:click={() => showForm = !showForm}>
        {showForm ? 'Cancel' : '+ New Project'}
      </button>
      <button class="btn" on:click={() => showImport = !showImport}>
        {showImport ? 'Cancel' : 'Import'}
      </button>
    </div>
  </div>

  {#if error}
    <div class="error">{error}</div>
  {/if}

  {#if showForm}
    <form class="create-form" on:submit|preventDefault={handleCreate}>
      <label>
        Name
        <input type="text" bind:value={form.name} required placeholder="My Glitch Target" />
      </label>
      <label>
        Template
        <select bind:value={form.template} on:change={onTemplateChange}>
          {#each templates as t}
            <option value={t.id}>{t.id} ({t.language}/{t.hal})</option>
          {/each}
        </select>
      </label>
      <label>
        Description
        <input type="text" bind:value={form.description} placeholder="Optional" />
      </label>
      <button class="btn primary" type="submit" disabled={creating || !form.name}>
        {creating ? 'Creating…' : 'Create'}
      </button>
    </form>
  {/if}

  {#if showImport}
    <form class="create-form" on:submit|preventDefault={handleImport}>
      <label>
        Name
        <input type="text" bind:value={importForm.name} required placeholder="EMFI Loop" />
      </label>
      <label>
        Source path
        <input type="text" bind:value={importForm.source_path} required
               placeholder="/home/stephen/workspace_ccstheia/EMFI_Loop" style="min-width:320px" />
      </label>
      <label>
        Language
        <select bind:value={importForm.language}>
          <option value="c">C</option>
          <option value="rust">Rust</option>
        </select>
      </label>
      <label>
        HAL
        <select bind:value={importForm.hal}>
          <option value="ti">TI</option>
          <option value="b01lers">b01lers</option>
        </select>
      </label>
      <label>
        Description
        <input type="text" bind:value={importForm.description} placeholder="Optional" />
      </label>
      <label>
        Exclude (one glob/line)
        <textarea bind:value={importForm.exclude} rows={3} style="font-family:monospace;font-size:0.8rem"></textarea>
      </label>
      <button class="btn primary" type="submit" disabled={importing || !importForm.name || !importForm.source_path}>
        {importing ? 'Importing…' : 'Import'}
      </button>
    </form>
  {/if}

  {#if loading}
    <p class="muted">Loading projects…</p>
  {:else if projects.length === 0}
    <p class="muted">No projects yet. Create one to get started.</p>
  {:else}
    <div class="grid">
      {#each projects as p}
        <a href="{base}/projects/{p.id}" class="card">
          <div class="card-header">
            <strong>{p.name}</strong>
            <button class="btn-icon danger" on:click|preventDefault|stopPropagation={() => handleDelete(p.id)} title="Delete">✕</button>
          </div>
          <div class="card-meta">
            <span class="badge">{p.language.toUpperCase()}</span>
            <span class="badge">{p.hal}</span>
            <span class="badge">{p.target}</span>
          </div>
          {#if p.description}
            <p class="desc">{p.description}</p>
          {/if}
          <div class="card-footer">
            <span>{p.versions.length} version{p.versions.length !== 1 ? 's' : ''}</span>
            <span class="date">{new Date(p.created_at).toLocaleDateString()}</span>
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { padding: 1rem 1.5rem; overflow-y: auto; height: 100%; }
  .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
  h2 { margin: 0; font-size: 1.3rem; }
  .error { background: #fee; color: #c00; padding: 0.5rem 1rem; border-radius: 4px; margin-bottom: 1rem; font-size: 0.85rem; }
  .create-form {
    display: flex; gap: 0.75rem; align-items: flex-end; flex-wrap: wrap;
    padding: 1rem; background: #fff; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 1rem;
  }
  .create-form label { display: flex; flex-direction: column; gap: 4px; font-size: 0.8rem; color: #555; }
  .create-form input, .create-form select {
    padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem;
  }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
  .card {
    display: block; text-decoration: none; color: inherit;
    background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 1rem;
    transition: box-shadow 0.15s;
  }
  .card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; }
  .card-header strong { font-size: 1rem; }
  .card-meta { display: flex; gap: 0.4rem; margin-top: 0.5rem; }
  .badge {
    font-size: 0.7rem; padding: 2px 6px; border-radius: 3px;
    background: #eef; color: #446; font-weight: 600;
  }
  .desc { font-size: 0.85rem; color: #666; margin: 0.5rem 0 0; }
  .card-footer { display: flex; justify-content: space-between; margin-top: 0.75rem; font-size: 0.75rem; color: #999; }
  .date { font-style: italic; }
  .btn {
    padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem;
  }
  .btn.primary { background: #2563eb; color: #fff; }
  .btn.primary:hover { background: #1d4ed8; }
  .btn.primary:disabled { background: #93c; opacity: 0.5; }
  .btn-icon { all: unset; cursor: pointer; font-size: 0.9rem; padding: 2px 4px; border-radius: 3px; }
  .btn-icon.danger:hover { background: #fee; color: #c00; }
  .muted { color: #999; }
</style>
