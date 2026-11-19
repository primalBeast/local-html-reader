<script lang="ts">
  import { onMount } from 'svelte';
  import Tree from './lib/Tree.svelte';
  import SearchField from './lib/SearchField.svelte';
  import PathContextMenu from './lib/PathContextMenu.svelte';
  import ProjectContextMenu from './lib/ProjectContextMenu.svelte';
  import { api, historyFromUnknown, searchFlagsFromUnknown, setApiProject, viewUrl, windowsFullPath, windowsRelPath, type DocumentHit, type Project, type Root, type SearchHistoryItem, type SearchWorker, type Settings, type TreeNode } from './lib/api';
  import PdfViewer, { type PdfFindApi, type PdfFindLayer, type PdfZoomAnchor } from './lib/PdfViewer.svelte';
  import CopyPopup from './lib/CopyPopup.svelte';
  import { applyFinds, reveal } from './lib/pageFind';
  import HelpDialog from './lib/HelpDialog.svelte';
  import { copyImageToClipboard, copyToClipboard, selectedTextIn, wordAtPoint } from './lib/wordAtPoint';
  import { hashForSameFile, revealHash } from './lib/inPageLink';
  import { attachSideIndex, type ContentsZoomAnchor, type SideIndexController } from './lib/sideIndex';
  import { focusFirstMenuItem, onMenuKeydown } from './lib/menuKeys';
  import {
    applyWheelZoom,
    axisCanScroll,
    correctScrollByVisual,
    pageFraction,
    pageFractionVisualDelta,
    paneCentre,
    sameZoomSession,
    zoomAfterOpen,
    zoomAnchorSettled,
    zoomFromDrag,
    zoomFromKey,
    zoomKeyCommand,
    zoomReadout,
    clampDocZoom,
    ZOOM_ANCHOR_ITERS,
    type ZoomSessionPositions,
    type ZoomSessionSnapshot,
  } from './lib/docZoom';

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
  let appliedFlags = $state('');
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
  /** Scale of the open document only. Not saved. 1 is 100%. */
  let docZoom = $state(1);
  /** Fraction of a percent dropped by the integer snap, so trackpad ticks add up. */
  let wheelRemainder = 0;

  const zoomScrub = {
    pointerId: -1,
    startY: 0,
    startZoom: 1,
    dragging: false,
  };

  function setDocZoom(value: number) {
    docZoom = clampDocZoom(value);
    if (selected && isPdfHit(selected)) return;
    applyHtmlZoom();
  }

  /**
   * One zoom gesture. Anchors stay until the document changes or something
   * scrolls by more than a pixel, so a clamped step and tiny drag steps
   * still land back on the same content point.
   */
  type ZoomSession = {
    snapshot: ZoomSessionSnapshot;
    html: HtmlZoomAnchor | null;
    contents: ContentsZoomAnchor | null;
    pdf: PdfZoomAnchor | null;
  };

  let zoomSession: ZoomSession | null = null;

  type HtmlAnchorBox = { left: number; top: number; width: number; height: number };

  /** One character when `character` is set, otherwise the element box. Fractions are of that box. */
  type HtmlZoomAnchor = {
    node: Node;
    offset: number;
    character: boolean;
    fx: number;
    fy: number;
    targetX: number;
    targetY: number;
  };

  /**
   * Zoom the HTML document about the centre of the iframe's visible area.
   * The anchor is a fraction of a one-character box (or the element box).
   * getBoundingClientRect is visual pixels. scrollTop is not assumed: a probe
   * measures visual pixels per scroll unit. The contents hold runs in the
   * same turn and redraws the blue line once, after both corrections.
   */
  function applyHtmlZoom() {
    const doc = iframeDoc();
    const root = doc?.documentElement;
    if (!doc || !root || !selected || isPdfHit(selected)) return;
    const now = htmlZoomSnapshot();
    const reuse = sameZoomSession(zoomSession?.snapshot, now) ? zoomSession : null;
    const contentsReuse = reuse?.contents?.link.isConnected ? reuse.contents : null;
    const heldHtmlAnchor = reuse?.html ?? null;
    const hold = sideIndexCtl?.beginZoom(contentsReuse) ?? null;
    let anchor: HtmlZoomAnchor | null = null;
    try {
      anchor = htmlAnchorLive(doc, heldHtmlAnchor)
        ? heldHtmlAnchor
        : captureHtmlAnchor(doc, sideIndexCtl?.contentsElement() ?? null);
      root.style.setProperty('zoom', String(docZoom));
      if (anchor) settleHtmlAnchor(doc, anchor);
    } finally {
      const ended = sideIndexCtl?.endZoom(hold) ?? { anchor: null, scrollTop: null };
      commitHtmlZoomSession(anchor, ended.anchor);
    }
  }

  /** Visible centre, excluding scrollbars. clientWidth/clientHeight are visual pixels. */
  function iframePaneCentre(doc: Document): { x: number; y: number } | null {
    const view = doc.defaultView;
    if (!view) return null;
    const root = doc.documentElement;
    const width = root.clientWidth > 0 ? root.clientWidth : view.innerWidth;
    const height = root.clientHeight > 0 ? root.clientHeight : view.innerHeight;
    if (width <= 0 || height <= 0) return null;
    return paneCentre(width, height);
  }

  function inIframeView(view: Window, x: number, y: number): boolean {
    return Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0 && x < view.innerWidth && y < view.innerHeight;
  }

  function elementOfNode(node: Node | null): Element | null {
    if (!node) return null;
    return node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
  }

  function blockedZoomAnchor(el: Element | null, doc: Document, index: HTMLElement | null): boolean {
    if (!el) return true;
    if (index?.contains(el)) return true;
    if (el.closest('[data-lhr-index-ui]')) return true;
    const view = doc.defaultView;
    if (!view) return true;
    let node: Element | null = el;
    while (node && node !== doc.documentElement) {
      const pos = view.getComputedStyle(node).position;
      if (pos === 'fixed' || pos === 'sticky') return true;
      node = node.parentElement;
    }
    return false;
  }

  function caretRangeAt(doc: Document, x: number, y: number): Range | null {
    try {
      const range = doc.caretRangeFromPoint(x, y);
      if (range) return range;
    } catch {
      /* fall through to caretPositionFromPoint */
    }
    try {
      const pos = doc.caretPositionFromPoint(x, y);
      if (!pos) return null;
      const range = doc.createRange();
      range.setStart(pos.offsetNode, pos.offset);
      range.collapse(true);
      return range;
    } catch {
      return null;
    }
  }

  function usableBox(rect: { left: number; top: number; width: number; height: number } | null): HtmlAnchorBox | null {
    if (!rect) return null;
    if (!Number.isFinite(rect.left) || !Number.isFinite(rect.top)) return null;
    if (!(rect.width > 0) && !(rect.height > 0)) return null;
    return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  }

  /** One character at `offset`. A zero width cannot correct horizontal scroll. */
  function characterBox(doc: Document, node: Node, offset: number): HtmlAnchorBox | null {
    if (node.nodeType !== Node.TEXT_NODE || !node.isConnected) return null;
    const text = node.textContent ?? '';
    const at = Math.max(0, Math.min(offset, text.length));
    const range = doc.createRange();
    try {
      if (at < text.length) {
        range.setStart(node, at);
        range.setEnd(node, at + 1);
      } else if (at > 0) {
        range.setStart(node, at - 1);
        range.setEnd(node, at);
      } else {
        return null;
      }
    } catch {
      return null;
    }
    const box = usableBox(range.getBoundingClientRect());
    if (!box || !(box.width > 0)) return null;
    return box;
  }

  function readHtmlAnchorBox(doc: Document, anchor: HtmlZoomAnchor): HtmlAnchorBox | null {
    if (!anchor.node.isConnected || anchor.node.ownerDocument !== doc) return null;
    if (anchor.character) return characterBox(doc, anchor.node, anchor.offset);
    return usableBox(elementOfNode(anchor.node)?.getBoundingClientRect() ?? null);
  }

  function htmlAnchorLive(doc: Document, anchor: HtmlZoomAnchor | null | undefined): anchor is HtmlZoomAnchor {
    return Boolean(anchor && anchor.node.isConnected && anchor.node.ownerDocument === doc);
  }

  /**
   * Node under a hit-test point. Fractions are taken later against the pane
   * centre, which may sit outside this box when the centre is over the contents.
   */
  function pickHtmlNode(
    doc: Document,
    x: number,
    y: number,
    index: HTMLElement | null,
  ): { node: Node; offset: number; character: boolean } | null {
    const view = doc.defaultView;
    if (!view || !inIframeView(view, x, y)) return null;
    const range = caretRangeAt(doc, x, y);
    if (range && range.startContainer.nodeType === Node.TEXT_NODE) {
      const el = elementOfNode(range.startContainer);
      if (!blockedZoomAnchor(el, doc, index) && characterBox(doc, range.startContainer, range.startOffset)) {
        return { node: range.startContainer, offset: range.startOffset, character: true };
      }
    }
    const hit = doc.elementFromPoint(x, y);
    if (hit && hit !== doc.documentElement && hit !== doc.body && !blockedZoomAnchor(hit, doc, index)) {
      if (usableBox(hit.getBoundingClientRect())) return { node: hit, offset: 0, character: false };
    }
    return null;
  }

  function anchorFromPick(
    doc: Document,
    picked: { node: Node; offset: number; character: boolean },
    centre: { x: number; y: number },
  ): HtmlZoomAnchor | null {
    const draft: HtmlZoomAnchor = { ...picked, fx: 0, fy: 0, targetX: centre.x, targetY: centre.y };
    const box = readHtmlAnchorBox(doc, draft);
    if (!box) return null;
    // Fraction of the box, not the corner. A full-width block's left edge
    // stays at -scrollLeft, so a corner error never corrects X.
    return {
      ...draft,
      fx: pageFraction(centre.x, box.left, box.width),
      fy: pageFraction(centre.y, box.top, box.height),
    };
  }

  function captureHtmlAnchor(doc: Document, index: HTMLElement | null): HtmlZoomAnchor | null {
    const view = doc.defaultView;
    const centre = iframePaneCentre(doc);
    if (!view || !centre) return null;
    let picked = pickHtmlNode(doc, centre.x, centre.y, index);
    if (!picked && index) {
      const pane = index.getBoundingClientRect();
      picked = pickHtmlNode(doc, pane.right + 12, centre.y, index);
    }
    if (!picked && doc.body && !blockedZoomAnchor(doc.body, doc, index)) {
      picked = { node: doc.body, offset: 0, character: false };
    }
    if (!picked) return null;
    return anchorFromPick(doc, picked, centre);
  }

  function settleHtmlAnchor(doc: Document, anchor: HtmlZoomAnchor) {
    const scrolling = (doc.scrollingElement ?? doc.documentElement) as HTMLElement;
    for (let i = 0; i < ZOOM_ANCHOR_ITERS; i++) {
      const box = readHtmlAnchorBox(doc, anchor);
      if (!box) return;
      const errorX = pageFractionVisualDelta(anchor.fx, box.left, box.width, anchor.targetX);
      const errorY = pageFractionVisualDelta(anchor.fy, box.top, box.height, anchor.targetY);
      const needX = axisCanScroll(scrolling.scrollLeft, scrolling.scrollWidth, scrolling.clientWidth) && !zoomAnchorSettled(errorX);
      const needY = axisCanScroll(scrolling.scrollTop, scrolling.scrollHeight, scrolling.clientHeight) && !zoomAnchorSettled(errorY);
      if (!needX && !needY) return;
      let moved = false;
      if (needY) {
        moved =
          correctScrollByVisual(
            errorY,
            () => scrolling.scrollTop,
            (value) => {
              scrolling.scrollTop = value;
            },
            () => {
              const next = readHtmlAnchorBox(doc, anchor);
              return next ? next.top + anchor.fy * next.height : null;
            },
          ) || moved;
      }
      if (needX) {
        const again = readHtmlAnchorBox(doc, anchor);
        const errorXNow = again ? pageFractionVisualDelta(anchor.fx, again.left, again.width, anchor.targetX) : 0;
        if (
          again &&
          axisCanScroll(scrolling.scrollLeft, scrolling.scrollWidth, scrolling.clientWidth) &&
          !zoomAnchorSettled(errorXNow)
        ) {
          moved =
            correctScrollByVisual(
              errorXNow,
              () => scrolling.scrollLeft,
              (value) => {
                scrolling.scrollLeft = value;
              },
              () => {
                const next = readHtmlAnchorBox(doc, anchor);
                return next ? next.left + anchor.fx * next.width : null;
              },
            ) || moved;
        }
      }
      if (!moved) return;
    }
  }

  function documentZoomId(): string {
    return selected ? docKey(selected) : '';
  }

  function readZoomScroll(pdf: { top: number; left: number } | null): ZoomSessionPositions {
    if (selected && isPdfHit(selected)) {
      return {
        documentTop: null,
        documentLeft: null,
        contentsTop: null,
        pdfTop: pdf ? pdf.top : null,
        pdfLeft: pdf ? pdf.left : null,
      };
    }
    const doc = iframeDoc();
    const scrolling = (doc?.scrollingElement ?? doc?.documentElement) as HTMLElement | null;
    if (!doc || !scrolling) {
      return { documentTop: null, documentLeft: null, contentsTop: null, pdfTop: null, pdfLeft: null };
    }
    return {
      documentTop: scrolling.scrollTop,
      documentLeft: scrolling.scrollLeft,
      contentsTop: sideIndexCtl?.contentsScrollTop() ?? null,
      pdfTop: null,
      pdfLeft: null,
    };
  }

  function htmlZoomSnapshot(): ZoomSessionSnapshot {
    return { id: documentZoomId(), scroll: readZoomScroll(null) };
  }

  function commitHtmlZoomSession(html: HtmlZoomAnchor | null, contents: ContentsZoomAnchor | null) {
    const id = documentZoomId();
    if (!id || !selected || isPdfHit(selected)) return;
    zoomSession = { snapshot: { id, scroll: readZoomScroll(null) }, html, contents, pdf: null };
  }

  function reusePdfZoom(top: number, left: number): PdfZoomAnchor | null {
    const id = documentZoomId();
    const pdf = zoomSession?.pdf;
    if (!id || !pdf) return null;
    const now: ZoomSessionSnapshot = { id, scroll: readZoomScroll({ top, left }) };
    if (!sameZoomSession(zoomSession?.snapshot, now)) return null;
    return pdf;
  }

  function commitPdfZoom(anchor: PdfZoomAnchor | null, top: number, left: number) {
    const id = documentZoomId();
    if (!anchor || !id) {
      zoomSession = null;
      return;
    }
    zoomSession = {
      snapshot: { id, scroll: readZoomScroll({ top, left }) },
      html: null,
      contents: null,
      pdf: anchor,
    };
  }

  /** List, tree, or search — including the document that is already open. */
  function onUserOpenDocument() {
    wheelRemainder = 0;
    zoomSession = null;
    setDocZoom(zoomAfterOpen('user', docZoom));
  }

  /** Same document loaded again (iframe refresh). Does not reset zoom. Drops the zoom anchors. */
  function onDocumentContentReload() {
    zoomSession = null;
    setDocZoom(zoomAfterOpen('reload', docZoom));
  }

  function onDocumentWheel(event: WheelEvent) {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const step = applyWheelZoom(docZoom, event.deltaY, event.deltaMode, wheelRemainder);
    wheelRemainder = step.remainder;
    if (step.zoom === docZoom) return;
    setDocZoom(step.zoom);
  }

  /** Ctrl/Meta+wheel outside the document must not zoom the shell or the browser. */
  function onBlockedZoomWheel(event: WheelEvent) {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
  }

  function onZoomKey(event: KeyboardEvent): boolean {
    const command = zoomKeyCommand(event);
    if (!command) return false;
    event.preventDefault();
    wheelRemainder = 0;
    setDocZoom(zoomFromKey(docZoom, command));
    return true;
  }

  function onPdfScale(scale: number) {
    const next = clampDocZoom(scale);
    if (next === docZoom) return;
    docZoom = next;
  }

  function endZoomScrub() {
    zoomScrub.pointerId = -1;
    zoomScrub.dragging = false;
    document.body.classList.remove('lhr-zoom-scrubbing');
  }

  function onZoomReadoutPointerDown(e: PointerEvent) {
    if (e.button !== 0) return;
    const el = e.currentTarget;
    if (!(el instanceof HTMLElement)) return;
    e.preventDefault();
    e.stopPropagation();
    zoomScrub.pointerId = e.pointerId;
    zoomScrub.startY = e.clientY;
    zoomScrub.startZoom = docZoom;
    zoomScrub.dragging = false;
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* the pointer can already be gone */
    }
  }

  function onZoomReadoutPointerMove(e: PointerEvent) {
    if (e.pointerId !== zoomScrub.pointerId) return;
    const next = zoomFromDrag(zoomScrub.startZoom, e.clientY - zoomScrub.startY);
    if (next === null) return;
    if (!zoomScrub.dragging) {
      zoomScrub.dragging = true;
      document.body.classList.add('lhr-zoom-scrubbing');
    }
    e.preventDefault();
    wheelRemainder = 0;
    setDocZoom(next);
  }

  function onZoomReadoutPointerEnd(e: PointerEvent) {
    if (zoomScrub.pointerId === -1 || e.pointerId !== zoomScrub.pointerId) return;
    endZoomScrub();
  }

  function onZoomReadoutDblClick(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    wheelRemainder = 0;
    setDocZoom(zoomFromKey(docZoom, 'reset'));
  }

  let inWebview = $state(false);

  let menuOpen = $state(false);
  let projectMenuEl = $state<HTMLDivElement | null>(null);
  let helpOpen = $state(false);
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
  let indexLineEl = $state<HTMLDivElement | null>(null);
  let syncIndex = $state<(() => void) | null>(null);
  let sideIndexCtl: SideIndexController | null = null;
  let showSyncContents = $state(false);
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
  let pdfListCurrent = $state(0);
  let pdfListTotal = $state(0);
  let pdfPageCurrent = $state(0);
  let pdfPageTotal = $state(0);
  let pdfApi: PdfFindApi | null = null;
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

  function libraryStats(nodes: TreeNode[]): { files: number; bytes: number } {
    let files = 0;
    let bytes = 0;
    const walk = (list: TreeNode[]) => {
      for (const node of list) {
        if (node.kind === 'file') {
          files += 1;
          bytes += node.size || 0;
        } else if (node.children) {
          walk(node.children);
        }
      }
    };
    walk(nodes);
    return { files, bytes };
  }

  function withMatchCount(nodes: TreeNode[], rootId: string, rel: string, count: number): TreeNode[] {
    return nodes.map((node) => {
      if (node.kind === 'file' && node.root_id === rootId && node.rel === rel) {
        return { ...node, match_count: count };
      }
      if (node.children) return { ...node, children: withMatchCount(node.children, rootId, rel, count) };
      return node;
    });
  }

  function matchCountOf(nodes: TreeNode[], rootId: string, rel: string): number | null {
    for (const node of nodes) {
      if (node.kind === 'file' && node.root_id === rootId && node.rel === rel) {
        return node.match_count || 0;
      }
      if (node.children) {
        const found = matchCountOf(node.children, rootId, rel);
        if (found !== null) return found;
      }
    }
    return null;
  }

  function syncOpenFileMatchCount() {
    if (!selected || !appliedQuery) return;
    const leftFlags = searchFlagKey(treeRegex, treeMatchCase, treeWholeWord);
    let count: number | null = null;
    if (isPdfHit(selected)) {
      if (countedListQuery === appliedQuery && countedListFlags === leftFlags) count = pdfListTotal;
      if (countedPageQuery === appliedQuery && countedPageFlags === leftFlags) count = pdfPageTotal;
    } else {
      if (countedListQuery === appliedQuery && countedListFlags === leftFlags) count = listMarks.length;
      if (countedPageQuery === appliedQuery && countedPageFlags === leftFlags) count = pageMarks.length;
    }
    if (count === null) return;
    const current = matchCountOf(tree, selected.root_id, selected.rel);
    if (current === null || current === count) return;
    tree = withMatchCount(tree, selected.root_id, selected.rel, count);
  }

  function formatPages(count: number, estimated: boolean): string {
    const n = Math.max(1, Math.round(count));
    const word = n === 1 ? 'page' : 'pages';
    return estimated ? `about ${n} ${word}` : `${n} ${word}`;
  }

  const pageNum = new Intl.NumberFormat('en-CA');

  function formatPageLoad(loaded: number, total: number): string {
    const all = pageNum.format(Math.max(0, total));
    if (loaded >= total) return all;
    return `${pageNum.format(Math.max(0, loaded))} / ${all}`;
  }

  function estimatePrintedPages(doc: Document): number {
    const text = (doc.body?.innerText || '').replace(/\s+/g, ' ').trim();
    if (!text) return 1;
    // A single-spaced US Letter page holds about 3,000 characters.
    return Math.max(1, Math.ceil(text.length / 3000));
  }

  async function refreshTree() {
    const q = query.trim();
    const flags = searchFlagKey(treeRegex, treeMatchCase, treeWholeWord);
    const gen = ++searchGen;
    treeAbort?.abort();
    treeAbort = new AbortController();
    const signal = treeAbort.signal;
    searching = Boolean(q);
    if (q) {
      appliedQuery = q;
      appliedFlags = flags;
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
        appliedQuery = '';
        appliedFlags = '';
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
          if (nextTree) {
            tree = nextTree;
            syncOpenFileMatchCount();
          }
          if (workers) {
            searchWorkers = [...workers].sort((a, b) => b.size - a.size || a.slot - b.slot);
          }
        },
        signal,
        { regex: treeRegex, matchCase: treeMatchCase, wholeWord: treeWholeWord },
      );
      if (gen !== searchGen) return;
      tree = data.tree;
      syncOpenFileMatchCount();
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

  async function deleteNamedProject(slug: string) {
    projectMenu = null;
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
    const same =
      Boolean(selected) && docKey(selected) === key && (loadedKey === key || openingKey === key);
    // Clicking the open file again still counts as a user open: zoom returns to 100%.
    // A refresh of that file (onIframeLoad) uses zoomAfterOpen('reload') and keeps it.
    if (same) {
      onUserOpenDocument();
      return;
    }
    openingKey = key;
    pageSummary = '';
    syncIndex = null;
    showSyncContents = false;
    const fromHtml = selected && !isPdfHit(selected);
    if (isPdfHit(doc) && fromHtml) heldHtml = selected;
    else if (!isPdfHit(doc)) heldHtml = null;
    selected = doc;
    pdfRootEl = null;
    pdfListCurrent = 0;
    pdfListTotal = 0;
    pdfPageCurrent = 0;
    pdfPageTotal = 0;
    pageQuery = '';
    pageMarks = [];
    pageIndex = 0;
    listIndex = 0;
    onUserOpenDocument();
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

  function searchFlagKey(regex: boolean, matchCase: boolean, wholeWord: boolean): string {
    return `${regex ? 1 : 0}${matchCase ? 1 : 0}${wholeWord ? 1 : 0}`;
  }

  function commitTreeSearch(value?: string) {
    if (typeof value === 'string') query = value;
    const next = query.trim();
    const flags = searchFlagKey(treeRegex, treeMatchCase, treeWholeWord);
    if (next === appliedQuery && flags === appliedFlags) {
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
    el.dataset.pageUrl = new URL(url, window.location.href).href;
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
  let countedListQuery = '';
  let countedPageQuery = '';
  let countedListFlags = '';
  let countedPageFlags = '';

  function forgetFindCounts() {
    countedListQuery = '';
    countedPageQuery = '';
    countedListFlags = '';
    countedPageFlags = '';
  }

  function noteFindCounts() {
    countedListQuery = listQuery.trim();
    countedPageQuery = pageQuery.trim();
    countedListFlags = searchFlagKey(treeRegex, treeMatchCase, treeWholeWord);
    countedPageFlags = searchFlagKey(pageRegex, pageMatchCase, pageWholeWord);
  }

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
    noteFindCounts();
    syncOpenFileMatchCount();
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
    forgetFindCounts();
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
    if (isPdfHit(selected) && pdfApi) {
      const runPdf = () => {
        if (gen !== docFindGen || !pdfApi) return;
        if (which === 'list' || which === 'both') {
          if (listQuery.trim()) {
            pdfApi.search('list', listQuery, { regex: treeRegex, matchCase: treeMatchCase, wholeWord: treeWholeWord });
          } else {
            pdfApi.clear('list');
            listFinding = false;
          }
        }
        if (which === 'page' || which === 'both') {
          if (pageQuery.trim()) {
            pdfApi.search('page', pageQuery, { regex: pageRegex, matchCase: pageMatchCase, wholeWord: pageWholeWord });
          } else {
            pdfApi.clear('page');
            pageFinding = false;
          }
        }
      };
      if (!listQuery.trim() && !pageQuery.trim()) {
        runPdf();
        return;
      }
      docFindTimer = setTimeout(runPdf, 40);
      return;
    }
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
    if (isPdfHit(selected)) {
      if (!pdfListTotal) scheduleDocFind(true, 'list');
      else pdfApi?.again('list', false);
      return;
    }
    if (listMarks.length === 0) {
      scheduleDocFind(true, 'list');
      return;
    }
    listIndex = reveal(listMarks, listIndex + 1, 'list');
  }

  function listFindPrev() {
    if (isPdfHit(selected)) {
      if (!pdfListTotal) scheduleDocFind(true, 'list');
      else pdfApi?.again('list', true);
      return;
    }
    if (listMarks.length === 0) {
      scheduleDocFind(true, 'list');
      return;
    }
    listIndex = reveal(listMarks, listIndex - 1, 'list');
  }

  function pageFindNext() {
    if (isPdfHit(selected)) {
      if (!pdfPageTotal) scheduleDocFind(false, 'page');
      else pdfApi?.again('page', false);
      return;
    }
    if (pageMarks.length === 0) {
      scheduleDocFind(false, 'page');
      return;
    }
    pageIndex = reveal(pageMarks, pageIndex + 1, 'page');
  }

  function pageFindPrev() {
    if (isPdfHit(selected)) {
      if (!pdfPageTotal) scheduleDocFind(false, 'page');
      else pdfApi?.again('page', true);
      return;
    }
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
    // New document content, not a user open. A click in the list already reset zoom.
    if (!isPdfHit(selected)) onDocumentContentReload();
    scheduleDocFind(Boolean(listQuery.trim()), 'both');
    const doc = iframeDoc();
    const frame = iframeEl;
    if (!doc || !frame) return;
    const onFrameWheel = (event: WheelEvent) => {
      onDocumentWheel(event);
    };
    const onFrameKey = (event: KeyboardEvent) => {
      onZoomKey(event);
    };
    doc.addEventListener('wheel', onFrameWheel, { capture: true, passive: false });
    doc.addEventListener('keydown', onFrameKey, true);
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
    const onLink = (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (event.defaultPrevented) return;
      const view = doc.defaultView;
      if (!view) return;
      const node = event.target;
      const el =
        node instanceof view.Element ? node : node instanceof view.Node ? node.parentElement : null;
      const anchor = el?.closest('a[href], area[href]');
      if (!anchor) return;
      const where = (anchor.getAttribute('target') || '').toLowerCase();
      if (where === '_blank' || where === '_parent' || where === '_top') return;
      const pageUrl = frame.dataset.pageUrl || '';
      const rawHref = anchor.getAttribute('href') || '';
      const hrefValue = (anchor as HTMLAnchorElement).href;
      const resolved = typeof hrefValue === 'string' && hrefValue ? hrefValue : rawHref;
      const hash = hashForSameFile(rawHref, resolved, pageUrl);
      if (!hash) return;
      event.preventDefault();
      revealHash(doc, hash);
    };
    doc.addEventListener('click', onLink, true);
    const indexCtl = attachSideIndex(
      doc,
      frame.dataset.pageUrl || '',
      (sync) => {
        syncIndex = sync;
        if (sync) showSyncContents = true;
      },
      (box) => {
        const el = indexLineEl;
        if (!el) return;
        if (!box || (selected && isPdfHit(selected))) {
          el.style.display = 'none';
          return;
        }
        el.style.display = 'block';
        el.style.top = `${box.top}px`;
        el.style.left = `${box.left}px`;
        el.style.width = `${box.width}px`;
      },
    );
    sideIndexCtl = indexCtl;
    iframeCopyCleanup = () => {
      doc.removeEventListener('wheel', onFrameWheel, { capture: true });
      doc.removeEventListener('keydown', onFrameKey, true);
      doc.removeEventListener('contextmenu', handler);
      doc.removeEventListener('click', onLink, true);
      indexCtl.destroy();
      if (sideIndexCtl === indexCtl) sideIndexCtl = null;
      syncIndex = null;
      if (indexLineEl) indexLineEl.style.display = 'none';
    };
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

  function onPdfApi(api: PdfFindApi) {
    pdfApi = api;
  }

  function onPdfFindUpdate(info: { layer: PdfFindLayer; current: number; total: number; pending: boolean }) {
    if (info.layer === 'list') {
      pdfListCurrent = info.current;
      pdfListTotal = info.total;
      listMatchCount = info.total;
      listFinding = info.pending;
    } else {
      pdfPageCurrent = info.current;
      pdfPageTotal = info.total;
      pageMatchCount = info.total;
      pageFinding = info.pending;
    }
    if (!info.pending) {
      noteFindCounts();
      syncOpenFileMatchCount();
    }
  }

  function findPos(layer: 'list' | 'page'): string {
    if (isPdfHit(selected)) {
      const total = layer === 'list' ? pdfListTotal : pdfPageTotal;
      const pos = layer === 'list' ? pdfListCurrent : pdfPageCurrent;
      return total ? `${pos} / ${total}` : '0 / 0';
    }
    const marks = layer === 'list' ? listMarks : pageMarks;
    const index = layer === 'list' ? listIndex : pageIndex;
    return marks.length ? `${index + 1} / ${marks.length}` : '0 / 0';
  }

  function findHasHits(layer: 'list' | 'page'): boolean {
    if (isPdfHit(selected)) return (layer === 'list' ? pdfListTotal : pdfPageTotal) > 0;
    return (layer === 'list' ? listMarks : pageMarks).length > 0;
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

  function onPdfPageProgress(loaded: number, total: number, src: string) {
    if (!selected || !isPdfHit(selected)) return;
    if (viewUrl(selected.root_id, selected.rel) !== src) return;
    pageSummary = formatPageLoad(loaded, total);
  }

  function onPdfSettled(src: string) {
    if (!selected || !isPdfHit(selected)) return;
    if (viewUrl(selected.root_id, selected.rel) !== src) return;
    if (loadedKey === docKey(selected)) return;
    if (openingKey === docKey(selected)) openingKey = null;
  }

  function onKeydown(event: KeyboardEvent) {
    if (onZoomKey(event)) return;
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
      if (helpOpen) helpOpen = false;
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

  async function revealMenuPath() {
    const menu = pathMenu;
    pathMenu = null;
    if (!menu?.rootId) return;
    error = null;
    try {
      await api.revealDocument(menu.rootId, menu.relApi);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  $effect(() => {
    if (!menuOpen) return;
    const el = projectMenuEl;
    queueMicrotask(() => focusFirstMenuItem(el, '.current'));
  });

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
    window.addEventListener('wheel', onBlockedZoomWheel, { capture: true, passive: false });
    return () => {
      iframeCopyCleanup?.();
      stopWatch();
      clearInterval(healthTick);
      clearInterval(webviewTick);
      endZoomScrub();
      window.removeEventListener('keydown', onKeydown);
      window.removeEventListener('click', onWindowClick);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('wheel', onBlockedZoomWheel, { capture: true });
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
          aria-haspopup="true"
          aria-expanded={menuOpen}
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
          <div
            class="menu-drop project-menu"
            bind:this={projectMenuEl}
            role="presentation"
            onclick={(e) => e.stopPropagation()}
            onkeydown={onMenuKeydown}
          >
            <div class="menu-col projects" role="menu" aria-label="Projects">
              <div class="menu-heading">Projects</div>
              <div class="menu-col-scroll">
                {#each projects as proj (proj.slug)}
                  <button
                    type="button"
                    role="menuitem"
                    data-menu-item
                    class:current={proj.slug === currentSlug}
                    onclick={() => void selectProject(proj.slug)}
                    oncontextmenu={(e) => openProjectContextMenu(e, proj)}
                  >
                    {proj.slug === currentSlug ? '● ' : '○ '}{proj.name}
                  </button>
                {/each}
              </div>
              <div class="menu-col-foot">
                <button
                  type="button"
                  role="menuitem"
                  data-menu-item
                  onclick={() => {
                    menuOpen = false;
                    projectNameDraft = '';
                    projectDialog = 'new';
                  }}
                >+ New project…</button>
              </div>
            </div>
            <div class="menu-col folders">
              <div class="menu-heading">Folders in this project</div>
              <div class="menu-col-scroll">
                {#if !currentSlug}
                  <div class="menu-hint">Create a project, then add documentation folders.</div>
                {:else if (currentProject?.folders.length ?? 0) === 0}
                  <div class="menu-hint">No folders yet. Add one below.</div>
                {:else}
                  {#each currentProject?.folders || [] as folder (folder.id)}
                    <label
                      class="folder-check"
                      oncontextmenu={(e) => openPathMenu(e, folder.path, '', false, folder.id)}
                    >
                      <input
                        type="checkbox"
                        data-menu-item
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
              </div>
              <div class="menu-col-foot">
                <button type="button" data-menu-item onclick={openFolderDialog} disabled={!currentSlug}>
                  + Add folder…
                </button>
              </div>
            </div>
          </div>
        {/if}
      </div>
      <div class="brand">
        <h1>Local HTML Reader</h1>
        <span title={rootLabel}>{rootLabel}</span>
      </div>
    </div>
    <div class="topbar-spacer" title="Drag to move. Double-click to maximize"></div>
    <button
      class="menu-btn"
      type="button"
      title="Supported formats and limits"
      onclick={(e) => {
        e.stopPropagation();
        helpOpen = true;
      }}
    >Help</button>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <span
      class="zoom-readout"
      title="Drag up or down to zoom the document. Double-click to reset to 100%."
      onpointerdown={onZoomReadoutPointerDown}
      onpointermove={onZoomReadoutPointerMove}
      onpointerup={onZoomReadoutPointerEnd}
      onpointercancel={onZoomReadoutPointerEnd}
      onlostpointercapture={onZoomReadoutPointerEnd}
      ondblclick={onZoomReadoutDblClick}
    >{zoomReadout(docZoom)}</span>
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
    style={`grid-template-columns: ${sidebarWidth}px 6px minmax(0, 1fr);`}
  >
    <section class="pane sidebar">
      <div class="pane-head">
        <h2>Documents</h2>
        <SearchField
          value={query}
          placeholder="Search documents"
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
        <div class="muted">
          {#if searching}
            Searching… {fileCount} matching file{fileCount === 1 ? '' : 's'}
          {:else if appliedQuery}
            {fileCount} matching file{fileCount === 1 ? '' : 's'}
            {#if truncated} (truncated){/if}
          {:else if loading}
            Loading…
          {:else}
            {@const stats = libraryStats(tree)}
            {stats.files} file{stats.files === 1 ? '' : 's'} · {formatMb(stats.bytes)}
            {#if truncated} (truncated){/if}
          {/if}
        </div>
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
            Documents stay on disk; this app only reads them.
          </div>
        {:else if tree.length === 0}
          <div class="empty">
            {#if searching}
              Searching…
            {:else if appliedQuery}
              No documents contain that text.
            {:else}
              No supported documents in the enabled folders.
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
            <div class="doc-title-row">
              <code
                class="doc-path"
                title={windowsFullPath(selected.root_path, selected.rel)}
                oncontextmenu={(e) => {
                  if (!selected) return;
                  openPathMenu(e, selected.root_path, selected.rel, true, selected.root_id);
                }}
              >{windowsRelPath(selected.rel)}</code>
            </div>
            {#if pageSummary}
              <div class="doc-pages">{pageSummary}</div>
            {/if}
          </div>
          <div class="page-finds">
            {#if showSyncContents && !isPdfHit(selected)}
              <button
                class="sync-contents"
                type="button"
                title="Scroll the contents to the place shown in the document"
                onclick={() => syncIndex?.()}
              >Sync Contents</button>
            {:else}
              <span class="sync-contents sync-contents-spacer" aria-hidden="true">Sync Contents</span>
            {/if}
            <div class="page-finds-center">
            <form
              class="page-find list-find"
              onsubmit={(e) => {
                e.preventDefault();
                listFindNext();
              }}
            >
              <span class="find-count">
                {findPos('list')}
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
              <button class="btn-ghost btn-small" type="button" onclick={listFindPrev} disabled={!findHasHits('list')}>Prev</button>
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
                {findPos('page')}
              </span>
              <button class="btn-ghost btn-small" type="button" onclick={pageFindPrev} disabled={!findHasHits('page')}>Prev</button>
              <button class="btn-ghost btn-small" type="submit" disabled={!pageQuery.trim()}>Next</button>
            </form>
            </div>
            <span class="sync-contents sync-contents-spacer" aria-hidden="true">Sync Contents</span>
          </div>
        </div>
        <div class="viewer-stage">
          <div class="index-line" bind:this={indexLineEl}></div>
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
              scale={docZoom}
              onScale={onPdfScale}
              onZoomWheel={onDocumentWheel}
              reusePdfZoom={reusePdfZoom}
              commitPdfZoom={commitPdfZoom}
              onReady={onPdfReady}
              onSettled={onPdfSettled}
              onPageProgress={onPdfPageProgress}
              onApi={onPdfApi}
              onPdfFind={onPdfFindUpdate}
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

{#if helpOpen}
  <HelpDialog onClose={() => (helpOpen = false)} />
{/if}

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
      if (slug) void deleteNamedProject(slug);
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
    onReveal={pathMenu.rootId ? () => void revealMenuPath() : undefined}
    onClose={() => {
      pathMenu = null;
    }}
  />
{/if}
