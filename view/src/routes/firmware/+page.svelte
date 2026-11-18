<script lang="ts">
  import { CONTROL_URL } from '$lib/config';

  type Image = { path: string; name: string; mode: 'swd' | 'ectf' };
  let folder = '/home/sam/fault_injection/EMFI/firmware';
  let images: Image[] = [];
  let selected = '';
  let mode: 'swd' | 'ectf' = 'swd';
  let name = 'firmware';
  let status = '';
  let busy = false;
  let truncated = false;

  async function scan() {
    busy = true; status = '';
    try {
      const response = await fetch(`${CONTROL_URL}/target/firmware?folder=${encodeURIComponent(folder)}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || response.statusText);
      folder = result.folder; images = result.images; truncated = result.truncated;
      selected = ''; status = `${images.length} firmware files found`;
    } catch (e: any) { status = `Scan failed: ${e.message}`; }
    finally { busy = false; }
  }

  function selectImage() {
    const image = images.find(item => item.path === selected);
    if (image) mode = image.mode;
  }

  async function flash() {
    if (!selected) return;
    busy = true; status = 'Flashing…';
    try {
      const response = await fetch(`${CONTROL_URL}/target/flash`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_sha: `file:${selected}`, elf_url: selected, mode, name })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || response.statusText);
      status = `Flash complete. SHA-256: ${result.build_sha}`;
    } catch (e: any) { status = `Flash failed: ${e.message}`; }
    finally { busy = false; }
  }
</script>

<div class="firmware-page">
  <h1>Firmware</h1>
  <p>Choose a folder on the Control computer. Subfolders are searched for firmware images.</p>
  <label for="folder">Firmware folder</label>
  <div class="row"><input id="folder" bind:value={folder} /><button on:click={scan} disabled={busy || !folder.trim()}>Scan folder</button></div>
  <label for="image">Firmware image</label>
  <select id="image" bind:value={selected} on:change={selectImage} disabled={busy || !images.length}>
    <option value="">Select firmware</option>
    {#each images as image}<option value={image.path}>{image.name}</option>{/each}
  </select>
  {#if truncated}<p>Showing first 5,000 files. Choose a smaller folder.</p>{/if}
  <label for="mode">Load method</label>
  <select id="mode" bind:value={mode} disabled={busy}><option value="swd">Pico SWD (ELF, OUT, HEX)</option><option value="ectf">eCTF bootloader UART (BIN, PROT, HSM)</option></select>
  {#if mode === 'ectf'}<label for="name">eCTF image name</label><input id="name" bind:value={name} disabled={busy} /><p>Put the board in bootloader update mode before flashing. Secure bootloaders require compatible signed images.</p>{:else}<p>SWD writes the addresses in the image and may overwrite the bootloader.</p>{/if}
  <button on:click={flash} disabled={busy || !selected}>Flash selected firmware</button>
  {#if status}<p role="status">{status}</p>{/if}
</div>

<style>
  .firmware-page { max-width: 850px; margin: 2rem auto; padding: 1.5rem; display: grid; gap: .8rem; }
  .row { display: flex; gap: .5rem; }
  input, select { width: 100%; padding: .6rem; }
  button { padding: .6rem 1rem; cursor: pointer; }
  button:disabled { cursor: default; }
</style>
