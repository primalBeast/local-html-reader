<script lang="ts">
  import { onMount } from 'svelte';
  import CopyPopup from './CopyPopup.svelte';
  import { copyImageToClipboard, copyToClipboard, selectedTextIn, wordAtPoint } from './wordAtPoint';
  import type { EventBus, PDFFindController, PDFLinkService, PDFViewer } from 'pdfjs-dist/web/pdf_viewer.mjs';
  import type { PDFDocumentProxy } from 'pdfjs-dist';
  import { indexMarkY } from './sideIndex';
  import { buildToc, destTop, topFraction, readingKeyFromPages, type OutlineNode, type TocRow } from './pdfOutline';

  const TEXT_LAYER = 1;
  const ANNOTATIONS = 1;
  const NO_EDITOR = -1;

  export type PdfFindFlags = { regex: boolean; matchCase: boolean; wholeWord: boolean };
  export type PdfFindLayer = 'list' | 'page';
  export type PdfFindApi = {
    search(layer: PdfFindLayer, query: string, flags: PdfFindFlags): void;
    again(layer: PdfFindLayer, previous: boolean): void;
    clear(layer: PdfFindLayer): void;
  };

  let {
    src,
    overlay = false,
    onReady,
    onSettled,
    onPageProgress,
    onApi,
    onPdfFind,
  }: {
    src: string;
    overlay?: boolean;
    onReady?: (root: HTMLElement) => void;
    onSettled?: (src: string) => void;
    onPageProgress?: (loaded: number, total: number, src: string) => void;
    onApi?: (api: PdfFindApi) => void;
    onPdfFind?: (info: { layer: PdfFindLayer; current: number; total: number; pending: boolean }) => void;
  } = $props();

  let frame = $state<HTMLDivElement | null>(null);
  let scroller = $state<HTMLDivElement | null>(null);
  let host = $state<HTMLDivElement | null>(null);
  let tocEl = $state<HTMLElement | null>(null);
  let tocBody = $state<HTMLElement | null>(null);
  let toc = $state<TocRow[]>([]);
  let lineTop = $state(0);
  let showTocLine = $state(false);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let viewerReady = $state(false);
  let findLayer = $state<PdfFindLayer | null>(null);
  let copyMenu = $state<{
    x: number;
    y: number;
    text: string;
    image: HTMLImageElement | null;
    canvas: HTMLCanvasElement | null;
  } | null>(null);

  let loadUrl: (url: string) => Promise<void> = async () => {};
  let gotoDest: ((dest: string | unknown[]) => void) | null = null;
  let tocItems: TocRow[] = [];

  function setToc(items: TocRow[]) {
    tocItems = items;
    toc = items;
    if (!items.length) showTocLine = false;
  }

  function placeTocLine() {
    const pane = tocEl;
    const body = tocBody;
    const box = scroller;
    const root = host;
    if (!pane || !body || !box || !root || tocItems.length === 0) {
      showTocLine = false;
      return;
    }
    const boxRect = box.getBoundingClientRect();
    const pages: { pageNumber: number; top: number; bottom: number }[] = [];
    for (const node of root.querySelectorAll('.page')) {
      if (!(node instanceof HTMLElement)) continue;
      const pageNumber = Number(node.dataset.pageNumber);
      if (!pageNumber) continue;
      const rect = node.getBoundingClientRect();
      const top = rect.top - boxRect.top + box.scrollTop;
      pages.push({ pageNumber, top, bottom: top + Math.max(rect.height, 1) });
    }
    const key = readingKeyFromPages(box.scrollTop + box.clientHeight / 2, pages);
    if (key === null) {
      showTocLine = false;
      return;
    }
    const bodyRect = body.getBoundingClientRect();
    const marks = [];
    for (const item of tocItems) {
      if (item.key === null) continue;
      const row = body.querySelector(`[data-toc-id="${item.id}"]`);
      if (!(row instanceof HTMLElement)) continue;
      const rect = row.getBoundingClientRect();
      marks.push({
        content: item.key,
        index: rect.top - bodyRect.top + rect.height / 2,
      });
    }
    const y = indexMarkY(marks, key);
    if (y === null) {
      showTocLine = false;
      return;
    }
    lineTop = y;
    showTocLine = true;
  }

  function syncToc() {
    placeTocLine();
    if (!tocEl || !showTocLine) return;
    tocEl.scrollTo({ top: Math.max(0, lineTop - tocEl.clientHeight / 2), behavior: 'smooth' });
  }

  function openToc(item: TocRow) {
    if (!item.dest) return;
    gotoDest?.(item.dest);
  }

  onMount(() => {
    let cancelled = false;
    let activeUrl = '';
    let loadGen = 0;
    let userHasZoomed = false;
    let userScale = 1;
    let findReady = false;
    const findQueue: Array<() => void> = [];
    const saved = new Map<PdfFindLayer, { query: string; flags: PdfFindFlags }>();
    let activeLayer: PdfFindLayer | null = null;

    let pdfjsMod: typeof import('pdfjs-dist') | null = null;
    let pdfWorker: { destroy?: () => void } | null = null;
    let pdfDoc: PDFDocumentProxy | null = null;
    let loadingTask: { destroy: () => Promise<void> } | null = null;
    let pdfViewer: PDFViewer | null = null;
    let eventBus: EventBus | null = null;
    let linkService: PDFLinkService | null = null;
    let findController: (PDFFindController & { useRegex: boolean }) | null = null;
    let FindStatePending = -1;

    function report(layer: PdfFindLayer, current: number, total: number, pending: boolean) {
      onPdfFind?.({ layer, current, total, pending });
    }

    function runFind(layer: PdfFindLayer, previous: boolean, fresh: boolean) {
      const spec = saved.get(layer);
      const bus = eventBus;
      const finder = findController;
      if (!spec || !bus || !finder || !frame) return;
      activeLayer = layer;
      findLayer = layer;
      finder.useRegex = spec.flags.regex;
      bus.dispatch('find', {
        source: host,
        type: fresh ? 'find' : 'again',
        query: spec.query,
        caseSensitive: spec.flags.matchCase,
        entireWord: spec.flags.wholeWord && !spec.flags.regex,
        highlightAll: true,
        findPrevious: previous,
        matchDiacritics: !spec.flags.regex,
      });
    }

    function whenReady(fn: () => void) {
      if (findReady) fn();
      else findQueue.push(fn);
    }

    const api: PdfFindApi = {
      search(layer, query, flags) {
        const text = query.trim();
        if (!text) {
          api.clear(layer);
          return;
        }
        saved.set(layer, { query: text, flags });
        whenReady(() => {
          report(layer, 0, 0, true);
          runFind(layer, false, true);
        });
      },
      again(layer, previous) {
        if (!saved.get(layer)) return;
        whenReady(() => runFind(layer, previous, activeLayer !== layer));
      },
      clear(layer) {
        saved.delete(layer);
        whenReady(() => {
          if (activeLayer === layer) {
            activeLayer = null;
            findLayer = null;
            eventBus?.dispatch('findbarclose', { source: host });
          }
          report(layer, 0, 0, false);
        });
      },
    };
    onApi?.(api);

    function onFindEvent(evt: { state?: number; matchesCount?: { current?: number; total?: number } }) {
      const layer = activeLayer;
      if (!layer || !evt.matchesCount) return;
      const current = evt.matchesCount.current || 0;
      const total = evt.matchesCount.total || 0;
      const pending = evt.state === FindStatePending;
      report(layer, current, total, pending);
    }

    async function ensureEngine() {
      if (pdfjsMod && pdfWorker && pdfViewer) return pdfjsMod;
      const pdfjs = await import('pdfjs-dist');
      // The viewer bundle reads this global while it loads. Set it before that import.
      (globalThis as typeof globalThis & { pdfjsLib: typeof pdfjs }).pdfjsLib = pdfjs;
      const viewer = await import('pdfjs-dist/web/pdf_viewer.mjs');
      const WorkerCtor = (await import('pdfjs-dist/build/pdf.worker.min.mjs?worker')).default;
      const port = new WorkerCtor();
      const worker = pdfjs.PDFWorker.create({ port });
      pdfjsMod = pdfjs;
      pdfWorker = worker;
      if (!frame || !host || !scroller) return pdfjs;
      const bus = new viewer.EventBus();
      const links = new viewer.PDFLinkService({ eventBus: bus });
      links.externalLinkEnabled = false;
      const finder = makeFinder(viewer.PDFFindController, links, bus);
      const view = new viewer.PDFViewer({
        container: scroller,
        viewer: host,
        eventBus: bus,
        linkService: links,
        findController: finder,
        textLayerMode: TEXT_LAYER,
        annotationMode: ANNOTATIONS,
        annotationEditorMode: NO_EDITOR,
        removePageBorders: true,
        enableAutoLinking: false,
        supportsPinchToZoom: false,
        imagesRightClickMinSize: -1,
        l10n: quietL10n as never,
      });
      links.setViewer(view);
      bus.on('updatefindcontrolstate', onFindEvent);
      bus.on('updatefindmatchescount', (evt: { matchesCount?: { current?: number; total?: number } }) => {
        onFindEvent(evt);
      });
      bus.on('pagesinit', () => {
        if (!pdfViewer) return;
        if (userHasZoomed) pdfViewer.currentScale = userScale;
        else pdfViewer.currentScaleValue = 'page-fit';
        placeTocLine();
      });
      bus.on('scalechanging', () => placeTocLine());
      FindStatePending = viewer.FindState.PENDING;
      eventBus = bus;
      linkService = links;
      findController = finder;
      pdfViewer = view;
      gotoDest = (dest) => {
        void links.goToDestination(dest);
      };
      return pdfjs;
    }

    function flushFind() {
      findReady = true;
      const queued = findQueue.splice(0);
      for (const fn of queued) fn();
    }

    async function countLoadedPages(pdf: { numPages: number; getPage: (n: number) => Promise<unknown> }, gen: number, url: string) {
      const total = pdf.numPages;
      for (let n = 1; n <= total; n++) {
        if (cancelled || gen !== loadGen || url !== activeUrl) return;
        try {
          await pdf.getPage(n);
        } catch {
          /* keep counting so the label can finish */
        }
        if (cancelled || gen !== loadGen || url !== activeUrl) return;
        onPageProgress?.(n, total, url);
        if (n % 12 === 0) await new Promise((resolve) => setTimeout(resolve, 0));
      }
    }

    async function loadOutline(pdf: PDFDocumentProxy, gen: number, url: string) {
      try {
        const outline = await pdf.getOutline?.();
        if (cancelled || gen !== loadGen || url !== activeUrl) return;
        if (!outline?.length) {
          setToc([]);
          return;
        }
        let labels: string[] | null = null;
        try {
          labels = (await pdf.getPageLabels?.()) ?? null;
        } catch {
          labels = null;
        }
        if (cancelled || gen !== loadGen || url !== activeUrl) return;
        const views = new Map<number, number[]>();
        const rows = await buildToc(
          outline as OutlineNode[],
          async (dest) => {
            if (!dest || cancelled || gen !== loadGen) return null;
            let explicit: unknown[] | null = Array.isArray(dest) ? dest : null;
            if (typeof dest === 'string') {
              try {
                explicit = (await pdf.getDestination?.(dest)) ?? null;
              } catch {
                return null;
              }
            }
            if (!explicit?.length || cancelled || gen !== loadGen) return null;
            const destRef = explicit[0];
            let pageIndex = -1;
            if (destRef && typeof destRef === 'object') {
              try {
                pageIndex = await pdf.getPageIndex(destRef as { num: number; gen: number });
              } catch {
                return null;
              }
            } else if (typeof destRef === 'number' && Number.isInteger(destRef)) {
              pageIndex = destRef;
            } else {
              return null;
            }
            if (pageIndex < 0) return null;
            let fraction = 0;
            const top = destTop(explicit);
            if (top !== null && pdf.getPage) {
              try {
                let viewBox = views.get(pageIndex);
                if (!viewBox) {
                  viewBox = (await pdf.getPage(pageIndex + 1)).view;
                  views.set(pageIndex, viewBox);
                }
                fraction = topFraction(viewBox, top);
              } catch {
                fraction = 0;
              }
            }
            return { page: pageIndex + 1, fraction };
          },
          (page) => labels?.[page - 1] || String(page),
        );
        if (cancelled || gen !== loadGen || url !== activeUrl) return;
        setToc(rows);
        if (!userHasZoomed && pdfViewer) pdfViewer.currentScaleValue = 'page-fit';
        requestAnimationFrame(() => placeTocLine());
      } catch {
        if (!cancelled && gen === loadGen) setToc([]);
      }
    }

    loadUrl = async (url: string) => {
      activeUrl = url;
      const gen = ++loadGen;
      error = null;
      loading = true;
      findReady = false;
      activeLayer = null;
      findLayer = null;
      setToc([]);
      try {
        const pdfjs = await ensureEngine();
        if (cancelled || gen !== loadGen || !pdfViewer || !linkService) return;
        const worker = pdfWorker;
        if (!worker) return;
        const previous = pdfDoc;
        const task = pdfjs.getDocument({
          url,
          worker: worker as never,
          enableXfa: false,
        });
        loadingTask = task;
        const pdf = await task.promise;
        if (cancelled || gen !== loadGen) {
          try {
            await pdf.cleanup?.();
          } catch {
            /* ignore */
          }
          return;
        }
        pdfDoc = pdf;
        onPageProgress?.(0, pdf.numPages, url);
        linkService.setDocument(pdf);
        pdfViewer.setDocument(pdf);
        void loadOutline(pdf, gen, url);
        const ready = pdfViewer.onePageRendered;
        if (ready) {
          void ready.then(() => {
            if (cancelled || gen !== loadGen || url !== activeUrl) return;
            loading = false;
            void countLoadedPages(pdf, gen, url);
            flushFind();
            if (host) onReady?.(host);
            onSettled?.(url);
          });
        } else {
          void countLoadedPages(pdf, gen, url);
        }
        try {
          await previous?.cleanup?.();
        } catch {
          /* ignore */
        }
      } catch (e) {
        if (cancelled || gen !== loadGen) return;
        loading = false;
        findReady = false;
        error = e instanceof Error ? e.message : String(e);
        onSettled?.(url);
      }
    };

    function onWheel(event: WheelEvent) {
      if (tocEl && event.target instanceof Node && tocEl.contains(event.target)) return;
      if ((!event.ctrlKey && !event.metaKey) || !pdfViewer?.pdfDocument) return;
      event.preventDefault();
      let dy = event.deltaY;
      if (event.deltaMode === 1) dy *= 16;
      else if (event.deltaMode === 2) dy *= 400;
      const factor = Math.exp(-dy * 0.0015);
      if (!Number.isFinite(factor) || Math.abs(factor - 1) < 0.001) return;
      userHasZoomed = true;
      pdfViewer.updateScale({
        scaleFactor: factor,
        drawingDelay: 200,
        origin: [event.clientX, event.clientY],
      });
      userScale = pdfViewer.currentScale;
    }

    let resizeTimer = 0;
    const ro = new ResizeObserver(() => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        if (!pdfViewer?.pdfDocument || userHasZoomed) return;
        pdfViewer.currentScaleValue = 'page-fit';
      }, 80);
    });
    if (frame) {
      ro.observe(frame);
      frame.addEventListener('wheel', onWheel, { passive: false });
    }
    const onPdfScroll = () => placeTocLine();
    scroller?.addEventListener('scroll', onPdfScroll, { passive: true });
    viewerReady = true;

    return () => {
      cancelled = true;
      loadGen += 1;
      gotoDest = null;
      window.clearTimeout(resizeTimer);
      ro.disconnect();
      frame?.removeEventListener('wheel', onWheel);
      scroller?.removeEventListener('scroll', onPdfScroll);
      try {
        pdfViewer?.cleanup();
      } catch {
        /* ignore */
      }
      try {
        void loadingTask?.destroy();
      } catch {
        /* ignore */
      }
      try {
        pdfWorker?.destroy?.();
      } catch {
        /* ignore */
      }
    };
  });

  $effect(() => {
    if (!viewerReady) return;
    const url = src;
    void loadUrl(url);
  });

  function onPdfContextMenu(event: MouseEvent) {
    const text = selectedTextIn(host) || wordAtPoint(document, event.clientX, event.clientY);
    const pageEl = event.target instanceof Element ? event.target.closest('.page') : null;
    const imgNode = pageEl?.querySelector('img');
    const canvasNode = pageEl?.querySelector('canvas');
    const img = event.target instanceof HTMLImageElement ? event.target : imgNode instanceof HTMLImageElement ? imgNode : null;
    const canvas =
      event.target instanceof HTMLCanvasElement ? event.target : canvasNode instanceof HTMLCanvasElement ? canvasNode : null;
    if (!text && !img && !canvas) return;
    event.preventDefault();
    event.stopPropagation();
    copyMenu = {
      x: event.clientX,
      y: event.clientY,
      text,
      image: text ? null : img,
      canvas: text || img ? null : canvas,
    };
  }

  async function copyPdfSelection() {
    const menu = copyMenu;
    if (!menu) return;
    try {
      if (menu.text) await copyToClipboard(menu.text);
      else if (menu.image) await copyImageToClipboard(menu.image);
      else if (menu.canvas) {
        const blob = await new Promise<Blob | null>((resolve) => menu.canvas?.toBlob(resolve, 'image/png'));
        if (blob) await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
      }
    } catch {
      if (menu.text) await copyToClipboard(menu.text);
    }
    copyMenu = null;
  }

  const quietL10n = {
    getLanguage: () => 'en-US',
    getDirection: () => 'ltr',
    get: async (key: string) => key,
    translate: async () => {},
    pause: () => {},
    resume: () => {},
    destroy: () => {},
  };

  function makeFinder(
    Base: new (opts: { linkService: PDFLinkService; eventBus: EventBus; delay?: number }) => PDFFindController,
    links: PDFLinkService,
    bus: EventBus,
  ): PDFFindController & { useRegex: boolean } {
    const finder = new Base({ linkService: links, eventBus: bus, delay: 0 }) as PDFFindController & {
      useRegex: boolean;
    };
    const stockMatch = finder.match.bind(finder);
    finder.useRegex = false;
    finder.match = function (query, pageContent, pageIndex) {
      const state = this.state as { query?: string | string[]; caseSensitive?: boolean; entireWord?: boolean } | null;
      if (!this.useRegex || !state || typeof state.query !== 'string') {
        return stockMatch(query, pageContent, pageIndex);
      }
      let re: RegExp;
      try {
        re = new RegExp(state.query, state.caseSensitive ? 'g' : 'gi');
      } catch {
        return [];
      }
      const matches: { index: number; length: number }[] = [];
      re.lastIndex = 0;
      let found: RegExpExecArray | null;
      while ((found = re.exec(pageContent)) !== null) {
        if (!found[0]) {
          re.lastIndex += 1;
          continue;
        }
        if (state.entireWord && !wholeWordAt(pageContent, found.index, found[0].length)) continue;
        matches.push({ index: found.index, length: found[0].length });
      }
      return matches;
    };
    return finder;
  }

  function wholeWordAt(content: string, start: number, length: number): boolean {
    const word = /[\p{L}\p{N}_]/u;
    const before = start > 0 ? content[start - 1] : '';
    const after = content[start + length] || '';
    if (before && word.test(before)) return false;
    if (after && word.test(after)) return false;
    return true;
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="pdf-frame doc-frame"
  class:pdf-frame-overlay={overlay}
  class:pdf-has-toc={toc.length > 0}
  class:find-list={findLayer === 'list'}
  class:find-page={findLayer === 'page'}
  bind:this={frame}
  role="document"
  oncontextmenu={onPdfContextMenu}
>
  {#if toc.length}
    <aside class="pdf-toc" bind:this={tocEl} aria-label="Contents">
      <div class="pdf-toc-body" bind:this={tocBody}>
        <div class="pdf-toc-line" class:on={showTocLine} style:top="{lineTop}px"></div>
        <button
          class="pdf-toc-sync"
          type="button"
          title="Scroll the contents to the place shown in the PDF"
          onclick={syncToc}
        >Index</button>
        {#each toc as item (item.id)}
          <button
            class="pdf-toc-item"
            type="button"
            data-toc-id={item.id}
            style:padding-left="{0.45 + item.depth * 0.75}rem"
            title={item.page ? `${item.title} — page ${item.label}` : item.title}
            disabled={!item.dest}
            onclick={() => openToc(item)}
          >
            <span class="pdf-toc-title">{item.title}</span>
            {#if item.label}<span class="pdf-toc-page">{item.label}</span>{/if}
          </button>
        {/each}
      </div>
    </aside>
  {/if}
  <div class="pdf-scroll" bind:this={scroller}>
    <div class="pdf-pages pdfViewer" bind:this={host}></div>
  </div>
  {#if loading}
    <div class="pdf-loading" role="status" aria-label="Loading PDF">
      <span class="pdf-loading-spinner"></span>
    </div>
  {/if}
  {#if error}
    <div class="pdf-status error">{error}</div>
  {/if}
</div>
{#if copyMenu}
  <CopyPopup
    x={copyMenu.x}
    y={copyMenu.y}
    onCopy={copyPdfSelection}
    onClose={() => (copyMenu = null)}
  />
{/if}
