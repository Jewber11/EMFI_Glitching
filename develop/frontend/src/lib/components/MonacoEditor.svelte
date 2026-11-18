<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';

  export let value = '';
  export let language = 'c';

  let container: HTMLDivElement;
  let editor: any;
  let monaco: any;
  const dispatch = createEventDispatcher<{ save: string; change: string }>();

  const EXT_LANG: Record<string, string> = {
    '.c': 'c', '.h': 'c', '.rs': 'rust', '.toml': 'toml',
    '.json': 'json', '.ld': 'plaintext', '.md': 'markdown',
    '.s': 'plaintext', '.S': 'plaintext', '.py': 'python',
    '.mk': 'makefile', '.txt': 'plaintext',
  };

  export function detectLanguage(path: string): string {
    const dot = path.lastIndexOf('.');
    if (dot === -1) {
      if (path.endsWith('Makefile') || path.endsWith('makefile')) return 'makefile';
      return 'plaintext';
    }
    return EXT_LANG[path.slice(dot)] ?? 'plaintext';
  }

  onMount(async () => {
    // Configure Monaco web workers for Vite bundling
    // @ts-ignore
    self.MonacoEnvironment = {
      getWorker(_: string, _label: string) {
        return new Worker(
          new URL('monaco-editor/esm/vs/editor/editor.worker.js', import.meta.url),
          { type: 'module' }
        );
      }
    };

    monaco = await import('monaco-editor');

    editor = monaco.editor.create(container, {
      value,
      language,
      theme: 'vs-dark',
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 13,
      lineNumbers: 'on',
      scrollBeyondLastLine: false,
      wordWrap: 'off',
    });

    editor.onDidChangeModelContent(() => {
      value = editor.getValue();
      dispatch('change', value);
    });

    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
      () => dispatch('save', editor.getValue()),
    );
  });

  onDestroy(() => editor?.dispose());

  $: if (editor && editor.getValue() !== value) {
    editor.setValue(value);
  }
  $: if (editor && monaco) {
    const model = editor.getModel();
    if (model) monaco.editor.setModelLanguage(model, language);
  }
</script>

<div class="monaco-host" bind:this={container}></div>

<style>
  .monaco-host {
    width: 100%;
    height: 100%;
    min-height: 300px;
  }
</style>
