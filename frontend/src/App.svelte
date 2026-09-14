<script lang="ts">
  import { onMount } from 'svelte';
  import Tree from './lib/Tree.svelte';
  import SearchField from './lib/SearchField.svelte';
  import PathContextMenu from './lib/PathContextMenu.svelte';
  import ProjectContextMenu from './lib/ProjectContextMenu.svelte';
  import { api, viewUrl, windowsFullPath, windowsRelPath, type DocumentHit, type Project, type Root, type Settings, type TreeNode } from './lib/api';
  import { applyFinds, reveal } from './lib/pageFind';

  let roots = $state<Root[]>([]);
  let projects = $state<Project[]>([]);
  let currentSlug = $state<string | null>(null);
  let projectDialog = $state<'new' | 'rename' | null>(null);
  let projectNameDraft = $state('');
  let projectsEpoch = $state(0);
  let tree = $state<TreeNode[]>([]);
  let fileCount = $state(0);
  let truncated = $state(false);
  let query = $state('');
  let appliedQuery = $state('');
  let searching = $state(false);
  let searchHistory = $state<string[]>([]);
  let pageHistory = $state<string[]>([]);
  let selected = $state<DocumentHit | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let version = $state('');
  let inWebview = $state(false);

  let menuOpen = $state(false);
  let pathMenu = $state<{ x: number; y: number; full: string; rel: string } | null>(null);
  let projectMenu = $state<{ x: number; y: number; slug: string; name: string } | null>(null);
  let projectActionSlug = $state<string | null>(null);
  let folderDialog = $state(false);
  let folderPath = $state('');
  let settingFolder = $state(false);

  let iframeEl = $state<HTMLIFrameElement | null>(null);
  let listQuery = $state('');
  let listMarks = $state<HTMLElement[]>([]);
  let listIndex = $state(0);
  let listFinding = $state(false);
  let listMatchCount = $state(0);
  let pageQuery = $state('');
  let pageMarks = $state<HTMLElement[]>([]);
  let pageIndex = $state(0);
  let pageFinding = $state(false);
  let pageMatchCount = $state(0);
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

  let currentProject = $derived(projects.find((p) => p.slug === currentSlug) ?? null);
  let rootLabel = $derived(currentProject?.name || 'No project');

  async function loadProjects() {
    const data = await api.projects();
    projects = data.projects;
    currentSlug = data.current_slug;
  }

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
    const epoch = Number(s.projects_epoch || 0);
    const slugChanged = (s.last_project_slug || null) !== currentSlug;
    if (epoch !== projectsEpoch || slugChanged || incoming !== current) {
      projectsEpoch = epoch;
      void loadProjects()
        .then(() => refreshRoots())
        .then(() => refreshTree());
    }
  }

  function historyFromUnknown(raw: unknown): string[] {
    if (!Array.isArray(raw)) return [];
    return raw.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()));
  }

  let treeAbort: AbortController | null = null;

  async function refreshTree() {
    const q = query.trim();
    appliedQuery = q;
    const gen = ++searchGen;
    treeAbort?.abort();
    treeAbort = new AbortController();
    const signal = treeAbort.signal;
    searching = Boolean(q);
    if (q) fileCount = 0;
    try {
      if (!q) {
        const data = await api.tree();
        if (gen !== searchGen) return;
        tree = data.tree;
        fileCount = data.file_count;
        truncated = data.truncated;
        return;
      }
      const data = await api.treeStream(
        q,
        (n) => {
          if (gen === searchGen) fileCount = n;
        },
        signal,
      );
      if (gen !== searchGen) return;
      tree = data.tree;
      fileCount = data.file_count;
      truncated = data.truncated;
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (gen === searchGen) error = err instanceof Error ? err.message : String(err);
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
      projectsEpoch = Number(settings.projects_epoch || 0);
      await loadProjects();
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

  function folderLabel(path: string): string {
    const parts = path.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean);
    if (parts.length >= 2) return parts.slice(-2).join('\\');
    return parts[0] || path;
  }

  function openFolderDialog() {
    menuOpen = false;
    folderPath = '';
    folderDialog = true;
    error = null;
  }

  async function applyRootFolder() {
    const path = folderPath.trim();
    if (!path) return;
    settingFolder = true;
    error = null;
    try {
      if (!currentSlug) {
        const created = await api.createProject('Default');
        currentSlug = created.slug;
      }
      await api.addRoot(path);
      folderDialog = false;
      await loadProjects();
      await refreshRoots();
      await refreshTree();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      settingFolder = false;
    }
  }

  async function selectProject(slug: string) {
    error = null;
    try {
      const proj = await api.selectProject(slug);
      currentSlug = proj.slug;
      await loadProjects();
      await refreshRoots();
      await refreshTree();
      const last = proj.last_document;
      if (last) {
        selected = {
          root_id: last.root_id,
          root_path: (proj.folders || []).find((f) => f.id === last.root_id)?.path || '',
          rel: last.rel,
          name: last.rel.split('/').pop() || last.rel,
          size: 0,
          mtime: 0,
        };
      } else {
        selected = null;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function createNamedProject() {
    const name = projectNameDraft.trim();
    if (!name) return;
    error = null;
    try {
      const proj = await api.createProject(name);
      projectDialog = null;
      projectNameDraft = '';
      menuOpen = false;
      await selectProject(proj.slug);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function renameCurrentProject() {
    const name = projectNameDraft.trim();
    const slug = projectActionSlug || currentSlug;
    if (!name || !slug) return;
    error = null;
    try {
      await api.renameProject(slug, name);
      projectDialog = null;
      projectNameDraft = '';
      projectActionSlug = null;
      await loadProjects();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function deleteNamedProject(slug: string, name: string) {
    projectMenu = null;
    if (!confirm(`Delete project “${name}”? Folders on disk are not deleted.`)) return;
    error = null;
    try {
      await api.deleteProject(slug);
      menuOpen = false;
      if (slug === currentSlug) selected = null;
      await loadProjects();
      await refreshRoots();
      await refreshTree();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function openProjectContextMenu(event: MouseEvent, proj: Project) {
    event.preventDefault();
    event.stopPropagation();
    pathMenu = null;
    projectMenu = { x: event.clientX, y: event.clientY, slug: proj.slug, name: proj.name };
  }

  async function toggleFolder(id: string, enabled: boolean) {
    if (!currentSlug) return;
    error = null;
    try {
      await api.setFolderEnabled(currentSlug, id, enabled);
      await loadProjects();
      await refreshRoots();
      await refreshTree();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function removeFolder(id: string) {
    if (!currentSlug) return;
    error = null;
    try {
      await api.removeRoot(id);
      if (selected?.root_id === id) selected = null;
      await loadProjects();
      await refreshRoots();
      await refreshTree();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
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

  function onTreeType(value: string) {
    query = value;
  }

  function commitTreeSearch() {
    listQuery = query;
    searching = Boolean(query.trim());
    scheduleDocFind(true, 'list');
    void refreshTree();
  }

  function clearSearch() {
    query = '';
    appliedQuery = '';
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
    scheduleDocFind(true, 'list');
  }

  function clearPageFind() {
    pageQuery = '';
    scheduleDocFind(false, 'page');
  }

  function pickPageHistory(term: string) {
    pageQuery = term;
    scheduleDocFind(false, 'page');
  }

  function iframeDoc(): Document | null {
    try {
      return iframeEl?.contentDocument ?? null;
    } catch {
      return null;
    }
  }

  let docFindTimer: ReturnType<typeof setTimeout> | undefined;
  let docFindGen = 0;

  async function runAllFinds(focusList = false, gen = docFindGen) {
    const doc = iframeDoc();
    if (!doc) {
      listMarks = [];
      pageMarks = [];
      listIndex = 0;
      pageIndex = 0;
      listMatchCount = 0;
      pageMatchCount = 0;
      return;
    }
    const found = await applyFinds(
      doc,
      listQuery,
      pageQuery,
      (layer, count) => {
        if (gen !== docFindGen) return;
        if (layer === 'list') listMatchCount = count;
        else pageMatchCount = count;
      },
      () => gen !== docFindGen,
    );
    if (gen !== docFindGen) return;
    listMarks = found.list;
    pageMarks = found.page;
    listMatchCount = found.list.length;
    pageMatchCount = found.page.length;
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

  function scheduleDocFind(focusList: boolean, which: 'list' | 'page' | 'both') {
    const gen = ++docFindGen;
    if (which === 'list' || which === 'both') {
      listFinding = Boolean(listQuery.trim());
      listMatchCount = 0;
    }
    if (which === 'page' || which === 'both') {
      pageFinding = Boolean(pageQuery.trim());
      pageMatchCount = 0;
    }
    clearTimeout(docFindTimer);
    const run = () => {
      void runAllFinds(focusList, gen).finally(() => {
        if (gen !== docFindGen) return;
        listFinding = false;
        pageFinding = false;
      });
    };
    if (!listQuery.trim() && !pageQuery.trim()) {
      run();
      return;
    }
    docFindTimer = setTimeout(run, 40);
  }

  function onListType(value: string) {
    listQuery = value;
  }

  function commitListSearch() {
    scheduleDocFind(true, 'list');
  }

  function onPageType(value: string) {
    pageQuery = value;
  }

  function commitPageSearch() {
    scheduleDocFind(false, 'page');
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

  function isPdfHit(doc: DocumentHit | null): boolean {
    return Boolean(doc?.rel?.toLowerCase().endsWith('.pdf'));
  }

  function onIframeLoad() {
    if (isPdfHit(selected)) return;
    scheduleDocFind(Boolean(listQuery.trim()), 'both');
  }

  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    const inField = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f' && selected) {
      if (isPdfHit(selected)) return;
      event.preventDefault();
      pageFindInput?.focus();
      pageFindInput?.select();
      return;
    }
    if (event.key === 'F3' && selected) {
      if (isPdfHit(selected)) return;
      event.preventDefault();
      if (event.shiftKey) pageFindPrev();
      else pageFindNext();
      return;
    }
    if (event.key === 'Escape') {
      pathMenu = null;
      projectMenu = null;
      if (folderDialog) folderDialog = false;
      if (projectDialog) projectDialog = null;
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

  function webviewApi():
    | {
        toggle_fullscreen?: () => Promise<unknown>;
        toggle_maximize?: () => Promise<unknown>;
        minimize?: () => Promise<unknown>;
        close_app?: () => Promise<unknown>;
        start_resize?: (edge: string) => Promise<unknown>;
        start_drag?: () => Promise<unknown>;
      }
    | undefined {
    return (
      window as unknown as {
        pywebview?: {
          api?: {
            toggle_fullscreen?: () => Promise<unknown>;
            toggle_maximize?: () => Promise<unknown>;
            minimize?: () => Promise<unknown>;
            close_app?: () => Promise<unknown>;
            start_resize?: (edge: string) => Promise<unknown>;
            start_drag?: () => Promise<unknown>;
          };
        };
      }
    ).pywebview?.api;
  }

  function startWinResize(edge: string, e?: PointerEvent) {
    e?.preventDefault();
    e?.stopPropagation();
    void webviewApi()?.start_resize?.(edge);
  }

  function isTopbarInteractive(t: EventTarget | null): boolean {
    if (!(t instanceof Element)) return false;
    return Boolean(
      t.closest(
        'button, a, input, select, textarea, .window-chrome, .win-resize, .menu, .search-wrap, .path-menu',
      ),
    );
  }

  function onTopbarPointerDown(e: PointerEvent) {
    if (!inWebview || e.button !== 0) return;
    if (isTopbarInteractive(e.target)) return;
    e.preventDefault();
    void webviewApi()?.start_drag?.();
  }

  function onTopbarDblClick(e: MouseEvent) {
    if (!inWebview) return;
    if (isTopbarInteractive(e.target)) return;
    void webviewApi()?.toggle_maximize?.();
  }

  function openPathMenu(event: MouseEvent, rootPath: string, rel: string) {
    event.preventDefault();
    event.stopPropagation();
    pathMenu = {
      x: event.clientX,
      y: event.clientY,
      full: windowsFullPath(rootPath, rel),
      rel: windowsRelPath(rel),
    };
  }

  onMount(() => {
    void boot();
    const stopWatch = api.watchSettings(applySharedSettings);
    const onResize = () => {
      sidebarWidth = clampSidebar(sidebarWidth);
    };
    const syncWebview = () => {
      inWebview =
        document.documentElement.getAttribute('data-webview') === '1' || Boolean(webviewApi());
    };
    syncWebview();
    const webviewTick = setInterval(() => {
      syncWebview();
      if (inWebview) clearInterval(webviewTick);
    }, 200);
    window.addEventListener('keydown', onKeydown);
    window.addEventListener('click', onWindowClick);
    window.addEventListener('resize', onResize);
    return () => {
      stopWatch();
      clearInterval(webviewTick);
      window.removeEventListener('keydown', onKeydown);
      window.removeEventListener('click', onWindowClick);
      window.removeEventListener('resize', onResize);
    };
  });
</script>

<div class="app">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <header class="topbar" onpointerdown={onTopbarPointerDown} ondblclick={onTopbarDblClick}>
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
          {rootLabel}
        </button>
        {#if menuOpen}
          <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
          <div class="menu-drop project-menu" role="menu" tabindex="-1" onclick={(e) => e.stopPropagation()}>
            <div class="menu-heading">Projects</div>
            {#each projects as proj (proj.slug)}
              <button
                type="button"
                role="menuitem"
                class:current={proj.slug === currentSlug}
                onclick={() => void selectProject(proj.slug)}
                oncontextmenu={(e) => openProjectContextMenu(e, proj)}
              >
                {proj.slug === currentSlug ? '● ' : '○ '}{proj.name}
              </button>
            {/each}
            <button
              type="button"
              role="menuitem"
              onclick={() => {
                projectNameDraft = '';
                projectDialog = 'new';
              }}
            >+ New project…</button>
            <div class="menu-heading">Folders in this project</div>
            {#if !currentSlug}
              <div class="menu-hint">Create a project, then add documentation folders.</div>
            {:else if (currentProject?.folders.length ?? 0) === 0}
              <div class="menu-hint">No folders yet. Add one below.</div>
            {:else}
              {#each currentProject?.folders || [] as folder (folder.id)}
                <label
                  class="folder-check"
                  oncontextmenu={(e) => openPathMenu(e, folder.path, '')}
                >
                  <input
                    type="checkbox"
                    checked={folder.enabled}
                    onchange={(e) => void toggleFolder(folder.id, e.currentTarget.checked)}
                  />
                  <span title={folder.path}>{folderLabel(folder.path)}</span>
                  <button
                    type="button"
                    class="folder-remove"
                    title="Remove folder from project"
                    onclick={() => void removeFolder(folder.id)}
                  >×</button>
                </label>
              {/each}
            {/if}
            <button type="button" role="menuitem" onclick={openFolderDialog} disabled={!currentSlug}>
              + Add folder…
            </button>
          </div>
        {/if}
      </div>
      <div class="brand">
        <h1>Local HTML Reader</h1>
        <span title={rootLabel}>{rootLabel}</span>
      </div>
    </div>
    <div class="status">v{version || '…'} · 127.0.0.1:8766</div>
    {#if inWebview}
      <div class="window-chrome" role="group" aria-label="Window">
        <button
          type="button"
          class="window-chrome-btn"
          title="Minimize"
          onclick={() => void webviewApi()?.minimize?.()}
        >─</button>
        <button
          type="button"
          class="window-chrome-btn"
          title="Maximize"
          onclick={() => void webviewApi()?.toggle_maximize?.()}
        >□</button>
        <button
          type="button"
          class="window-chrome-btn window-chrome-close"
          title="Close"
          onclick={() => void webviewApi()?.close_app?.()}
        >✕</button>
      </div>
    {/if}
  </header>
  {#if inWebview}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize n" onpointerdown={(e) => startWinResize('top', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize s" onpointerdown={(e) => startWinResize('bottom', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize e" onpointerdown={(e) => startWinResize('right', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize w" onpointerdown={(e) => startWinResize('left', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize nw" onpointerdown={(e) => startWinResize('top-left', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize ne" onpointerdown={(e) => startWinResize('top-right', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize sw" onpointerdown={(e) => startWinResize('bottom-left', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize se" onpointerdown={(e) => startWinResize('bottom-right', e)}></div>
  {/if}

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
          placeholder="Search in HTML, PDF, and Markdown"
          ariaLabel="Search documents by text"
          history={searchHistory}
          searching={searching}
          onInput={onTreeType}
          onClear={clearSearch}
          onPick={pickHistory}
          onRemove={removeSearchHistory}
          onCommitHistory={rememberSearch}
          onSearch={commitTreeSearch}
        />
        {#if searching || appliedQuery}
          <div class="muted">
            {#if searching}
              Searching… {fileCount} matching file{fileCount === 1 ? '' : 's'}
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
        {:else if roots.filter((r) => r.enabled !== false).length === 0}
          <div class="empty">
            No folders are enabled. Open the project menu (top left), check a folder, or add one.
            HTML files stay on disk; this app only reads them.
          </div>
        {:else if tree.length === 0}
          <div class="empty">
            {#if appliedQuery}
              No HTML files contain that text.
            {:else}
              No HTML, PDF, or Markdown files in the enabled folders.
            {/if}
          </div>
        {:else}
          <Tree
            nodes={tree}
            {selected}
            onOpen={openDoc}
            onPathMenu={(e, node) => openPathMenu(e, node.root_path, node.rel)}
          />
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
          <code
            class="doc-path"
            title={windowsFullPath(selected.root_path, selected.rel)}
            oncontextmenu={(e) => {
              if (!selected) return;
              openPathMenu(e, selected.root_path, selected.rel);
            }}
          >{windowsRelPath(selected.rel)}</code>
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
                onInput={onListType}
                onClear={clearListFind}
                onPick={pickListHistory}
                onRemove={removeSearchHistory}
                onCommitHistory={rememberSearch}
                onSearch={commitListSearch}
              />
              {#if listQuery.trim()}
                <span class="find-count">
                  {#if listFinding}
                    {listMatchCount}
                  {:else}
                    {listMarks.length ? `${listIndex + 1} / ${listMarks.length}` : '0 / 0'}
                  {/if}
                </span>
              {/if}
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
                onInput={onPageType}
                onClear={clearPageFind}
                onPick={pickPageHistory}
                onRemove={removePageHistory}
                onCommitHistory={rememberPageSearch}
                onSearch={commitPageSearch}
                bindInput={(el) => {
                  pageFindInput = el;
                }}
              />
              {#if pageQuery.trim()}
                <span class="find-count">
                  {#if pageFinding}
                    {pageMatchCount}
                  {:else}
                    {pageMarks.length ? `${pageIndex + 1} / ${pageMarks.length}` : '0 / 0'}
                  {/if}
                </span>
              {/if}
              <button class="btn-ghost btn-small" type="button" onclick={pageFindPrev} disabled={!pageMarks.length}>Prev</button>
              <button class="btn-ghost btn-small" type="submit" disabled={!pageQuery.trim()}>Next</button>
            </form>
          </div>
        </div>
        {#key `${selected.root_id}:${selected.rel}`}
          {#if isPdfHit(selected)}
            <embed
              class="doc-frame"
              type="application/pdf"
              title={selected.name}
              src={viewUrl(selected.root_id, selected.rel)}
            />
          {:else}
            <iframe
              class="doc-frame"
              bind:this={iframeEl}
              title={selected.name}
              src={viewUrl(selected.root_id, selected.rel)}
              sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
              onload={onIframeLoad}
            ></iframe>
          {/if}
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
      <h2 id="set-root-title">Add folder</h2>
      <p>Paste an absolute folder path. It is added to the current project; uncheck it in the menu to hide it from the tree and search.</p>
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
        <button class="btn" type="submit" disabled={settingFolder || !folderPath.trim()}>Add folder</button>
      </div>
    </form>
    </div>
  </div>
{/if}

{#if projectDialog}
  <div
    class="modal-backdrop"
    onclick={(e) => {
      if (e.currentTarget === e.target) projectDialog = null;
    }}
    role="presentation"
  >
    <div class="modal" role="dialog" aria-labelledby="project-dialog-title">
      <form
        onsubmit={(e) => {
          e.preventDefault();
          if (projectDialog === 'rename') void renameCurrentProject();
          else void createNamedProject();
        }}
      >
        <h2 id="project-dialog-title">{projectDialog === 'rename' ? 'Rename project' : 'New project'}</h2>
        <p>A project holds its own list of documentation folders.</p>
        <input
          type="text"
          bind:value={projectNameDraft}
          placeholder="Kingfisher"
          aria-label="Project name"
        />
        {#if error}
          <div class="error">{error}</div>
        {/if}
        <div class="modal-actions">
          <button class="btn-ghost" type="button" onclick={() => (projectDialog = null)}>Cancel</button>
          <button class="btn" type="submit" disabled={!projectNameDraft.trim()}>
            {projectDialog === 'rename' ? 'Rename' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if projectMenu}
  <ProjectContextMenu
    x={projectMenu.x}
    y={projectMenu.y}
    name={projectMenu.name}
    onRename={() => {
      projectActionSlug = projectMenu?.slug || null;
      projectNameDraft = projectMenu?.name || '';
      projectMenu = null;
      projectDialog = 'rename';
    }}
    onDelete={() => {
      const slug = projectMenu?.slug;
      const name = projectMenu?.name || slug || '';
      if (slug) void deleteNamedProject(slug, name);
    }}
    onClose={() => {
      projectMenu = null;
    }}
  />
{/if}

{#if pathMenu}
  <PathContextMenu
    x={pathMenu.x}
    y={pathMenu.y}
    full={pathMenu.full}
    rel={pathMenu.rel}
    onClose={() => {
      pathMenu = null;
    }}
  />
{/if}
