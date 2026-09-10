<script lang="ts">
  import { onMount } from 'svelte';
  import Tree from './lib/Tree.svelte';
  import SearchField from './lib/SearchField.svelte';
  import { api, viewUrl, type DocumentHit, type Root, type Settings, type TreeNode } from './lib/api';
  import { applyFinds, reveal } from './lib/pageFind';

  let roots = $state<Root[]>([]);
  let tree = $state<TreeNode[]>([]);
  let fileCount = $state(0);
  let truncated = $state(false);
  let query = $state('');
  let searching = $state(false);
  let searchHistory = $state<string[]>([]);
  let pageHistory = $state<string[]>([]);
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
  let listFinding = $state(false);
  let pageQuery = $state('');
  let pageMarks = $state<HTMLElement[]>([]);
  let pageIndex = $state(0);
  let pageFinding = $state(false);
  let pageFindInput = $state<HTMLInputElement | null>(null);

  const SIDEBAR_DEFAULT = 320;
  const SIDEBAR_MIN = 180;
  const SIDEBAR_RIGHT_MIN = 280;
  const SIDEBAR_STORAGE = 'lhr.sidebar_width';
  const HISTORY_STORAGE = 'lhr.search_history';
  const PAGE_HISTORY_STORAGE = 'lhr.page_search_history';
  const HISTORY_MAX = 25;

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

  let searchGen = 0;

  function cacheHistory(storageKey: string, items: string[]) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(items));
    } catch {
      /* ignore */
    }
  }

  function rememberSearch(term: string) {
    const t = term.trim();
    if (!t) return;
    searchHistory = [t, ...searchHistory.filter((item) => item.toLowerCase() !== t.toLowerCase())].slice(
      0,
      HISTORY_MAX,
    );
    cacheHistory(HISTORY_STORAGE, searchHistory);
    void api
      .addHistory('search_history', t)
      .then((res) => {
        searchHistory = res.history;
        cacheHistory(HISTORY_STORAGE, res.history);
      })
      .catch(() => undefined);
  }

  function rememberPageSearch(term: string) {
    const t = term.trim();
    if (!t) return;
    pageHistory = [t, ...pageHistory.filter((item) => item.toLowerCase() !== t.toLowerCase())].slice(
      0,
      HISTORY_MAX,
    );
    cacheHistory(PAGE_HISTORY_STORAGE, pageHistory);
    void api
      .addHistory('page_search_history', t)
      .then((res) => {
        pageHistory = res.history;
        cacheHistory(PAGE_HISTORY_STORAGE, res.history);
      })
      .catch(() => undefined);
  }

  function removeSearchHistory(term: string) {
    searchHistory = searchHistory.filter((item) => item.toLowerCase() !== term.toLowerCase());
    cacheHistory(HISTORY_STORAGE, searchHistory);
    void api
      .removeHistory('search_history', term)
      .then((res) => {
        searchHistory = res.history;
        cacheHistory(HISTORY_STORAGE, res.history);
      })
      .catch(() => undefined);
  }

  function removePageHistory(term: string) {
    pageHistory = pageHistory.filter((item) => item.toLowerCase() !== term.toLowerCase());
    cacheHistory(PAGE_HISTORY_STORAGE, pageHistory);
    void api
      .removeHistory('page_search_history', term)
      .then((res) => {
        pageHistory = res.history;
        cacheHistory(PAGE_HISTORY_STORAGE, res.history);
      })
      .catch(() => undefined);
  }

  function applySharedSettings(s: Settings) {
    const nextSearch = historyFromUnknown(s.search_history);
    const nextPage = historyFromUnknown(s.page_search_history);
    if (JSON.stringify(nextSearch) !== JSON.stringify(searchHistory)) {
      searchHistory = nextSearch;
      cacheHistory(HISTORY_STORAGE, nextSearch);
    }
    if (JSON.stringify(nextPage) !== JSON.stringify(pageHistory)) {
      pageHistory = nextPage;
      cacheHistory(PAGE_HISTORY_STORAGE, nextPage);
    }
    const incoming = (s.roots || []).map((r) => `${r.id}\t${r.path}`).join('\n');
    const current = roots.map((r) => `${r.id}\t${r.path}`).join('\n');
    if (incoming !== current) {
      void refreshRoots().then(() => refreshTree());
    }
  }

  function historyFromUnknown(raw: unknown): string[] {
    if (!Array.isArray(raw)) return [];
    return raw.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()));
  }

  async function refreshTree() {
    const q = query.trim();
    const gen = ++searchGen;
    searching = Boolean(q);
    try {
      const data = await api.tree(q || undefined);
      if (gen !== searchGen) return;
      tree = data.tree;
      fileCount = data.file_count;
      truncated = data.truncated;
      if (q) rememberSearch(q);
    } finally {
      if (gen === searchGen) searching = false;
    }
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
      if (Array.isArray(settings.search_history) && settings.search_history.length) {
        searchHistory = historyFromUnknown(settings.search_history);
      } else {
        try {
          searchHistory = historyFromUnknown(JSON.parse(localStorage.getItem(HISTORY_STORAGE) || '[]'));
        } catch {
          searchHistory = [];
        }
      }
      if (Array.isArray(settings.page_search_history) && settings.page_search_history.length) {
        pageHistory = historyFromUnknown(settings.page_search_history);
      } else {
        try {
          pageHistory = historyFromUnknown(JSON.parse(localStorage.getItem(PAGE_HISTORY_STORAGE) || '[]'));
        } catch {
          pageHistory = [];
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
    scheduleDocFind(true, 'list');
    searching = Boolean(value.trim());
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      void refreshTree();
    }, 200);
  }

  function clearSearch() {
    query = '';
    listQuery = '';
    searching = false;
    searchGen += 1;
    scheduleDocFind(true, 'list');
    void refreshTree();
  }

  function pickHistory(term: string) {
    query = term;
    listQuery = term;
    searching = true;
    scheduleDocFind(true, 'list');
    void refreshTree();
  }

  function clearListFind() {
    listQuery = '';
    scheduleDocFind(true, 'list');
  }

  function pickListHistory(term: string) {
    listQuery = term;
    rememberSearch(term);
    scheduleDocFind(true, 'list');
  }

  function clearPageFind() {
    pageQuery = '';
    scheduleDocFind(false, 'page');
  }

  function pickPageHistory(term: string) {
    pageQuery = term;
    rememberPageSearch(term);
    scheduleDocFind(false, 'page');
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

  let docFindTimer: ReturnType<typeof setTimeout> | undefined;
  let docFindGen = 0;

  function scheduleDocFind(focusList: boolean, which: 'list' | 'page' | 'both') {
    const gen = ++docFindGen;
    if (which === 'list' || which === 'both') listFinding = Boolean(listQuery.trim());
    if (which === 'page' || which === 'both') pageFinding = Boolean(pageQuery.trim());
    clearTimeout(docFindTimer);
    if (!listQuery.trim() && !pageQuery.trim()) {
      runAllFinds(focusList);
      if (gen === docFindGen) {
        listFinding = false;
        pageFinding = false;
      }
      return;
    }
    docFindTimer = setTimeout(() => {
      requestAnimationFrame(() => {
        if (gen !== docFindGen) return;
        runAllFinds(focusList);
        if (gen === docFindGen) {
          listFinding = false;
          pageFinding = false;
        }
      });
    }, 40);
  }

  let listHistTimer: ReturnType<typeof setTimeout> | undefined;
  let pageHistTimer: ReturnType<typeof setTimeout> | undefined;

  function onListSearchInput(value: string) {
    listQuery = value;
    scheduleDocFind(true, 'list');
    clearTimeout(listHistTimer);
    if (value.trim()) {
      listHistTimer = setTimeout(() => rememberSearch(value), 400);
    }
  }

  function onPageSearchInput(value: string) {
    pageQuery = value;
    scheduleDocFind(false, 'page');
    clearTimeout(pageHistTimer);
    if (value.trim()) {
      pageHistTimer = setTimeout(() => rememberPageSearch(value), 400);
    }
  }

  function listFindNext() {
    if (listMarks.length === 0) {
      scheduleDocFind(true, 'list');
      return;
    }
    listIndex = reveal(listMarks, listIndex + 1, 'list');
  }

  function listFindPrev() {
    if (listMarks.length === 0) {
      scheduleDocFind(true, 'list');
      return;
    }
    listIndex = reveal(listMarks, listIndex - 1, 'list');
  }

  function pageFindNext() {
    if (pageMarks.length === 0) {
      scheduleDocFind(false, 'page');
      return;
    }
    pageIndex = reveal(pageMarks, pageIndex + 1, 'page');
  }

  function pageFindPrev() {
    if (pageMarks.length === 0) {
      scheduleDocFind(false, 'page');
      return;
    }
    pageIndex = reveal(pageMarks, pageIndex - 1, 'page');
  }

  function onIframeLoad() {
    scheduleDocFind(Boolean(listQuery.trim()), 'both');
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
      if (inField && target?.closest('.list-find-field')) {
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
    const stopWatch = api.watchSettings(applySharedSettings);
    const onResize = () => {
      sidebarWidth = clampSidebar(sidebarWidth);
    };
    window.addEventListener('keydown', onKeydown);
    window.addEventListener('click', onWindowClick);
    window.addEventListener('resize', onResize);
    return () => {
      stopWatch();
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
        <SearchField
          value={query}
          placeholder="Search in HTML files"
          ariaLabel="Search documents by text"
          history={searchHistory}
          searching={searching}
          onInput={onTreeSearch}
          onClear={clearSearch}
          onPick={pickHistory}
          onRemove={removeSearchHistory}
        />
        {#if query.trim()}
          <div class="muted">
            {#if searching}
              Searching files…
            {:else}
              {fileCount} matching file{fileCount === 1 ? '' : 's'}
              {#if truncated} (truncated){/if}
            {/if}
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
              <SearchField
                value={listQuery}
                placeholder="From list search"
                ariaLabel="Search this page for the document-list search term"
                history={searchHistory}
                searching={listFinding}
                extraClass="list-find-field"
                onInput={onListSearchInput}
                onClear={clearListFind}
                onPick={pickListHistory}
                onRemove={removeSearchHistory}
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
              <SearchField
                value={pageQuery}
                placeholder="Find in page"
                ariaLabel="Find in the open document"
                history={pageHistory}
                searching={pageFinding}
                extraClass="page-find-field"
                onInput={onPageSearchInput}
                onClear={clearPageFind}
                onPick={pickPageHistory}
                onRemove={removePageHistory}
                bindInput={(el) => {
                  pageFindInput = el;
                }}
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
