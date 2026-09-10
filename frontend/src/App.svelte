<script lang="ts">
  import { onMount } from 'svelte';
  import Tree from './lib/Tree.svelte';
  import { api, viewUrl, type DocumentHit, type Root, type TreeNode } from './lib/api';
  import { applyFinds, reveal } from './lib/pageFind';

  let roots = $state<Root[]>([]);
  let tree = $state<TreeNode[]>([]);
  let fileCount = $state(0);
  let truncated = $state(false);
  let query = $state('');
  let selected = $state<DocumentHit | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let version = $state('');

  let menuOpen = $state(false);
  let folderDialog = $state(false);
  let folderPath = $state('');
  let settingFolder = $state(false);

  let iframeEl = $state<HTMLIFrameElement | null>(null);
  let listQuery = $state('');
  let listMarks = $state<HTMLElement[]>([]);
  let listIndex = $state(0);
  let listFindInput = $state<HTMLInputElement | null>(null);
  let pageQuery = $state('');
  let pageMarks = $state<HTMLElement[]>([]);
  let pageIndex = $state(0);
  let pageFindInput = $state<HTMLInputElement | null>(null);

  const SIDEBAR_DEFAULT = 320;
  const SIDEBAR_MIN = 180;
  const SIDEBAR_RIGHT_MIN = 280;
  const SIDEBAR_STORAGE = 'lhr.sidebar_width';

  function readLocalWidth(): number {
    try {
      const n = Number.parseInt(localStorage.getItem(SIDEBAR_STORAGE) || '', 10);
      if (Number.isFinite(n) && n >= SIDEBAR_MIN) return n;
    } catch {
      /* ignore */
    }
    return SIDEBAR_DEFAULT;
  }

  let layoutEl = $state<HTMLElement | null>(null);
  let sidebarWidth = $state(readLocalWidth());
  let dragging = $state(false);

  let rootLabel = $derived(
    roots.length === 0 ? 'No folder selected' : roots.map((r) => r.path).join(' · '),
  );

  async function refreshRoots() {
    const data = await api.roots();
    roots = data.roots;
  }

  async function refreshTree() {
    const data = await api.tree(query.trim() || undefined);
    tree = data.tree;
    fileCount = data.file_count;
    truncated = data.truncated;
  }

  async function boot() {
    loading = true;
    error = null;
    try {
      const health = await api.health();
      version = health.version;
      const settings = await api.settings();
      if (typeof settings.sidebar_width === 'number') {
        sidebarWidth = clampSidebar(settings.sidebar_width);
        try {
          localStorage.setItem(SIDEBAR_STORAGE, String(sidebarWidth));
        } catch {
          /* ignore */
        }
      }
      await refreshRoots();
      await refreshTree();
      const last = settings.last_document;
      if (last) {
        selected = {
          root_id: last.root_id,
          root_path: roots.find((r) => r.id === last.root_id)?.path || '',
          rel: last.rel,
          name: last.rel.split('/').pop() || last.rel,
          size: 0,
          mtime: 0,
        };
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function openFolderDialog() {
    menuOpen = false;
    folderPath = roots[0]?.path || '';
    folderDialog = true;
    error = null;
  }

  async function applyRootFolder() {
    const path = folderPath.trim();
    if (!path) return;
    settingFolder = true;
    error = null;
    try {
      await api.setRoot(path);
      folderDialog = false;
      selected = null;
      pageQuery = '';
      pageMarks = [];
      listQuery = query;
      listMarks = [];
      await refreshRoots();
      await refreshTree();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      settingFolder = false;
    }
  }

  async function openDoc(doc: DocumentHit) {
    selected = doc;
    pageQuery = '';
    pageMarks = [];
    pageIndex = 0;
    listIndex = 0;
    try {
      await api.patchSettings({ last_document: { root_id: doc.root_id, rel: doc.rel } });
    } catch {
      /* non-fatal */
    }
  }

  function clampSidebar(raw: number): number {
    const layoutWidth = layoutEl?.clientWidth ?? window.innerWidth;
    const max = Math.max(SIDEBAR_MIN, layoutWidth - SIDEBAR_RIGHT_MIN);
    return Math.round(Math.min(max, Math.max(SIDEBAR_MIN, raw)));
  }

  function persistSidebar(width: number) {
    sidebarWidth = width;
    try {
      localStorage.setItem(SIDEBAR_STORAGE, String(width));
    } catch {
      /* ignore */
    }
    void api.patchSettings({ sidebar_width: width }).catch(() => undefined);
  }

  function onSplitPointerDown(event: PointerEvent) {
    event.preventDefault();
    dragging = true;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function onSplitPointerMove(event: PointerEvent) {
    if (!dragging || !layoutEl) return;
    const left = layoutEl.getBoundingClientRect().left;
    sidebarWidth = clampSidebar(event.clientX - left);
  }

  function onSplitPointerUp() {
    if (!dragging) return;
    dragging = false;
    persistSidebar(clampSidebar(sidebarWidth));
  }

  function onSplitDblClick() {
    persistSidebar(clampSidebar(SIDEBAR_DEFAULT));
  }

  function onSplitKeydown(event: KeyboardEvent) {
    const step = event.shiftKey ? 48 : 16;
    let next = sidebarWidth;
    if (event.key === 'ArrowLeft') next -= step;
    else if (event.key === 'ArrowRight') next += step;
    else if (event.key === 'Home') next = SIDEBAR_MIN;
    else if (event.key === 'End') next = (layoutEl?.clientWidth ?? 800) - SIDEBAR_RIGHT_MIN;
    else return;
    event.preventDefault();
    persistSidebar(clampSidebar(next));
  }

  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  function onTreeSearch(value: string) {
    query = value;
    listQuery = value;
    runAllFinds(true);
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      void refreshTree();
    }, 200);
  }

  function iframeDoc(): Document | null {
    try {
      return iframeEl?.contentDocument ?? null;
    } catch {
      return null;
    }
  }

  function runAllFinds(focusList = false) {
    const doc = iframeDoc();
    if (!doc) {
      listMarks = [];
      pageMarks = [];
      listIndex = 0;
      pageIndex = 0;
      return;
    }
    const found = applyFinds(doc, listQuery, pageQuery);
    listMarks = found.list;
    pageMarks = found.page;
    const scrollList = Boolean(listMarks.length) && (focusList || !pageQuery.trim());
    const scrollPage = Boolean(pageMarks.length) && !scrollList;
    if (listMarks.length) {
      listIndex = reveal(listMarks, focusList ? 0 : listIndex, 'list', scrollList);
    } else {
      listIndex = 0;
    }
    if (pageMarks.length) {
      pageIndex = reveal(pageMarks, focusList ? pageIndex : 0, 'page', scrollPage);
    } else {
      pageIndex = 0;
    }
  }

  function onListSearchInput(value: string) {
    listQuery = value;
    runAllFinds(true);
  }

  function onPageSearchInput(value: string) {
    pageQuery = value;
    runAllFinds(false);
  }

  function listFindNext() {
    if (listMarks.length === 0) {
      runAllFinds(true);
      return;
    }
    listIndex = reveal(listMarks, listIndex + 1, 'list');
  }

  function listFindPrev() {
    if (listMarks.length === 0) {
      runAllFinds(true);
      return;
    }
    listIndex = reveal(listMarks, listIndex - 1, 'list');
  }

  function pageFindNext() {
    if (pageMarks.length === 0) {
      runAllFinds(false);
      return;
    }
    pageIndex = reveal(pageMarks, pageIndex + 1, 'page');
  }

  function pageFindPrev() {
    if (pageMarks.length === 0) {
      runAllFinds(false);
      return;
    }
    pageIndex = reveal(pageMarks, pageIndex - 1, 'page');
  }

  function onIframeLoad() {
    runAllFinds(Boolean(listQuery.trim()));
    if (listQuery.trim()) {
      window.setTimeout(() => {
        if (listMarks.length === 0) runAllFinds(true);
      }, 0);
    }
  }

  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    const inField = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f' && selected) {
      event.preventDefault();
      pageFindInput?.focus();
      pageFindInput?.select();
      return;
    }
    if (event.key === 'F3' && selected) {
      event.preventDefault();
      if (event.shiftKey) pageFindPrev();
      else pageFindNext();
      return;
    }
    if (event.key === 'Escape') {
      if (folderDialog) folderDialog = false;
      menuOpen = false;
      if (inField && target === pageFindInput) {
        pageQuery = '';
        runAllFinds(false);
      }
      if (inField && target === listFindInput) {
        listQuery = '';
        runAllFinds(true);
      }
    }
  }

  function onWindowClick() {
    menuOpen = false;
  }

  onMount(() => {
    void boot();
    const onResize = () => {
      sidebarWidth = clampSidebar(sidebarWidth);
    };
    window.addEventListener('keydown', onKeydown);
    window.addEventListener('click', onWindowClick);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('keydown', onKeydown);
      window.removeEventListener('click', onWindowClick);
      window.removeEventListener('resize', onResize);
    };
  });
</script>

<div class="app">
  <header class="topbar">
    <div class="menubar">
      <div class="menu">
        <button
          class="menu-btn"
          type="button"
          class:open={menuOpen}
          onclick={(e) => {
            e.stopPropagation();
            menuOpen = !menuOpen;
          }}
        >
          Folder
        </button>
        {#if menuOpen}
          <div class="menu-drop" role="menu">
            <button type="button" role="menuitem" onclick={openFolderDialog}>Set root folder…</button>
          </div>
        {/if}
      </div>
      <div class="brand">
        <h1>Local HTML Reader</h1>
        <span title={rootLabel}>{rootLabel}</span>
      </div>
    </div>
    <div class="status">v{version || '…'} · 127.0.0.1:8766</div>
  </header>

  <main
    class="layout"
    class:dragging
    bind:this={layoutEl}
    style={`grid-template-columns: ${sidebarWidth}px 6px minmax(0, 1fr)`}
  >
    <section class="pane sidebar">
      <div class="pane-head">
        <h2>Documents</h2>
        <input
          type="text"
          value={query}
          oninput={(e) => onTreeSearch(e.currentTarget.value)}
          placeholder="Search in HTML files"
          aria-label="Search documents by text"
          spellcheck="false"
        />
        {#if query.trim()}
          <div class="muted">
            {fileCount} matching file{fileCount === 1 ? '' : 's'}
            {#if truncated} (truncated){/if}
          </div>
        {/if}
      </div>
      {#if error && !folderDialog}
        <div class="error">{error}</div>
      {/if}
      <div class="scroll">
        {#if loading}
          <div class="empty">Loading…</div>
        {:else if roots.length === 0}
          <div class="empty">
            Choose <strong>Folder → Set root folder…</strong> and paste an absolute path.
            HTML files stay on disk; this app only reads them.
          </div>
        {:else if tree.length === 0}
          <div class="empty">
            {#if query.trim()}
              No HTML files contain that text.
            {:else}
              No .html / .htm files under the root folder.
            {/if}
          </div>
        {:else}
          <Tree nodes={tree} {selected} onOpen={openDoc} />
        {/if}
      </div>
    </section>

    <button
      class="splitter"
      class:active={dragging}
      type="button"
      aria-label="Resize document list"
      onpointerdown={onSplitPointerDown}
      onpointermove={onSplitPointerMove}
      onpointerup={onSplitPointerUp}
      onpointercancel={onSplitPointerUp}
      ondblclick={onSplitDblClick}
      onkeydown={onSplitKeydown}
    ></button>

    <section class="viewer">
      {#if selected}
        <div class="viewer-bar">
          <code class="doc-path" title={selected.rel}>{selected.rel}</code>
          <div class="page-finds">
            <form
              class="page-find list-find"
              onsubmit={(e) => {
                e.preventDefault();
                listFindNext();
              }}
            >
              <input
                bind:this={listFindInput}
                type="text"
                value={listQuery}
                oninput={(e) => onListSearchInput(e.currentTarget.value)}
                placeholder="From list search"
                aria-label="Search this page for the document-list search term"
                spellcheck="false"
              />
              <span class="find-count">
                {#if listQuery.trim()}
                  {listMarks.length ? `${listIndex + 1} / ${listMarks.length}` : '0 / 0'}
                {/if}
              </span>
              <button class="btn-ghost btn-small" type="button" onclick={listFindPrev} disabled={!listMarks.length}>Prev</button>
              <button class="btn-ghost btn-small" type="submit" disabled={!listQuery.trim()}>Next</button>
            </form>
            <form
              class="page-find"
              onsubmit={(e) => {
                e.preventDefault();
                pageFindNext();
              }}
            >
              <input
                bind:this={pageFindInput}
                type="text"
                value={pageQuery}
                oninput={(e) => onPageSearchInput(e.currentTarget.value)}
                placeholder="Find in page"
                aria-label="Find in the open document"
                spellcheck="false"
              />
              <span class="find-count">
                {#if pageQuery.trim()}
                  {pageMarks.length ? `${pageIndex + 1} / ${pageMarks.length}` : '0 / 0'}
                {/if}
              </span>
              <button class="btn-ghost btn-small" type="button" onclick={pageFindPrev} disabled={!pageMarks.length}>Prev</button>
              <button class="btn-ghost btn-small" type="submit" disabled={!pageQuery.trim()}>Next</button>
            </form>
          </div>
        </div>
        {#key `${selected.root_id}:${selected.rel}`}
          <iframe
            bind:this={iframeEl}
            title={selected.name}
            src={viewUrl(selected.root_id, selected.rel)}
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
            onload={onIframeLoad}
          ></iframe>
        {/key}
      {:else}
        <div class="empty viewer-empty">
          Click a document in the left pane to open it here.
        </div>
      {/if}
    </section>
  </main>
</div>

{#if folderDialog}
  <div
    class="modal-backdrop"
    onclick={(e) => {
      if (e.currentTarget === e.target) folderDialog = false;
    }}
    role="presentation"
  >
    <div class="modal" role="dialog" aria-labelledby="set-root-title">
    <form
      onsubmit={(e) => {
        e.preventDefault();
        e.stopPropagation();
        void applyRootFolder();
      }}
    >
      <h2 id="set-root-title">Set root folder</h2>
      <p>Paste the absolute path of the folder that contains your HTML documentation.</p>
      <input
        type="text"
        bind:value={folderPath}
        placeholder="D:\Docs\html"
        aria-label="Root folder path"
        spellcheck="false"
      />
      {#if error}
        <div class="error">{error}</div>
      {/if}
      <div class="modal-actions">
        <button class="btn-ghost" type="button" onclick={() => (folderDialog = false)}>Cancel</button>
        <button class="btn" type="submit" disabled={settingFolder || !folderPath.trim()}>Set folder</button>
      </div>
    </form>
    </div>
  </div>
{/if}
