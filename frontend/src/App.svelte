<script lang="ts">
  import { onMount } from 'svelte';
  import Tree from './lib/Tree.svelte';
  import SearchField from './lib/SearchField.svelte';
  import PathContextMenu from './lib/PathContextMenu.svelte';
  import ProjectContextMenu from './lib/ProjectContextMenu.svelte';
  import { api, historyFromUnknown, searchFlagsFromUnknown, setApiProject, viewUrl, windowsFullPath, windowsRelPath, type DocumentHit, type Project, type Root, type SearchHistoryItem, type SearchWorker, type Settings, type TreeNode } from './lib/api';
  import PdfViewer from './lib/PdfViewer.svelte';
  import CopyPopup from './lib/CopyPopup.svelte';
  import { applyFinds, reveal } from './lib/pageFind';
  import { copyImageToClipboard, copyToClipboard, selectedTextIn, wordAtPoint } from './lib/wordAtPoint';

  let roots = $state<Root[]>([]);
  let projects = $state<Project[]>([]);
  let currentSlug = $state<string | null>(null);
  let projectDialog = $state<'new' | 'rename' | null>(null);
  let projectNameDraft = $state('');
  let projectsEpoch = $state(0);
  let tree = $state<TreeNode[]>([]);
  let fileCount = $state(0);
  let searchWorkers = $state<SearchWorker[]>([]);
  let truncated = $state(false);
  let query = $state('');
  let treeRegex = $state(false);
  let treeMatchCase = $state(false);
  let treeWholeWord = $state(false);
  let pageRegex = $state(false);
  let pageMatchCase = $state(false);
  let pageWholeWord = $state(false);
  let appliedQuery = $state('');
  let searching = $state(false);
  let searchHistory = $state<SearchHistoryItem[]>([]);
  let pageHistory = $state<SearchHistoryItem[]>([]);
  let selected = $state<DocumentHit | null>(null);
  let openingKey = $state<string | null>(null);
  let loadedKey = $state<string | null>(null);
  let pageSummary = $state('');
  let loading = $state(true);
  let error = $state<string | null>(null);
  let version = $state('');
  let serverOk = $state(true);
  const ZOOM_MIN = 0.5;
  const ZOOM_MAX = 2;
  let uiZoom = $state(1);

  function clampZoom(value: number): number {
    return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, value));
  }

  function setUiZoom(value: number) {
    uiZoom = clampZoom(value);
    try {
      localStorage.setItem('lhr-ui-zoom', String(uiZoom));
    } catch {
      /* ignore */
    }
  }

  function zoomFromPointerScrub(startZoom: number, dx: number, dy: number): number {
    return clampZoom(startZoom * Math.exp((dx - dy) * 0.008));
  }

  function zoomFromWheelDelta(oldZoom: number, deltaY: number, deltaMode = 0): number {
    let dy = deltaY;
    if (deltaMode === 1) dy *= 16;
    if (deltaMode === 2) dy *= 800;
    return clampZoom(oldZoom * Math.exp(-dy * 0.0015));
  }

  const zoomScrub = {
    pointerId: -1,
    startX: 0,
    startY: 0,
    startZoom: 1,
    dragging: false,
  };

  function endZoomScrub() {
    zoomScrub.pointerId = -1;
    zoomScrub.dragging = false;
    document.body.classList.remove('lhr-zoom-scrubbing');
    window.removeEventListener('pointermove', onZoomScrubMove, true);
    window.removeEventListener('pointerup', onZoomScrubUp, true);
    window.removeEventListener('pointercancel', onZoomScrubUp, true);
  }

  function onZoomReadoutPointerDown(e: PointerEvent) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    zoomScrub.pointerId = e.pointerId;
    zoomScrub.startX = e.clientX;
    zoomScrub.startY = e.clientY;
    zoomScrub.startZoom = uiZoom;
    zoomScrub.dragging = false;
    window.addEventListener('pointermove', onZoomScrubMove, true);
    window.addEventListener('pointerup', onZoomScrubUp, true);
    window.addEventListener('pointercancel', onZoomScrubUp, true);
  }

  function onZoomScrubMove(e: PointerEvent) {
    if (e.pointerId !== zoomScrub.pointerId) return;
    const dx = e.clientX - zoomScrub.startX;
    const dy = e.clientY - zoomScrub.startY;
    if (!zoomScrub.dragging && Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
    zoomScrub.dragging = true;
    document.body.classList.add('lhr-zoom-scrubbing');
    e.preventDefault();
    setUiZoom(zoomFromPointerScrub(zoomScrub.startZoom, dx, dy));
  }

  function onZoomScrubUp(e: PointerEvent) {
    if (e.pointerId !== zoomScrub.pointerId) return;
    endZoomScrub();
  }

  function onZoomWheel(e: WheelEvent) {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setUiZoom(zoomFromWheelDelta(uiZoom, e.deltaY, e.deltaMode));
  }
  let inWebview = $state(false);

  let menuOpen = $state(false);
  let pathMenu = $state<{
    x: number;
    y: number;
    full: string;
    rel: string;
    file: boolean;
    rootId: string;
    relApi: string;
  } | null>(null);
  let projectMenu = $state<{ x: number; y: number; slug: string; name: string } | null>(null);
  let projectActionSlug = $state<string | null>(null);
  let folderDialog = $state(false);
  let folderPath = $state('');
  let settingFolder = $state(false);

  let iframeEl = $state<HTMLIFrameElement | null>(null);
  let pdfRootEl = $state<HTMLElement | null>(null);
  let heldHtml = $state<DocumentHit | null>(null);
  let htmlCopyMenu = $state<{ x: number; y: number; text: string; image: HTMLImageElement | null } | null>(
    null,
  );
  let iframeCopyCleanup: (() => void) | null = null;
  let listQuery = $state('');
  let listMarks = $state<HTMLElement[]>([]);
  let listIndex = $state(0);
  let listFinding = $state(false);
  let listFindParallel = $state(false);
  let listFindThreads = $state(0);
  let listMatchCount = $state(0);
  let pageQuery = $state('');
  let pageMarks = $state<HTMLElement[]>([]);
  let pageIndex = $state(0);
  let pageFinding = $state(false);
  let pageFindParallel = $state(false);
  let pageFindThreads = $state(0);
  let pageMatchCount = $state(0);
  let pageFindInput = $state<HTMLInputElement | null>(null);

  const SIDEBAR_DEFAULT = 320;
  const SIDEBAR_MIN = 180;
  const SIDEBAR_RIGHT_MIN = 280;
  const SIDEBAR_STORAGE = 'lhr.sidebar_width';
  const HISTORY_STORAGE = 'lhr.search_history';
  const PAGE_HISTORY_STORAGE = 'lhr.page_search_history';
  const SESSION_PROJECT = 'lhr.project.slug';
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

  function persistSessionProject(slug: string | null) {
    setApiProject(slug);
    try {
      if (slug) sessionStorage.setItem(SESSION_PROJECT, slug);
      else sessionStorage.removeItem(SESSION_PROJECT);
    } catch {
      /* ignore */
    }
  }

  function readSessionProject(): string | null {
    try {
      return sessionStorage.getItem(SESSION_PROJECT);
    } catch {
      return null;
    }
  }

  async function loadProjects() {
    const data = await api.projects();
    projects = data.projects;
    const slugs = new Set(projects.map((p) => p.slug));
    if (currentSlug && slugs.has(currentSlug)) {
      persistSessionProject(currentSlug);
      return;
    }
    const stored = readSessionProject();
    const next = stored && slugs.has(stored) ? stored : data.current_slug;
    currentSlug = next;
    persistSessionProject(currentSlug);
  }

  async function refreshRoots() {
    const data = await api.roots();
    roots = data.roots;
  }

  let searchGen = 0;

  function cacheHistory(storageKey: string, items: SearchHistoryItem[]) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(items));
    } catch {
      /* ignore */
    }
  }

  function rememberSearch(
    term: string,
    flags: { regex?: boolean; matchCase?: boolean; wholeWord?: boolean } = {},
  ) {
    const t = term.trim();
    if (!t) return;
    const item = {
      term: t,
      regex: Boolean(flags.regex),
      matchCase: Boolean(flags.matchCase),
      wholeWord: Boolean(flags.wholeWord),
    };
    searchHistory = [
      item,
      ...searchHistory.filter((row) => row.term.toLowerCase() !== t.toLowerCase()),
    ].slice(0, HISTORY_MAX);
    cacheHistory(HISTORY_STORAGE, searchHistory);
    void api
      .addHistory('search_history', t, item)
      .then((res) => {
        searchHistory = historyFromUnknown(res.history, searchHistory);
        cacheHistory(HISTORY_STORAGE, searchHistory);
      })
      .catch(() => undefined);
  }

  function rememberPageSearch(
    term: string,
    flags: { regex?: boolean; matchCase?: boolean; wholeWord?: boolean } = {},
  ) {
    const t = term.trim();
    if (!t) return;
    const item = {
      term: t,
      regex: Boolean(flags.regex),
      matchCase: Boolean(flags.matchCase),
      wholeWord: Boolean(flags.wholeWord),
    };
    pageHistory = [
      item,
      ...pageHistory.filter((row) => row.term.toLowerCase() !== t.toLowerCase()),
    ].slice(0, HISTORY_MAX);
    cacheHistory(PAGE_HISTORY_STORAGE, pageHistory);
    void api
      .addHistory('page_search_history', t, item)
      .then((res) => {
        pageHistory = historyFromUnknown(res.history, pageHistory);
        cacheHistory(PAGE_HISTORY_STORAGE, pageHistory);
      })
      .catch(() => undefined);
  }

  function removeSearchHistory(term: string) {
    searchHistory = searchHistory.filter((item) => item.term.toLowerCase() !== term.toLowerCase());
    cacheHistory(HISTORY_STORAGE, searchHistory);
    void api
      .removeHistory('search_history', term)
      .then((res) => {
        searchHistory = historyFromUnknown(res.history, searchHistory);
        cacheHistory(HISTORY_STORAGE, searchHistory);
      })
      .catch(() => undefined);
  }

  function removePageHistory(term: string) {
    pageHistory = pageHistory.filter((item) => item.term.toLowerCase() !== term.toLowerCase());
    cacheHistory(PAGE_HISTORY_STORAGE, pageHistory);
    void api
      .removeHistory('page_search_history', term)
      .then((res) => {
        pageHistory = historyFromUnknown(res.history, pageHistory);
        cacheHistory(PAGE_HISTORY_STORAGE, pageHistory);
      })
      .catch(() => undefined);
  }

  function applySharedSettings(s: Settings) {
    const nextSearch = historyFromUnknown(s.search_history, searchHistory);
    const nextPage = historyFromUnknown(s.page_search_history, pageHistory);
    if (JSON.stringify(nextSearch) !== JSON.stringify(searchHistory)) {
      searchHistory = nextSearch;
      cacheHistory(HISTORY_STORAGE, nextSearch);
    }
    if (JSON.stringify(nextPage) !== JSON.stringify(pageHistory)) {
      pageHistory = nextPage;
      cacheHistory(PAGE_HISTORY_STORAGE, nextPage);
    }
    const epoch = Number(s.projects_epoch || 0);
    if (epoch !== projectsEpoch) {
      projectsEpoch = epoch;
      void loadProjects()
        .then(() => refreshRoots())
        .then(() => refreshTree());
    }
  }

  let treeAbort: AbortController | null = null;

  function formatMb(bytes: number | undefined): string {
    const mb = (bytes ?? 0) / (1024 * 1024);
    if (mb < 1) return `${mb.toFixed(1)} MB`;
    return `${Math.round(mb)} MB`;
  }

  function formatPages(count: number, estimated: boolean): string {
    const n = Math.max(1, Math.round(count));
    const word = n === 1 ? 'page' : 'pages';
    return estimated ? `about ${n} ${word}` : `${n} ${word}`;
  }

  function estimatePrintedPages(doc: Document): number {
    const text = (doc.body?.innerText || '').replace(/\s+/g, ' ').trim();
    if (!text) return 1;
    // A single-spaced US Letter page holds about 3,000 characters.
    return Math.max(1, Math.ceil(text.length / 3000));
  }

  async function refreshTree() {
    const q = query.trim();
    appliedQuery = q;
    const gen = ++searchGen;
    treeAbort?.abort();
    treeAbort = new AbortController();
    const signal = treeAbort.signal;
    searching = Boolean(q);
    if (q) {
      fileCount = 0;
      tree = [];
      truncated = false;
      searchWorkers = [];
    } else {
      searchWorkers = [];
    }
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
        (n, nextTree, workers) => {
          if (gen !== searchGen) return;
          fileCount = n;
          if (nextTree) tree = nextTree;
          if (workers) {
            searchWorkers = [...workers].sort((a, b) => b.size - a.size || a.slot - b.slot);
          }
        },
        signal,
        { regex: treeRegex, matchCase: treeMatchCase, wholeWord: treeWholeWord },
      );
      if (gen !== searchGen) return;
      tree = data.tree;
      fileCount = data.file_count;
      truncated = data.truncated;
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (gen === searchGen) error = err instanceof Error ? err.message : String(err);
    } finally {
      if (gen === searchGen) {
        searching = false;
        searchWorkers = [];
      }
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
      let cachedSearch: SearchHistoryItem[] = [];
      let cachedPage: SearchHistoryItem[] = [];
      try {
        cachedSearch = historyFromUnknown(JSON.parse(localStorage.getItem(HISTORY_STORAGE) || '[]'));
      } catch {
        cachedSearch = [];
      }
      try {
        cachedPage = historyFromUnknown(JSON.parse(localStorage.getItem(PAGE_HISTORY_STORAGE) || '[]'));
      } catch {
        cachedPage = [];
      }
      if (Array.isArray(settings.search_history) && settings.search_history.length) {
        searchHistory = historyFromUnknown(settings.search_history, cachedSearch);
      } else {
        searchHistory = cachedSearch;
      }
      if (Array.isArray(settings.page_search_history) && settings.page_search_history.length) {
        pageHistory = historyFromUnknown(settings.page_search_history, cachedPage);
      } else {
        pageHistory = cachedPage;
      }
      projectsEpoch = Number(settings.projects_epoch || 0);
      await loadProjects();
      await refreshRoots();
      await refreshTree();
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
        persistSessionProject(currentSlug);
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
    menuOpen = false;
    error = null;
    const switching = slug !== currentSlug;
    try {
      persistSessionProject(slug);
      currentSlug = slug;
      const proj = await api.selectProject(slug);
      currentSlug = proj.slug;
      persistSessionProject(currentSlug);
      await loadProjects();
      await refreshRoots();
      if (switching) clearSearch();
      else await refreshTree();
      const last = proj.last_document;
      if (last) {
        await openDoc({
          root_id: last.root_id,
          root_path: (proj.folders || []).find((f) => f.id === last.root_id)?.path || '',
          rel: last.rel,
          name: last.rel.split('/').pop() || last.rel,
          size: 0,
          mtime: 0,
        });
      } else {
        selected = null;
        loadedKey = null;
        openingKey = null;
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
      if (slug === currentSlug) {
        selected = null;
        loadedKey = null;
        openingKey = null;
      }
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
      if (selected?.root_id === id) {
        selected = null;
        loadedKey = null;
        openingKey = null;
      }
      await loadProjects();
      await refreshRoots();
      await refreshTree();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function openDoc(doc: DocumentHit) {
    const key = docKey(doc);
    if (loadedKey === key || openingKey === key) return;
    openingKey = key;
    pageSummary = '';
    const fromHtml = selected && !isPdfHit(selected);
    if (isPdfHit(doc) && fromHtml) heldHtml = selected;
    else if (!isPdfHit(doc)) heldHtml = null;
    selected = doc;
    pdfRootEl = null;
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

  function commitTreeSearch(value?: string) {
    if (typeof value === 'string') query = value;
    const next = query.trim();
    if (next === appliedQuery) {
      listQuery = query;
      return;
    }
    listQuery = query;
    searching = Boolean(next);
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

  function pickHistory(term: string, flags: unknown = {}) {
    const f = searchFlagsFromUnknown(flags);
    treeRegex = f.regex;
    treeMatchCase = f.matchCase;
    treeWholeWord = f.wholeWord;
    query = term;
    listQuery = term;
    rememberSearch(term, f);
    searching = true;
    scheduleDocFind(true, 'list');
    void refreshTree();
  }

  function clearListFind() {
    listQuery = '';
    scheduleDocFind(true, 'list');
  }

  function pickListHistory(term: string, flags: unknown = {}) {
    const f = searchFlagsFromUnknown(flags);
    treeRegex = f.regex;
    treeMatchCase = f.matchCase;
    treeWholeWord = f.wholeWord;
    listQuery = term;
    rememberSearch(term, f);
    scheduleDocFind(true, 'list');
  }

  function clearPageFind() {
    pageQuery = '';
    scheduleDocFind(false, 'page');
  }

  function pickPageHistory(term: string, flags: unknown = {}) {
    const f = searchFlagsFromUnknown(flags);
    pageRegex = f.regex;
    pageMatchCase = f.matchCase;
    pageWholeWord = f.wholeWord;
    pageQuery = term;
    rememberPageSearch(term, f);
    scheduleDocFind(false, 'page');
  }

  function iframeDoc(): Document | null {
    try {
      return iframeEl?.contentDocument ?? iframeEl?.contentWindow?.document ?? null;
    } catch {
      return null;
    }
  }

  function isPdfHit(doc: DocumentHit | null): boolean {
    return Boolean(doc?.rel?.toLowerCase().endsWith('.pdf'));
  }

  function docKey(doc: { root_id: string; rel: string } | null): string {
    return doc ? `${doc.root_id}:${doc.rel}` : '';
  }

  function clearOpening(doc: { root_id: string; rel: string } | null) {
    if (!doc || openingKey !== docKey(doc)) return;
    openingKey = null;
    loadedKey = docKey(doc);
  }

  function findRoot(): Document | HTMLElement | null {
    if (isPdfHit(selected)) {
      if (pdfRootEl?.isConnected) return pdfRootEl;
      return null;
    }
    const doc = iframeDoc();
    if (!doc) return null;
    return doc.body ?? doc.documentElement ?? doc;
  }

  function withBaseHref(html: string, pageUrl: string): string {
    const abs = new URL(pageUrl, window.location.href);
    const dir = `${abs.origin}${abs.pathname.replace(/[^/]+$/, '')}`;
    const tag = `<base href="${dir.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}">`;
    if (/<base\s/i.test(html)) return html;
    const withHead = html.replace(/<head([^>]*)>/i, (open) => `${open}${tag}`);
    if (withHead !== html) return withHead;
    return `<!doctype html><head>${tag}</head>${html}`;
  }

  async function loadHtmlFrame(doc: DocumentHit, el: HTMLIFrameElement) {
    const url = viewUrl(doc.root_id, doc.rel);
    const key = docKey(doc);
    delete el.dataset.readyKey;
    try {
      const res = await fetch(url, { headers: { Accept: 'text/html,*/*' } });
      if (openingKey !== key) return;
      el.dataset.readyKey = key;
      if (!res.ok) {
        el.src = url;
        return;
      }
      const html = await res.text();
      if (openingKey !== key) return;
      el.removeAttribute('sandbox');
      el.removeAttribute('src');
      el.srcdoc = withBaseHref(html, url);
    } catch {
      if (openingKey !== key) return;
      try {
        el.dataset.readyKey = key;
        el.src = url;
      } catch {
        clearOpening(doc);
      }
    }
  }

  let docFindTimer: ReturnType<typeof setTimeout> | undefined;
  let docFindGen = 0;

  async function runAllFinds(focusList = false, gen = docFindGen) {
    const doc = findRoot();
    if (!doc) {
      listMarks = [];
      pageMarks = [];
      listIndex = 0;
      pageIndex = 0;
      listMatchCount = 0;
      pageMatchCount = 0;
      return;
    }
    let found: { list: HTMLElement[]; page: HTMLElement[] };
    try {
      found = await applyFinds(
        doc,
        listQuery,
        pageQuery,
        (layer, count) => {
          if (gen !== docFindGen) return;
          if (layer === 'list') listMatchCount = count;
          else pageMatchCount = count;
        },
        () => gen !== docFindGen,
        {
          list: { regex: treeRegex, matchCase: treeMatchCase, wholeWord: treeWholeWord },
          page: { regex: pageRegex, matchCase: pageMatchCase, wholeWord: pageWholeWord },
          byteSize: selected?.size ?? 0,
        },
        (layer, parallel) => {
          if (gen !== docFindGen) return;
          if (layer === 'list') listFindParallel = parallel;
          else pageFindParallel = parallel;
        },
        (layer, count) => {
          if (gen !== docFindGen) return;
          if (layer === 'list') listFindThreads = count;
          else pageFindThreads = count;
        },
      );
    } catch {
      listMarks = [];
      pageMarks = [];
      listIndex = 0;
      pageIndex = 0;
      listMatchCount = 0;
      pageMatchCount = 0;
      return;
    }
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
      listFindParallel = false;
      listFindThreads = 0;
      listMatchCount = 0;
    }
    if (which === 'page' || which === 'both') {
      pageFinding = Boolean(pageQuery.trim());
      pageFindParallel = false;
      pageFindThreads = 0;
      pageMatchCount = 0;
    }
    clearTimeout(docFindTimer);
    const run = () => {
      void runAllFinds(focusList, gen).finally(() => {
        if (gen !== docFindGen) return;
        listFinding = false;
        pageFinding = false;
        listFindParallel = false;
        pageFindParallel = false;
        listFindThreads = 0;
        pageFindThreads = 0;
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

  function commitListSearch(value?: string) {
    if (typeof value === 'string') listQuery = value;
    scheduleDocFind(true, 'list');
  }

  function onPageType(value: string) {
    pageQuery = value;
  }

  function commitPageSearch(value?: string) {
    if (typeof value === 'string') pageQuery = value;
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

  function onIframeLoad() {
    const readyKey = iframeEl?.dataset.readyKey;
    if (selected && !isPdfHit(selected) && readyKey && readyKey === docKey(selected)) {
      clearOpening(selected);
      const shown = iframeDoc();
      if (shown) {
        requestAnimationFrame(() => {
          if (!selected || isPdfHit(selected) || docKey(selected) !== readyKey) return;
          pageSummary = formatPages(estimatePrintedPages(shown), true);
        });
      }
    }
    iframeCopyCleanup?.();
    iframeCopyCleanup = null;
    scheduleDocFind(Boolean(listQuery.trim()), 'both');
    const doc = iframeDoc();
    const frame = iframeEl;
    if (!doc || !frame) return;
    const handler = (event: MouseEvent) => {
      const text =
        selectedTextIn(doc.body ?? doc) || wordAtPoint(doc, event.clientX, event.clientY);
      const img = event.target instanceof HTMLImageElement ? event.target : null;
      if (!text && !img) return;
      event.preventDefault();
      event.stopPropagation();
      const rect = frame.getBoundingClientRect();
      htmlCopyMenu = {
        x: event.clientX + rect.left,
        y: event.clientY + rect.top,
        text,
        image: text ? null : img,
      };
    };
    doc.addEventListener('contextmenu', handler);
    iframeCopyCleanup = () => doc.removeEventListener('contextmenu', handler);
  }

  async function copyHtmlSelection() {
    const menu = htmlCopyMenu;
    if (!menu) return;
    try {
      if (menu.text) await copyToClipboard(menu.text);
      else if (menu.image) await copyImageToClipboard(menu.image);
    } catch {
      if (menu.text) await copyToClipboard(menu.text);
    }
    htmlCopyMenu = null;
  }

  function onPdfReady(root: HTMLElement) {
    pdfRootEl = root;
    heldHtml = null;
    if (selected && isPdfHit(selected)) {
      loadedKey = docKey(selected);
      if (openingKey === loadedKey) openingKey = null;
    }
    scheduleDocFind(Boolean(listQuery.trim()), 'both');
  }

  function onPdfPageCount(pages: number, src: string) {
    if (!selected || !isPdfHit(selected)) return;
    if (viewUrl(selected.root_id, selected.rel) !== src) return;
    pageSummary = formatPages(pages, false);
  }

  function onPdfSettled(src: string) {
    if (!selected || !isPdfHit(selected)) return;
    if (viewUrl(selected.root_id, selected.rel) !== src) return;
    if (loadedKey === docKey(selected)) return;
    if (openingKey === docKey(selected)) openingKey = null;
  }

  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    const inField = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');
    if ((event.ctrlKey || event.metaKey) && (event.key === '=' || event.key === '+' || event.key === 'Add')) {
      event.preventDefault();
      setUiZoom(uiZoom * 1.12);
      return;
    }
    if ((event.ctrlKey || event.metaKey) && (event.key === '-' || event.key === '_' || event.key === 'Subtract')) {
      event.preventDefault();
      setUiZoom(uiZoom / 1.12);
      return;
    }
    if ((event.ctrlKey || event.metaKey) && (event.key === '0' || event.key === 'Numpad0')) {
      event.preventDefault();
      setUiZoom(1);
      return;
    }
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
      pathMenu = null;
      projectMenu = null;
      if (folderDialog) folderDialog = false;
      if (projectDialog) projectDialog = null;
      menuOpen = false;
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
        'button, a, input, select, textarea, .zoom-readout, .window-chrome, .win-resize, .menu, .search-wrap, .path-menu',
      ),
    );
  }

  function onTopbarPointerDown(e: PointerEvent) {
    if (!inWebview || e.button !== 0) return;
    if (isTopbarInteractive(e.target)) return;
    const origin = { x: e.clientX, y: e.clientY };
    const onMove = (ev: PointerEvent) => {
      const dx = ev.clientX - origin.x;
      const dy = ev.clientY - origin.y;
      if (dx * dx + dy * dy < 36) return;
      window.removeEventListener('pointermove', onMove, true);
      window.removeEventListener('pointerup', onUp, true);
      void webviewApi()?.start_drag?.();
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove, true);
      window.removeEventListener('pointerup', onUp, true);
    };
    window.addEventListener('pointermove', onMove, true);
    window.addEventListener('pointerup', onUp, true);
  }

  function onTopbarDblClick(e: MouseEvent) {
    if (!inWebview) return;
    if (isTopbarInteractive(e.target)) return;
    e.preventDefault();
    void webviewApi()?.toggle_maximize?.();
  }

  function openPathMenu(
    event: MouseEvent,
    rootPath: string,
    rel: string,
    file = false,
    rootId = '',
  ) {
    event.preventDefault();
    event.stopPropagation();
    pathMenu = {
      x: event.clientX,
      y: event.clientY,
      full: windowsFullPath(rootPath, rel),
      rel: windowsRelPath(rel),
      file,
      rootId,
      relApi: rel,
    };
  }

  async function launchMenuFile() {
    const menu = pathMenu;
    pathMenu = null;
    if (!menu?.file || !menu.rootId) return;
    try {
      await api.launchDocument(menu.rootId, menu.relApi);
    } catch {
      /* the default app reports its own errors */
    }
  }

  $effect(() => {
    const el = iframeEl;
    const doc = heldHtml ?? (selected && !isPdfHit(selected) ? selected : null);
    if (!el || !doc) return;
    void loadHtmlFrame(doc, el);
  });

  async function pingServer() {
    try {
      const health = await api.health();
      serverOk = health.status === 'ok';
      if (health.version) version = health.version;
    } catch {
      serverOk = false;
    }
  }

  onMount(() => {
    void boot();
    void pingServer();
    const healthTick = setInterval(() => void pingServer(), 4000);
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
    window.addEventListener('wheel', onZoomWheel, { passive: false });
    return () => {
      iframeCopyCleanup?.();
      stopWatch();
      clearInterval(healthTick);
      clearInterval(webviewTick);
      endZoomScrub();
      window.removeEventListener('keydown', onKeydown);
      window.removeEventListener('click', onWindowClick);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('wheel', onZoomWheel);
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
          <div
            class="menu-backdrop"
            onclick={() => (menuOpen = false)}
            onpointerdown={(e) => {
              e.preventDefault();
              menuOpen = false;
            }}
          ></div>
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
                menuOpen = false;
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
    <div class="topbar-spacer" title="Drag to move. Double-click to maximize"></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <span
      class="zoom-readout"
      title="Drag to zoom. Double-click to reset to 100%"
      onpointerdown={onZoomReadoutPointerDown}
      ondblclick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setUiZoom(1);
      }}
    >zoom {(uiZoom * 100).toFixed(0)}%</span>
    <div class="status">
      <span>v{version || '…'}</span>
      <span
        class="server-dot"
        class:ok={serverOk}
        class:down={!serverOk}
        title={serverOk ? 'Connected to server' : 'Server disconnected'}
        aria-label={serverOk ? 'Connected to server' : 'Server disconnected'}
      ></span>
    </div>
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
    <div class="win-resize s" onpointerdown={(e) => startWinResize('bottom', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize w" onpointerdown={(e) => startWinResize('left', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize sw" onpointerdown={(e) => startWinResize('bottom-left', e)}></div>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="win-resize se" onpointerdown={(e) => startWinResize('bottom-right', e)}></div>
  {/if}

  <main
    class="layout"
    class:dragging
    bind:this={layoutEl}
    style={`grid-template-columns: ${sidebarWidth}px 6px minmax(0, 1fr); zoom: ${uiZoom}; width: ${100 / uiZoom}%; height: ${100 / uiZoom}%;`}
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
          parallel={searchWorkers.length > 1}
          threadCount={searchWorkers.length}
          onInput={onTreeType}
          onClear={clearSearch}
          onPick={pickHistory}
          onRemove={removeSearchHistory}
          onCommitHistory={rememberSearch}
          onSearch={commitTreeSearch}
          regex={treeRegex}
          matchCase={treeMatchCase}
          wholeWord={treeWholeWord}
          onRegexChange={(on) => {
            treeRegex = on;
            if (query.trim()) void commitTreeSearch();
            else if (listQuery.trim()) commitListSearch();
          }}
          onMatchCaseChange={(on) => {
            treeMatchCase = on;
            if (query.trim()) void commitTreeSearch();
            else if (listQuery.trim()) commitListSearch();
          }}
          onWholeWordChange={(on) => {
            treeWholeWord = on;
            if (query.trim()) void commitTreeSearch();
            else if (listQuery.trim()) commitListSearch();
          }}
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
            {#if searching}
              Searching…
            {:else if appliedQuery}
              No HTML files contain that text.
            {:else}
              No HTML, PDF, or Markdown files in the enabled folders.
            {/if}
          </div>
        {:else}
          <Tree
            nodes={tree}
            {selected}
            {openingKey}
            onOpen={openDoc}
            onPathMenu={(e, node) =>
              openPathMenu(e, node.root_path, node.rel, node.kind === 'file', node.root_id)}
          />
        {/if}
      </div>
      {#if searching && searchWorkers.length}
        <ol class="search-workers">
          {#each searchWorkers as worker (worker.slot)}
            <li>
              <span class="search-worker-n">{worker.slot}.</span>
              <span class="search-worker-name" title={worker.name}>{worker.name}</span>
              <span class="search-worker-size">{formatMb(worker.size)}</span>
            </li>
          {/each}
        </ol>
      {/if}
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
          <div class="doc-heading">
            <code
              class="doc-path"
              title={windowsFullPath(selected.root_path, selected.rel)}
              oncontextmenu={(e) => {
                if (!selected) return;
                openPathMenu(e, selected.root_path, selected.rel);
              }}
            >{windowsRelPath(selected.rel)}</code>
            {#if pageSummary}
              <div class="doc-pages">{pageSummary}</div>
            {/if}
          </div>
          <div class="page-finds">
            <form
              class="page-find list-find"
              onsubmit={(e) => {
                e.preventDefault();
                listFindNext();
              }}
            >
              <span class="find-count">
                {listMarks.length ? `${listIndex + 1} / ${listMarks.length}` : '0 / 0'}
              </span>
              <SearchField
                value={listQuery}
                placeholder="From list search"
                ariaLabel="Search this page for the document-list search term"
                history={searchHistory}
                searching={listFinding}
                parallel={listFindParallel}
                threadCount={listFindThreads}
                extraClass="list-find-field"
                onInput={onListType}
                onClear={clearListFind}
                onPick={pickListHistory}
                onRemove={removeSearchHistory}
                onCommitHistory={rememberSearch}
                onSearch={commitListSearch}
                onNext={listFindNext}
                onPrev={listFindPrev}
                regex={treeRegex}
                matchCase={treeMatchCase}
                wholeWord={treeWholeWord}
                onRegexChange={(on) => {
                  treeRegex = on;
                  if (query.trim()) void commitTreeSearch();
                  else if (listQuery.trim()) commitListSearch();
                }}
                onMatchCaseChange={(on) => {
                  treeMatchCase = on;
                  if (query.trim()) void commitTreeSearch();
                  else if (listQuery.trim()) commitListSearch();
                }}
                onWholeWordChange={(on) => {
                  treeWholeWord = on;
                  if (query.trim()) void commitTreeSearch();
                  else if (listQuery.trim()) commitListSearch();
                }}
              />
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
                parallel={pageFindParallel}
                threadCount={pageFindThreads}
                extraClass="page-find-field"
                onInput={onPageType}
                onClear={clearPageFind}
                onPick={pickPageHistory}
                onRemove={removePageHistory}
                onCommitHistory={rememberPageSearch}
                onSearch={commitPageSearch}
                onNext={pageFindNext}
                onPrev={pageFindPrev}
                regex={pageRegex}
                matchCase={pageMatchCase}
                wholeWord={pageWholeWord}
                onRegexChange={(on) => {
                  pageRegex = on;
                  if (pageQuery.trim()) commitPageSearch();
                }}
                onMatchCaseChange={(on) => {
                  pageMatchCase = on;
                  if (pageQuery.trim()) commitPageSearch();
                }}
                onWholeWordChange={(on) => {
                  pageWholeWord = on;
                  if (pageQuery.trim()) commitPageSearch();
                }}
                bindInput={(el) => {
                  pageFindInput = el;
                }}
              />
              <span class="find-count">
                {pageMarks.length ? `${pageIndex + 1} / ${pageMarks.length}` : '0 / 0'}
              </span>
              <button class="btn-ghost btn-small" type="button" onclick={pageFindPrev} disabled={!pageMarks.length}>Prev</button>
              <button class="btn-ghost btn-small" type="submit" disabled={!pageQuery.trim()}>Next</button>
            </form>
          </div>
        </div>
        <div class="viewer-stage">
          {#if selected && (!isPdfHit(selected) || heldHtml)}
            {#key `${(heldHtml ?? selected).root_id}:${(heldHtml ?? selected).rel}`}
              <iframe
                class="doc-frame"
                class:viewer-under={Boolean(heldHtml)}
                bind:this={iframeEl}
                title={(heldHtml ?? selected).name}
                onload={onIframeLoad}
              ></iframe>
            {/key}
          {/if}
          {#if isPdfHit(selected)}
            <PdfViewer
              src={viewUrl(selected.root_id, selected.rel)}
              overlay={Boolean(heldHtml)}
              onReady={onPdfReady}
              onSettled={onPdfSettled}
              onPageCount={onPdfPageCount}
            />
          {/if}
        </div>
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

{#if htmlCopyMenu}
  <CopyPopup
    x={htmlCopyMenu.x}
    y={htmlCopyMenu.y}
    onCopy={copyHtmlSelection}
    onClose={() => {
      htmlCopyMenu = null;
    }}
  />
{/if}

{#if pathMenu}
  <PathContextMenu
    x={pathMenu.x}
    y={pathMenu.y}
    full={pathMenu.full}
    rel={pathMenu.rel}
    file={pathMenu.file}
    onLaunch={() => void launchMenuFile()}
    onClose={() => {
      pathMenu = null;
    }}
  />
{/if}
