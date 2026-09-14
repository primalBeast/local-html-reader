<script lang="ts">
  import { onMount } from 'svelte';

  let {
    src,
    onReady,
  }: {
    src: string;
    onReady?: (root: HTMLElement) => void;
  } = $props();

  let frame = $state<HTMLDivElement | null>(null);
  let slot = $state<HTMLDivElement | null>(null);
  let host = $state<HTMLDivElement | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let viewerReady = $state(false);

  let loadUrl: (url: string) => Promise<void> = async () => {};

  onMount(() => {
    let cancelled = false;
    const lifetime: Array<{ destroy?: () => void; cancel?: () => void }> = [];
    let pageTasks: Array<{ destroy?: () => void; cancel?: () => void }> = [];
    let pdfjsMod: typeof import('pdfjs-dist') | null = null;
    let pdfWorker: { destroy?: () => void } | null = null;
    let pdfDoc: { numPages: number; getPage: (n: number) => Promise<any>; destroy?: () => void } | null = null;
    let paintGen = 0;
    let loadGen = 0;
    let lastWidth = 0;
    let paintedHeight = 0;
    let resizeTimer = 0;

    function gutterWidth(): number {
      const el = slot || frame;
      if (!el) return 0;
      return Math.max(160, Math.floor(el.clientWidth));
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

    function resetLiveScale() {
      if (host) {
        host.style.transform = '';
        host.style.width = '';
        host.style.marginLeft = '';
      }
      if (slot) slot.style.height = '';
    }

    function applyLiveScale(targetWidth: number) {
      if (!host || !slot || lastWidth < 80 || !host.childElementCount) return;
      const fit = targetWidth / lastWidth;
      if (!Number.isFinite(fit) || fit <= 0) return;
      if (Math.abs(fit - 1) < 0.002) {
        resetLiveScale();
        return;
      }
      // Keep the unscaled page centered in the pane, then scale from its
      // center. Without the negative margin, a too-wide page left-aligns
      // and shrinking slides the left edge right.
      host.style.width = `${lastWidth}px`;
      host.style.marginLeft = `${(targetWidth - lastWidth) / 2}px`;
      host.style.transformOrigin = 'top center';
      host.style.transform = `scale(${fit})`;
      const base = paintedHeight || host.scrollHeight;
      slot.style.height = `${base * fit}px`;
    }

    async function paintPages() {
      const pdfjs = pdfjsMod;
      const pdf = pdfDoc;
      const root = host;
      if (!pdfjs || !pdf || !root) return;
      const cssWidth = gutterWidth();
      if (cssWidth < 80) return;
      if (Math.abs(cssWidth - lastWidth) < 2 && root.childElementCount) {
        resetLiveScale();
        return;
      }
      const gen = ++paintGen;
      cancelPageTasks();
      const first = !root.childElementCount;
      if (first) loading = true;
      const frag = document.createDocumentFragment();
      try {
        const maxPages = Math.min(pdf.numPages, 200);
        for (let n = 1; n <= maxPages; n++) {
          if (cancelled || gen !== paintGen) return;
          const page = await pdf.getPage(n);
          const unscaled = page.getViewport({ scale: 1 });
          const scale = cssWidth / unscaled.width;
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
          wrap.append(canvas, textDiv);
          frag.append(wrap);
        }
        if (cancelled || gen !== paintGen) return;
        root.replaceChildren(frag);
        lastWidth = cssWidth;
        resetLiveScale();
        paintedHeight = root.scrollHeight;
        loading = false;
        onReady?.(root);
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
        lastWidth = 0;
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

    const ro = new ResizeObserver(() => {
      if (!pdfDoc) return;
      applyLiveScale(gutterWidth());
      schedulePaint();
    });
    const attachObserver = () => {
      if (frame) ro.observe(frame);
    };
    attachObserver();
    requestAnimationFrame(attachObserver);
    viewerReady = true;

    return () => {
      cancelled = true;
      window.clearTimeout(resizeTimer);
      ro.disconnect();
      cancelPageTasks();
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
</script>

<div class="pdf-frame doc-frame" bind:this={frame}>
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
