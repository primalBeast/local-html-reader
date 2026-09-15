<script lang="ts">
  import { onMount } from 'svelte';
  import CopyPopup from './CopyPopup.svelte';
  import { copyImageToClipboard, copyToClipboard, selectedTextIn, wordAtPoint } from './wordAtPoint';

  let {
    src,
    overlay = false,
    onReady,
  }: {
    src: string;
    overlay?: boolean;
    onReady?: (root: HTMLElement) => void;
  } = $props();

  let frame = $state<HTMLDivElement | null>(null);
  let slot = $state<HTMLDivElement | null>(null);
  let host = $state<HTMLDivElement | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let viewerReady = $state(false);
  let copyMenu = $state<{ x: number; y: number; text: string; image: HTMLImageElement | null } | null>(
    null,
  );

  let loadUrl: (url: string) => Promise<void> = async () => {};

  onMount(() => {
    let cancelled = false;
    const lifetime: Array<{ destroy?: () => void; cancel?: () => void }> = [];
    let pageTasks: Array<{ destroy?: () => void; cancel?: () => void }> = [];
    const blobUrls: string[] = [];
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
      return avail / pageHeightPt;
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

    function revokeBlobs() {
      for (const url of blobUrls) URL.revokeObjectURL(url);
      blobUrls.length = 0;
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
      slot.style.width = `${Math.max(viewW, nextVW)}px`;
      slot.style.height = `${nextVH}px`;
      liveFit = nextFit;
      scrollKeepCentered(prevVW, prevVH, Math.max(viewW, nextVW), nextVH);
    }

    async function paintPages() {
      const pdfjs = pdfjsMod;
      const pdf = pdfDoc;
      const root = host;
      if (!pdfjs || !pdf || !root) return;
      const scale = desiredScale;
      if (scale < 0.05) return;
      if (Math.abs(scale - paintedScale) < 0.002 && root.childElementCount) {
        resetLiveScale();
        return;
      }
      const gen = ++paintGen;
      cancelPageTasks();
      const first = !root.childElementCount;
      if (first) loading = true;
      const frag = document.createDocumentFragment();
      const nextBlobs: string[] = [];
      try {
        const maxPages = Math.min(pdf.numPages, 200);
        for (let n = 1; n <= maxPages; n++) {
          if (cancelled || gen !== paintGen) return;
          const page = await pdf.getPage(n);
          const viewport = page.getViewport({ scale });
          const wrap = document.createElement('div');
          wrap.className = 'pdf-page';
          wrap.style.setProperty('--scale-factor', String(scale));
          wrap.style.width = `${viewport.width}px`;
          wrap.style.height = `${viewport.height}px`;
          const canvas = document.createElement('canvas');
          const outputScale = window.devicePixelRatio || 1;
          canvas.width = Math.floor(viewport.width * outputScale);
          canvas.height = Math.floor(viewport.height * outputScale);
          canvas.style.width = `${viewport.width}px`;
          canvas.style.height = `${viewport.height}px`;
          const ctx = canvas.getContext('2d');
          if (!ctx) continue;
          const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;
          const renderTask = page.render({ canvas, viewport, transform });
          pageTasks.push(renderTask);
          await renderTask.promise;
          if (cancelled || gen !== paintGen) return;
          const textDiv = document.createElement('div');
          textDiv.className = 'textLayer';
          const textContent = await page.getTextContent();
          const layer = new pdfjs.TextLayer({
            textContentSource: textContent,
            container: textDiv,
            viewport,
          });
          pageTasks.push(layer);
          await layer.render();
          const blob = await new Promise<Blob | null>((resolve) => {
            canvas.toBlob(resolve, 'image/png');
          });
          if (cancelled || gen !== paintGen) return;
          if (blob) {
            const url = URL.createObjectURL(blob);
            nextBlobs.push(url);
            const img = document.createElement('img');
            img.src = url;
            img.alt = `Page ${n}`;
            img.draggable = true;
            img.style.width = `${viewport.width}px`;
            img.style.height = `${viewport.height}px`;
            wrap.append(img, textDiv);
          } else {
            wrap.append(canvas, textDiv);
          }
          frag.append(wrap);
        }
        if (cancelled || gen !== paintGen) {
          for (const url of nextBlobs) URL.revokeObjectURL(url);
          return;
        }
        root.replaceChildren(frag);
        revokeBlobs();
        blobUrls.push(...nextBlobs);
        resetLiveScale();
        const firstPage = root.querySelector('.pdf-page') as HTMLElement | null;
        lastWidth = firstPage ? firstPage.offsetWidth : Math.round(pageWidthPt * scale);
        paintedScale = scale;
        paintedHeight = root.scrollHeight;
        if (firstPage && lastWidth > gutterWidth() && slot) {
          slot.style.width = `${lastWidth}px`;
          root.style.width = `${lastWidth}px`;
        }
        loading = false;
        requestAnimationFrame(() => {
          if (cancelled || gen !== paintGen || !frame) return;
          if (lastWidth > frame.clientWidth) {
            frame.scrollLeft = (lastWidth - frame.clientWidth) / 2;
          } else {
            frame.scrollLeft = 0;
          }
          requestAnimationFrame(() => {
            if (cancelled || gen !== paintGen) return;
            onReady?.(root);
          });
        });
      } catch (e) {
        if (cancelled || gen !== paintGen) return;
        if (first) {
          loading = false;
          error = e instanceof Error ? e.message : String(e);
        }
      }
    }

    function schedulePaint() {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        void paintPages();
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
        const firstPage = await pdf.getPage(1);
        const unscaled = firstPage.getViewport({ scale: 1 });
        pageWidthPt = unscaled.width;
        pageHeightPt = unscaled.height;
        if (!zoomReady) {
          desiredScale = clampScale(fitHeightScale());
          zoomReady = true;
        }
        lastWidth = 0;
        paintedScale = 0;
        await paintPages();
        if (cancelled || gen !== loadGen) return;
        loading = false;
        if (frame) frame.scrollTop = 0;
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

    const ro = new ResizeObserver(() => {
      if (!pdfDoc) return;
      if (!userHasZoomed) desiredScale = clampScale(fitHeightScale());
      applyLiveZoom();
      schedulePaint();
    });
    const attachObserver = () => {
      if (frame) {
        ro.observe(frame);
        frame.addEventListener('wheel', onWheel, { passive: false });
      }
    };
    attachObserver();
    requestAnimationFrame(attachObserver);
    viewerReady = true;

    return () => {
      cancelled = true;
      window.clearTimeout(resizeTimer);
      ro.disconnect();
      frame?.removeEventListener('wheel', onWheel);
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
    const page = event.target instanceof Element ? event.target.closest('.pdf-page') : null;
    const img =
      event.target instanceof HTMLImageElement
        ? event.target
        : (page?.querySelector('img') ?? null);
    if (!text && !img) return;
    event.preventDefault();
    event.stopPropagation();
    copyMenu = {
      x: event.clientX,
      y: event.clientY,
      text,
      image: text ? null : img,
    };
  }

  async function copyPdfSelection() {
    const menu = copyMenu;
    if (!menu) return;
    try {
      if (menu.text) await copyToClipboard(menu.text);
      else if (menu.image) await copyImageToClipboard(menu.image);
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
