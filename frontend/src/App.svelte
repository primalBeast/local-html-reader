<script lang="ts">
  import { onMount } from 'svelte';
  import { api, viewUrl, type DocumentHit, type Root } from './lib/api';

  let roots = $state<Root[]>([]);
  let documents = $state<DocumentHit[]>([]);
  let truncated = $state(false);
  let query = $state('');
  let newPath = $state('');
  let selectedRootId = $state<string | null>(null);
  let selected = $state<DocumentHit | null>(null);
  let loading = $state(true);
  let adding = $state(false);
  let error = $state<string | null>(null);
  let version = $state('');

  let filteredRootId = $derived(selectedRootId);

  async function refreshRoots() {
    const data = await api.roots();
    roots = data.roots;
  }

  async function refreshDocuments() {
    const data = await api.documents(query.trim() || undefined, filteredRootId || undefined);
    documents = data.documents;
    truncated = data.truncated;
  }

  async function boot() {
    loading = true;
    error = null;
    try {
      const health = await api.health();
      version = health.version;
      const settings = await api.settings();
      await refreshRoots();
      await refreshDocuments();
      const last = settings.last_document;
      if (last) {
        const match = documents.find((d) => d.root_id === last.root_id && d.rel === last.rel);
        if (match) selected = match;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  async function addFolder() {
    const path = newPath.trim();
    if (!path) return;
    adding = true;
    error = null;
    try {
      const rec = await api.addRoot(path);
      newPath = '';
      selectedRootId = rec.id;
      await refreshRoots();
      await refreshDocuments();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      adding = false;
    }
  }

  async function removeFolder(id: string, event: MouseEvent) {
    event.stopPropagation();
    error = null;
    try {
      await api.removeRoot(id);
      if (selectedRootId === id) selectedRootId = null;
      if (selected?.root_id === id) selected = null;
      await refreshRoots();
      await refreshDocuments();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function selectRoot(id: string) {
    selectedRootId = selectedRootId === id ? null : id;
    await refreshDocuments();
  }

  async function openDoc(doc: DocumentHit) {
    selected = doc;
    try {
      await api.patchSettings({ last_document: { root_id: doc.root_id, rel: doc.rel } });
    } catch {
      /* non-fatal */
    }
  }

  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  function onSearch(value: string) {
    query = value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      void refreshDocuments();
    }, 150);
  }

  onMount(() => {
    void boot();
  });
</script>

<div class="app">
  <header class="topbar">
    <div class="brand">
      <h1>Local HTML Reader</h1>
      <span>Read HTML files on this PC — nothing is uploaded</span>
    </div>
    <div class="status">v{version || '…'} · 127.0.0.1:8766</div>
  </header>

  <main class="layout">
    <section class="pane">
      <div class="pane-head">
        <h2>Folders</h2>
        <form class="add-row" onsubmit={(e) => { e.preventDefault(); void addFolder(); }}>
          <input
            type="text"
            bind:value={newPath}
            placeholder="D:\Notes\html"
            aria-label="Absolute folder path"
            spellcheck="false"
          />
          <button class="btn" type="submit" disabled={adding || !newPath.trim()}>Add</button>
        </form>
        <div class="hint">Paste an absolute folder path. HTML files stay on disk.</div>
      </div>
      {#if error}
        <div class="error">{error}</div>
      {/if}
      <div class="scroll">
        {#if loading}
          <div class="empty">Loading…</div>
        {:else if roots.length === 0}
          <div class="empty">
            Add one or more documents-root folders. The app will list <code>.html</code> and
            <code>.htm</code> files under them.
          </div>
        {:else}
          {#each roots as root (root.id)}
            <div class="root-row">
              <button
                class="root-item"
                class:active={selectedRootId === root.id}
                type="button"
                onclick={() => void selectRoot(root.id)}
              >
                <div class="root-path">{root.path}</div>
                {#if !root.exists}
                  <div class="warn">Folder not found</div>
                {/if}
              </button>
              <button
                class="btn-icon"
                type="button"
                title="Remove folder"
                aria-label="Remove folder"
                onclick={(e) => void removeFolder(root.id, e)}
              >
                ×
              </button>
            </div>
          {/each}
        {/if}
      </div>
    </section>

    <section class="pane">
      <div class="pane-head">
        <h2>Documents</h2>
        <input
          type="text"
          value={query}
          oninput={(e) => onSearch(e.currentTarget.value)}
          placeholder="Search filename or path"
          aria-label="Search documents"
        />
      </div>
      <div class="scroll">
        {#if roots.length === 0}
          <div class="empty">Add a folder to see files.</div>
        {:else if documents.length === 0}
          <div class="empty">No .html / .htm files match.</div>
        {:else}
          {#each documents as doc (`${doc.root_id}:${doc.rel}`)}
            <button
              class="doc-item"
              class:active={selected?.root_id === doc.root_id && selected?.rel === doc.rel}
              type="button"
              onclick={() => void openDoc(doc)}
            >
              <div class="doc-name">{doc.name}</div>
              <div class="doc-rel">{doc.rel}</div>
            </button>
          {/each}
          {#if truncated}
            <div class="muted">Results truncated. Narrow the search.</div>
          {/if}
        {/if}
      </div>
    </section>

    <section class="viewer">
      {#if selected}
        <div class="viewer-bar">
          <code>{selected.rel}</code>
          <span class="muted">{selected.root_path}</span>
        </div>
        <iframe
          title={selected.name}
          src={viewUrl(selected.root_id, selected.rel)}
          sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
        ></iframe>
      {:else}
        <div class="empty" style="padding: 1.25rem">
          Select an HTML file to view it here. Relative images and CSS in the same folder
          load through the sandboxed viewer.
        </div>
      {/if}
    </section>
  </main>
</div>
