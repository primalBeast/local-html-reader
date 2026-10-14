<script lang="ts">
  import { onMount } from 'svelte';
  import CopyPopup from './CopyPopup.svelte';
  import { copyImageToClipboard, copyToClipboard, selectedTextIn, wordAtPoint } from './wordAtPoint';

  let {
    src,
    overlay = false,
    onReady,
    onSettled,
    onPageCount,
  }: {
    src: string;
    overlay?: boolean;
    onReady?: (root: HTMLElement) => void;
    onSettled?: (src: string) => void;
    onPageCount?: (pages: number, src: string) => void;
  } = $props();

  let frame = $state<HTMLDivElement | null>(null);
  let slot = $state<HTMLDivElement | null>(null);
  let host = $state<HTMLDivElement | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let viewerReady = $state(false);
  let copyMenu = $state<{
    x: number;
    y: number;
    text: string;
    image: HTMLImageElement | null;
    canvas: HTMLCanvasElement | null;
  } | null>(null);

  let loadUrl: (url: string) => Promise<void> = async () => {};

  onMount(() => {
    let cancelled = false;
    let activeUrl = '';
    const lifetime: Array<{ destroy?: () => void; cancel?: () => void }> = [];
    let pageTasks: Array<{ destroy?: () => void; cancel?: () => void }> = [];
    let pdfjsMod: typeof import('pdfjs-dist') | null = null;
    let pdfWorker: { destroy?: () => void } | null = null;
    let pdfDoc: { numPages: number; getPage: (n: number) => Promise<any>; destroy?: () => void } | null = null;
    let paintGen = 0;
    let loadGen = 0;
    let lastWidth = 0;
    let paintedHeight = 0;
    let paintedScale = 0;
    let desiredScale = 1;
    let pageWidthPt = 1;
    let pageHeightPt = 1;
    let userHasZoomed = false;
    let zoomReady = false;
    let liveFit = 1;
    let resizeTimer = 0;
    let pageEls: HTMLDivElement[] = [];
    let pageTops: number[] = [];
    const renderedFull = new Set<number>();
    const renderedText = new Set<number>();
    const failedFull = new Set<number>();
    const failedText = new Set<number>();
    const blobByPage = new Map<number, string>();
    const wantFull = new Set<number>();
    let textReadyPending = false;
    let textNotifiedGen = -1;
    const pageChain = new Map<number, Promise<unknown>>();
    const bitmapTasks = new Map<number, { cancel?: () => void }>();
    let laidOutUrl = '';
    let notifyFirst: (() => void) | null = null;
    let scrollQueued = false;
    let paintLock: Promise<void> = Promise.resolve();
    let layoutCommitted = false;

    function gutterWidth(): number {
      const el = slot || frame;
      if (!el) return 0;
      return Math.max(160, Math.floor(el.clientWidth));
    }

    function viewportHeight(): number {
      if (!frame) return 0;
      return Math.max(80, Math.floor(frame.clientHeight));
    }

    function fitHeightScale(): number {
      if (pageHeightPt < 1) return 1;
      const hostPad = host
        ? (parseFloat(getComputedStyle(host).paddingTop) || 0) +
          (parseFloat(getComputedStyle(host).paddingBottom) || 0)
        : 48;
      const avail = Math.max(80, viewportHeight() - hostPad - 8);
      const heightScale = avail / pageHeightPt;
      if (!frame || pageWidthPt < 1) return heightScale;
      // Stay a few pixels inside the scrollport so a rounding error cannot
      // turn the horizontal scrollbar on and off.
      const widthScale = Math.max(80, frame.clientWidth - 8) / pageWidthPt;
      return Math.min(heightScale, widthScale);
    }

    function clampScale(value: number): number {
      return Math.min(8, Math.max(0.15, value));
    }

    function cancelPageTasks() {
      for (const task of pageTasks) {
        try {
          task.cancel?.();
          task.destroy?.();
        } catch {
          /* ignore */
        }
      }
      pageTasks = [];
    }

    function track(task: { cancel?: () => void; destroy?: () => void }) {
      pageTasks.push(task);
      return task;
    }

    function untrack(task: { cancel?: () => void; destroy?: () => void }) {
      const index = pageTasks.indexOf(task);
      if (index >= 0) pageTasks.splice(index, 1);
    }

    function revokeBlobs() {
      for (const url of blobByPage.values()) URL.revokeObjectURL(url);
      blobByPage.clear();
    }

    function resetLiveScale() {
      liveFit = 1;
      if (host) {
        host.style.transform = '';
        host.style.width = '';
        host.style.marginLeft = '';
      }
      if (slot) {
        slot.style.height = '';
        slot.style.width = '';
      }
    }

    function scrollKeepCentered(prevVisualW: number, prevVisualH: number, nextVisualW: number, nextVisualH: number) {
      if (!frame) return;
      const viewW = frame.clientWidth;
      const viewH = frame.clientHeight;
      const cx = prevVisualW <= viewW ? 0.5 : (frame.scrollLeft + viewW / 2) / Math.max(1, prevVisualW);
      const cy = prevVisualH < 1 ? 0 : (frame.scrollTop + viewH / 2) / Math.max(1, prevVisualH);
      if (nextVisualW <= viewW) frame.scrollLeft = 0;
      else frame.scrollLeft = cx * nextVisualW - viewW / 2;
      frame.scrollTop = cy * nextVisualH - viewH / 2;
    }

    function applyLiveZoom() {
      if (!host || !slot || !frame || lastWidth < 80 || paintedScale < 0.05 || !host.childElementCount) return;
      const nextFit = desiredScale / paintedScale;
      if (!Number.isFinite(nextFit) || nextFit <= 0) return;
      const prevFit = liveFit;
      const viewW = frame.clientWidth;
      const prevVW = Math.max(lastWidth * prevFit, 1);
      const prevVH = Math.max(paintedHeight * prevFit, 1);
      const nextVW = lastWidth * nextFit;
      const nextVH = paintedHeight * nextFit;
      if (Math.abs(nextFit - 1) < 0.002) {
        resetLiveScale();
        scrollKeepCentered(prevVW, prevVH, lastWidth, paintedHeight);
        return;
      }
      host.style.width = `${lastWidth}px`;
      host.style.marginLeft = '0';
      host.style.transformOrigin = 'top center';
      host.style.transform = `scale(${nextFit})`;
      slot.style.width = nextVW > viewW + 2 ? `${Math.ceil(nextVW)}px` : '';
      slot.style.height = `${nextVH}px`;
      liveFit = nextFit;
      scrollKeepCentered(prevVW, prevVH, Math.max(viewW, nextVW), nextVH);
    }

    function applySlotWidth() {
      const root = host;
      if (!root || !frame || !slot) return;
      if (lastWidth > frame.clientWidth + 2) {
        slot.style.width = `${lastWidth}px`;
        root.style.width = `${lastWidth}px`;
      } else {
        slot.style.width = '';
        root.style.width = '';
      }
    }

    function rebuildTops() {
      pageTops = pageEls.map((el) => el.offsetTop);
    }

    function indexAt(y: number): number {
      let lo = 0;
      let hi = pageTops.length - 1;
      let ans = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (pageTops[mid] <= y) {
          ans = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }
      return ans;
    }

    function visibleRange(): [number, number] {
      const total = pageEls.length;
      if (!total) return [1, 1];
      if (!frame) return [1, Math.min(total, 3)];
      if (pageTops.length !== total) rebuildTops();
      const pageH = pageEls[0]?.offsetHeight || 800;
      const top = frame.scrollTop - pageH;
      const bottom = frame.scrollTop + frame.clientHeight + pageH;
      const first = Math.max(0, indexAt(top));
      const last = Math.min(total - 1, Math.max(first, indexAt(bottom)));
      return [first + 1, last + 1];
    }

    function noteWidth(cssW: number) {
      if (cssW <= lastWidth) return;
      lastWidth = cssW;
      if (layoutCommitted) applySlotWidth();
    }

    function fitShell(el: HTMLDivElement, cssW: number, cssH: number) {
      const prevH = el.offsetHeight;
      el.style.setProperty('--scale-factor', String(paintedScale));
      el.style.width = `${cssW}px`;
      el.style.height = `${cssH}px`;
      pageTops = [];
      noteWidth(cssW);
      const delta = cssH - prevH;
      if (el.isConnected && frame && delta && el.offsetTop + prevH <= frame.scrollTop) {
        frame.scrollTop += delta;
      }
    }

    function enqueuePageJob(n: number, job: (page: any) => Promise<void>): Promise<void> {
      const prev = pageChain.get(n) ?? Promise.resolve();
      const run = prev.then(async () => {
        const pdf = pdfDoc;
        if (!pdf || cancelled) return;
        const page = await pdf.getPage(n);
        try {
          await job(page);
        } finally {
          try {
            page.cleanup?.();
          } catch {
            /* ignore */
          }
        }
      });
      pageChain.set(
        n,
        run.then(
          () => {},
          () => {},
        ),
      );
      return run;
    }

    async function ensureText(n: number, gen: number): Promise<void> {
      if (renderedText.has(n) || failedText.has(n) || gen !== paintGen) return;
      const pdfjs = pdfjsMod;
      const el = pageEls[n - 1];
      if (!pdfjs || !el) return;
      try {
        await enqueuePageJob(n, async (page) => {
          if (gen !== paintGen || renderedText.has(n) || failedText.has(n)) return;
          const viewport = page.getViewport({ scale: paintedScale });
          const cssW = Math.floor(viewport.width);
          const cssH = Math.floor(viewport.height);
          fitShell(el, cssW, cssH);
          let textDiv = el.querySelector(':scope > .textLayer') as HTMLDivElement | null;
          if (textDiv && textDiv.childElementCount) {
            renderedText.add(n);
            return;
          }
          if (!textDiv) {
            textDiv = document.createElement('div');
            textDiv.className = 'textLayer';
            el.append(textDiv);
          }
          const textContent = await page.getTextContent();
          if (gen !== paintGen) return;
          const layer = new pdfjs.TextLayer({
            textContentSource: textContent,
            container: textDiv,
            viewport,
          });
          track(layer);
          try {
            await layer.render();
          } finally {
            untrack(layer);
          }
          if (gen === paintGen) renderedText.add(n);
        });
      } catch {
        if (gen === paintGen) failedText.add(n);
      }
    }

    async function ensureBitmap(n: number, gen: number): Promise<void> {
      if (renderedFull.has(n) || failedFull.has(n) || gen !== paintGen) return;
      const el = pageEls[n - 1];
      if (!el) return;
      try {
        await enqueuePageJob(n, async (page) => {
          if (gen !== paintGen || renderedFull.has(n) || !wantFull.has(n)) return;
          const viewport = page.getViewport({ scale: paintedScale });
          const cssW = Math.floor(viewport.width);
          const cssH = Math.floor(viewport.height);
          fitShell(el, cssW, cssH);
          const canvas = document.createElement('canvas');
          const outputScale = Math.min(window.devicePixelRatio || 1, 2);
          canvas.width = Math.floor(viewport.width * outputScale);
          canvas.height = Math.floor(viewport.height * outputScale);
          canvas.style.width = `${cssW}px`;
          canvas.style.height = `${cssH}px`;
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            failedFull.add(n);
            return;
          }
          const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;
          const renderTask = page.render({ canvas, viewport, transform });
          track(renderTask);
          bitmapTasks.set(n, renderTask);
          try {
            await renderTask.promise;
          } catch {
            if (gen === paintGen && wantFull.has(n)) failedFull.add(n);
            return;
          } finally {
            untrack(renderTask);
            if (bitmapTasks.get(n) === renderTask) bitmapTasks.delete(n);
          }
          if (gen !== paintGen || !wantFull.has(n)) return;
          el.querySelector(':scope > canvas')?.remove();
          el.querySelector(':scope > img')?.remove();
          canvas.setAttribute('aria-label', `Page ${n}`);
          el.insertBefore(canvas, el.firstChild);
          renderedFull.add(n);
          if (host) paintedHeight = host.scrollHeight;
          notifyFirst?.();
        });
      } catch {
        if (gen === paintGen) failedFull.add(n);
      }
    }

    function notifyTextReady() {
      const root = host;
      const first = pageEls[0];
      if (!root || !first?.isConnected) {
        textReadyPending = true;
        return;
      }
      if (textNotifiedGen === paintGen) return;
      textNotifiedGen = paintGen;
      textReadyPending = false;
      onReady?.(root);
    }

    function urgentBitmap(): boolean {
      for (const n of wantFull) {
        if (!renderedFull.has(n) && !failedFull.has(n)) return true;
      }
      return false;
    }

    async function indexAllText(gen: number) {
      const total = pdfDoc?.numPages ?? 0;
      for (let n = 1; n <= total; n++) {
        if (gen !== paintGen || cancelled) return;
        while (gen === paintGen && !cancelled && urgentBitmap()) {
          await new Promise<void>((resolve) => setTimeout(resolve, 16));
        }
        if (gen !== paintGen || cancelled) return;
        await ensureText(n, gen);
      }
      if (gen !== paintGen || cancelled) return;
      notifyTextReady();
    }

    let bitmapPumping = false;
    let bitmapAgain = false;

    function nextBitmap(): number | null {
      const total = pageEls.length;
      if (!total) return null;
      if (!layoutCommitted) {
        for (const n of wantFull) {
          if (!renderedFull.has(n) && !failedFull.has(n)) return n;
        }
        return null;
      }
      const [first, last] = visibleRange();
      const ordered: number[] = [];
      for (let n = first; n <= last; n++) ordered.push(n);
      const ahead = Math.min(total, last + 4);
      for (let n = last + 1; n <= ahead; n++) ordered.push(n);
      for (let n = first - 1; n >= Math.max(1, first - 1); n--) ordered.push(n);
      for (const n of ordered) {
        if (wantFull.has(n) && !renderedFull.has(n) && !failedFull.has(n)) return n;
      }
      for (const n of wantFull) {
        if (!renderedFull.has(n) && !failedFull.has(n)) return n;
      }
      return null;
    }

    function kickBitmap() {
      if (bitmapPumping) {
        bitmapAgain = true;
        return;
      }
      bitmapPumping = true;
      void runBitmap();
    }

    async function runBitmap() {
      const gen = paintGen;
      try {
        while (gen === paintGen && !cancelled) {
          const next = nextBitmap();
          if (!next) break;
          await ensureBitmap(next, gen);
        }
      } finally {
        bitmapPumping = false;
        if (!cancelled && gen === paintGen && (bitmapAgain || nextBitmap())) {
          bitmapAgain = false;
          kickBitmap();
        }
      }
    }

    function dropBitmap(n: number) {
      bitmapTasks.get(n)?.cancel?.();
      const el = pageEls[n - 1];
      el?.querySelector(':scope > canvas')?.remove();
      el?.querySelector(':scope > img')?.remove();
      const url = blobByPage.get(n);
      if (url) URL.revokeObjectURL(url);
      blobByPage.delete(n);
      renderedFull.delete(n);
    }

    function evictBitmaps(first: number, last: number) {
      const keepFrom = first - 2;
      const keepTo = last + 6;
      const center = (first + last) / 2;
      const extras = [...renderedFull].filter((n) => n < keepFrom || n > keepTo);
      extras.sort((p, q) => Math.abs(q - center) - Math.abs(p - center));
      let over = renderedFull.size - 12;
      for (const n of extras) {
        if (over <= 0) break;
        dropBitmap(n);
        over -= 1;
      }
    }

    function syncWindow() {
      if (!layoutCommitted || !pdfDoc || pageEls.length === 0 || Math.abs(liveFit - 1) > 0.002) return;
      const [first, last] = visibleRange();
      const start = Math.max(1, first - 1);
      const end = Math.min(pageEls.length, last + 4);
      const want = new Set<number>();
      for (let n = start; n <= end; n++) want.add(n);
      for (const n of [...wantFull]) {
        if (!want.has(n)) bitmapTasks.get(n)?.cancel?.();
      }
      wantFull.clear();
      for (const n of want) {
        if (!renderedFull.has(n) && !failedFull.has(n)) wantFull.add(n);
      }
      evictBitmaps(first, last);
      for (let n = first; n <= last; n++) void ensureText(n, paintGen);
      kickBitmap();
    }

    function makeShells(scale: number, cssW: number, cssH: number, count: number): HTMLDivElement[] {
      const shells: HTMLDivElement[] = [];
      for (let n = 1; n <= count; n++) {
        const wrap = document.createElement('div');
        wrap.className = 'pdf-page';
        wrap.dataset.pageNumber = `Page ${n}`;
        wrap.style.setProperty('--scale-factor', String(scale));
        wrap.style.width = `${cssW}px`;
        wrap.style.height = `${cssH}px`;
        shells.push(wrap);
      }
      return shells;
    }

    function clearPageState() {
      renderedFull.clear();
      renderedText.clear();
      failedFull.clear();
      failedText.clear();
      wantFull.clear();
      textReadyPending = false;
      textNotifiedGen = -1;
      pageChain.clear();
      bitmapTasks.clear();
      pageTops = [];
    }

    async function paintPages(loadedUrl: string) {
      const pdf = pdfDoc;
      const root = host;
      if (!pdfjsMod || !pdf || !root) return;
      const scale = desiredScale;
      if (scale < 0.05) return;
      if (cancelled || loadedUrl !== activeUrl) return;
      if (Math.abs(scale - paintedScale) < 0.002 && pageEls.length === pdf.numPages && root.childElementCount) {
        resetLiveScale();
        syncWindow();
        return;
      }
      const gen = ++paintGen;
      cancelPageTasks();
      layoutCommitted = false;
      const switchingDoc = laidOutUrl !== loadedUrl;
      const zoomed = Math.abs(liveFit - 1) > 0.002;
      const savedTop = frame?.scrollTop ?? 0;
      const savedHeight = Math.max(1, root.scrollHeight);
      const [keepStart, keepEnd] =
        switchingDoc || pageEls.length !== pdf.numPages ? [1, Math.min(3, pdf.numPages)] : visibleRange();
      clearPageState();
      const previousBlobs = new Map(blobByPage);
      blobByPage.clear();
      if (switchingDoc) loading = true;
      const cssW = Math.max(1, Math.floor(pageWidthPt * scale));
      const cssH = Math.max(1, Math.floor(pageHeightPt * scale));
      const shells = makeShells(scale, cssW, cssH, pdf.numPages);
      pageEls = shells;
      paintedScale = scale;
      lastWidth = cssW;
      laidOutUrl = loadedUrl;
      for (let n = keepStart; n <= keepEnd; n++) wantFull.add(n);
      const firstReady = new Promise<void>((resolve) => {
        const done = () => {
          if (notifyFirst === done) notifyFirst = null;
          window.clearTimeout(timer);
          resolve();
        };
        notifyFirst = done;
        const timer = window.setTimeout(done, 20000);
        if (pdf.numPages === 0) done();
      });
      void indexAllText(gen);
      kickBitmap();
      await firstReady;
      if (cancelled || gen !== paintGen || loadedUrl !== activeUrl) {
        if (gen === paintGen) {
          paintGen += 1;
          for (const url of blobByPage.values()) URL.revokeObjectURL(url);
          blobByPage.clear();
          for (const [pageNumber, url] of previousBlobs) blobByPage.set(pageNumber, url);
        }
        return;
      }
      const frag = document.createDocumentFragment();
      for (const shell of shells) frag.append(shell);
      root.replaceChildren(frag);
      resetLiveScale();
      for (const url of previousBlobs.values()) URL.revokeObjectURL(url);
      applySlotWidth();
      paintedHeight = root.scrollHeight;
      rebuildTops();
      layoutCommitted = true;
      if (frame) {
        if (switchingDoc) {
          frame.scrollTop = 0;
          if (lastWidth > frame.clientWidth) frame.scrollLeft = (lastWidth - frame.clientWidth) / 2;
          else frame.scrollLeft = 0;
        } else if (zoomed) {
          frame.scrollTop = savedTop;
        } else if (savedTop > 0) {
          frame.scrollTop = savedTop * (root.scrollHeight / savedHeight);
        }
      }
      loading = false;
      syncWindow();
      onReady?.(root);
      onSettled?.(loadedUrl);
      if (textReadyPending) notifyTextReady();
    }

    function enqueuePaint(url: string): Promise<void> {
      const run = paintLock.then(() => paintPages(url));
      paintLock = run.then(
        () => {},
        () => {},
      );
      return run;
    }

    function schedulePaint() {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        void enqueuePaint(activeUrl);
      }, 220);
    }

    async function ensureEngine() {
      if (pdfjsMod && pdfWorker) return pdfjsMod;
      const pdfjs = await import('pdfjs-dist');
      const WorkerCtor = (await import('pdfjs-dist/build/pdf.worker.min.mjs?worker')).default;
      const port = new WorkerCtor();
      const worker = pdfjs.PDFWorker.create({ port });
      pdfjsMod = pdfjs;
      pdfWorker = worker;
      lifetime.push({
        destroy() {
          try {
            worker.destroy();
          } catch {
            /* ignore */
          }
          try {
            port.terminate();
          } catch {
            /* ignore */
          }
        },
      });
      return pdfjs;
    }

    loadUrl = async (url: string) => {
      activeUrl = url;
      const gen = ++loadGen;
      error = null;
      loading = true;
      try {
        const pdfjs = await ensureEngine();
        if (cancelled || gen !== loadGen) return;
        const worker = pdfWorker;
        if (!worker) return;
        const loadingTask = pdfjs.getDocument({ url, worker: worker as never });
        const pdf = await loadingTask.promise;
        if (cancelled || gen !== loadGen) {
          try {
            await (pdf as { destroy?: () => Promise<void> | void }).destroy?.();
          } catch {
            /* ignore */
          }
          return;
        }
        const previous = pdfDoc;
        pdfDoc = pdf;
        onPageCount?.(pdf.numPages, url);
        const firstPage = await pdf.getPage(1);
        const unscaled = firstPage.getViewport({ scale: 1 });
        pageWidthPt = unscaled.width;
        pageHeightPt = unscaled.height;
        try {
          firstPage.cleanup?.();
        } catch {
          /* ignore */
        }
        if (!zoomReady) {
          desiredScale = clampScale(fitHeightScale());
          zoomReady = true;
        }
        lastWidth = 0;
        paintedScale = 0;
        await enqueuePaint(url);
        if (cancelled || gen !== loadGen) return;
        loading = false;
        if (frame && laidOutUrl === url) frame.scrollTop = 0;
        try {
          await (previous as { destroy?: () => Promise<void> | void } | null)?.destroy?.();
        } catch {
          /* ignore */
        }
      } catch (e) {
        if (cancelled || gen !== loadGen) return;
        loading = false;
        if (!host?.childElementCount) {
          error = e instanceof Error ? e.message : String(e);
        }
        onSettled?.(url);
      }
    };

    function onWheel(event: WheelEvent) {
      if (!event.ctrlKey || !pdfDoc) return;
      event.preventDefault();
      event.stopPropagation();
      const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
      userHasZoomed = true;
      desiredScale = clampScale(desiredScale * factor);
      applyLiveZoom();
      schedulePaint();
    }

    function onFrameScroll() {
      if (Math.abs(liveFit - 1) > 0.002) return;
      if (scrollQueued) return;
      scrollQueued = true;
      requestAnimationFrame(() => {
        scrollQueued = false;
        syncWindow();
      });
    }

    const ro = new ResizeObserver(() => {
      if (!pdfDoc) return;
      if (!userHasZoomed) {
        const next = clampScale(fitHeightScale());
        if (Math.abs(next - desiredScale) < 0.01 && Math.abs(next - paintedScale) < 0.01) return;
        desiredScale = next;
      }
      applyLiveZoom();
      schedulePaint();
    });
    const attachObserver = () => {
      if (frame) {
        ro.observe(frame);
        frame.addEventListener('wheel', onWheel, { passive: false });
        frame.addEventListener('scroll', onFrameScroll, { passive: true });
      }
    };
    attachObserver();
    requestAnimationFrame(attachObserver);
    viewerReady = true;

    return () => {
      cancelled = true;
      paintGen += 1;
      window.clearTimeout(resizeTimer);
      ro.disconnect();
      frame?.removeEventListener('wheel', onWheel);
      frame?.removeEventListener('scroll', onFrameScroll);
      cancelPageTasks();
      revokeBlobs();
      for (const task of lifetime) {
        try {
          task.cancel?.();
          task.destroy?.();
        } catch {
          /* ignore */
        }
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
    const pageEl = event.target instanceof Element ? event.target.closest('.pdf-page') : null;
    const img =
      event.target instanceof HTMLImageElement
        ? event.target
        : pageEl?.querySelector('img') instanceof HTMLImageElement
          ? (pageEl.querySelector('img') as HTMLImageElement)
          : null;
    const canvas =
      event.target instanceof HTMLCanvasElement
        ? event.target
        : pageEl?.querySelector('canvas') instanceof HTMLCanvasElement
          ? (pageEl.querySelector('canvas') as HTMLCanvasElement)
          : null;
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
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="pdf-frame doc-frame"
  class:pdf-frame-overlay={overlay}
  bind:this={frame}
  role="document"
  oncontextmenu={onPdfContextMenu}
>
  <div class="pdf-fit" bind:this={slot}>
    <div class="pdf-pages" bind:this={host}></div>
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
