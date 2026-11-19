import { correctScrollByVisual, pageFraction, zoomAnchorSettled, ZOOM_ANCHOR_ITERS } from './docZoom';
import { hashForSameFile } from './inPageLink';

export type IndexMark = { content: number; index: number };

/** Y of the index line for the midpoint of the visible main text. */
export function indexMarkY(marks: IndexMark[], midpoint: number): number | null {
  if (marks.length === 0) return null;
  const ordered = [...marks].sort((a, b) => a.content - b.content || a.index - b.index);
  if (midpoint <= ordered[0].content) return ordered[0].index;
  const last = ordered[ordered.length - 1];
  if (midpoint >= last.content) return last.index;
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1];
    const next = ordered[i];
    if (midpoint > next.content) continue;
    const span = next.content - prev.content;
    const t = span > 0 ? (midpoint - prev.content) / span : 0;
    return prev.index + t * (next.index - prev.index);
  }
  return last.index;
}

type Pair = { link: HTMLAnchorElement; target: Element };

function fragmentTarget(doc: Document, hash: string): Element | null {
  const bare = hash.startsWith('#') ? hash.slice(1) : hash;
  if (!bare) return null;
  let id = bare;
  try {
    id = decodeURIComponent(bare);
  } catch {
    /* keep the raw id */
  }
  return doc.getElementById(id) || doc.getElementsByName(id)[0] || null;
}

function collectPairs(doc: Document, pageUrl: string): Pair[] {
  const pairs: Pair[] = [];
  for (const node of doc.querySelectorAll('a[href]')) {
    if (!(node instanceof doc.defaultView!.HTMLAnchorElement)) continue;
    if (node.closest('[data-lhr-index-ui]')) continue;
    const raw = node.getAttribute('href') || '';
    const hrefValue = node.href;
    const resolved = typeof hrefValue === 'string' && hrefValue ? hrefValue : raw;
    const hash = hashForSameFile(raw, resolved, pageUrl);
    if (!hash || hash === '#') continue;
    const target = fragmentTarget(doc, hash);
    if (!target || target === node || node.contains(target)) continue;
    const box = node.getBoundingClientRect();
    if (box.width < 1 && box.height < 1) continue;
    pairs.push({ link: node, target });
  }
  return pairs;
}

function onSide(rect: DOMRect, width: number): boolean {
  if (rect.width < 40 || rect.height < 40 || rect.width >= width * 0.55) return false;
  const onLeft = rect.left <= width * 0.1 && rect.right < width * 0.52;
  const onRight = rect.right >= width * 0.9 && rect.left > width * 0.48;
  return onLeft || onRight;
}

function chooseIndex(doc: Document, pairs: Pair[]): HTMLElement | null {
  const view = doc.defaultView;
  if (!view) return null;
  const width = view.innerWidth || doc.documentElement.clientWidth;
  if (width < 200) return null;
  const counts = new Map<HTMLElement, number>();
  for (const pair of pairs) {
    let node = pair.link.parentElement;
    while (node && node !== doc.body && node !== doc.documentElement) {
      const rect = node.getBoundingClientRect();
      if (!onSide(rect, width)) break;
      counts.set(node, (counts.get(node) || 0) + 1);
      node = node.parentElement;
    }
  }
  let bestCount = 0;
  for (const count of counts.values()) if (count > bestCount) bestCount = count;
  if (bestCount < 4) return null;
  const fullest = [...counts.keys()].filter((el) => counts.get(el) === bestCount);
  const tight = fullest.filter((el) => !fullest.some((other) => other !== el && el.contains(other)));
  tight.sort((a, b) => b.getBoundingClientRect().height - a.getBoundingClientRect().height);
  return tight[0] ?? null;
}

function targetTop(el: Element): number | null {
  const box = el.getBoundingClientRect();
  if (box.width === 0 && box.height === 0 && box.top === 0 && box.left === 0) return null;
  return box.top;
}

export type IndexLine = { top: number; left: number; width: number };

/**
 * Visual pixels (getBoundingClientRect, after CSS zoom) → this element's CSS
 * pixels (scrollTop). Scale is visualHeight / cssHeight. A non-finite or
 * non-positive size uses scale 1, so the visual delta is returned unchanged.
 */
export function cssPixelsFromVisual(
  visualDelta: number,
  visualHeight: number,
  cssHeight: number,
): number {
  if (!Number.isFinite(visualDelta)) return visualDelta;
  if (!Number.isFinite(visualHeight) || visualHeight <= 0) return visualDelta;
  if (!Number.isFinite(cssHeight) || cssHeight <= 0) return visualDelta;
  return visualDelta / (visualHeight / cssHeight);
}

/**
 * Visual Y of the center of a scroller's border box that lies in the viewport.
 * visibleTop = max(paneTop, 0), visibleBottom = min(paneBottom, viewH).
 * A slice shorter than 4px falls back to the box center (top + height / 2).
 */
export function visiblePaneCenter(
  pane: { top: number; height: number; bottom: number },
  viewH: number,
): number {
  const visibleTop = Math.max(pane.top, 0);
  const visibleBottom = Math.min(pane.bottom, viewH);
  if (visibleBottom - visibleTop < 4) return pane.top + pane.height / 2;
  return (visibleTop + visibleBottom) / 2;
}

/**
 * Unclamped blue-line Y to hold across zoom, or null.
 * Null when the line is missing or outside the visible contents: the caller
 * then holds the link fraction at the visible centre. CSS zoom reflows the
 * main text, so this Y is not scale-invariant. The caller stores it and
 * reclamps it on each step.
 */
export function contentsLineHold(
  lineY: number | null,
  visibleTop: number,
  visibleBottom: number,
): number | null {
  if (
    lineY !== null &&
    Number.isFinite(lineY) &&
    Number.isFinite(visibleTop) &&
    Number.isFinite(visibleBottom) &&
    visibleBottom >= visibleTop &&
    lineY >= visibleTop &&
    lineY <= visibleBottom
  ) {
    return lineY;
  }
  return null;
}

/**
 * Y held in the contents list across a zoom.
 * The blue line wins when it lies in the scroller's visible span. Otherwise
 * the visible centre, including when the line is scrolled out of view.
 */
export function contentsHoldY(
  lineY: number | null,
  visibleTop: number,
  visibleBottom: number,
  visibleCentre: number,
): number {
  const line = contentsLineHold(lineY, visibleTop, visibleBottom);
  if (line !== null) return line;
  return Number.isFinite(visibleCentre) ? visibleCentre : 0;
}

/**
 * Aim used for this zoom step. A sticky `height: 100vh` contents pane is
 * scaled by CSS zoom, so at 50% it is only half the viewport tall and the
 * original screen Y can sit below it. Clamp the aim to the visible span.
 * The caller keeps the original target and uses it again on the next step.
 * An unusable span leaves the target unchanged.
 */
export function clampContentsTarget(targetY: number, visibleTop: number, visibleBottom: number): number {
  if (!Number.isFinite(targetY)) return targetY;
  if (!Number.isFinite(visibleTop) || !Number.isFinite(visibleBottom) || !(visibleBottom >= visibleTop)) {
    return targetY;
  }
  if (targetY < visibleTop) return visibleTop;
  if (targetY > visibleBottom) return visibleBottom;
  return targetY;
}

/**
 * How far a contents point has drifted from the screen Y it was held at.
 * `offset` is the point's distance from `anchorY` when it was recorded
 * (0 when the point itself should sit on the aim). Positive means the
 * point is too low. A non-finite input does not move the list.
 */
export function contentsLinkError(linkPoint: number, anchorY: number, offset: number): number {
  if (!Number.isFinite(linkPoint) || !Number.isFinite(anchorY) || !Number.isFinite(offset)) return 0;
  return linkPoint - (anchorY + offset);
}

/**
 * Link under the blue line, the fraction of that link, and the screen Y to hold.
 * `lineY0` is the unclamped interpolated line when it lay inside the visible
 * contents. Null keeps the link-fraction anchor (no line, or the line was outside).
 */
export type ContentsZoomAnchor = {
  link: HTMLAnchorElement;
  fraction: number;
  targetY: number;
  lineY0: number | null;
};

export type SideIndexZoomToken = { id: number };

export type SideIndexZoomResult = {
  /** Original link, fraction, target Y, and line Y. Not the clamped aim. */
  anchor: ContentsZoomAnchor | null;
  scrollTop: number | null;
};

const emptyZoomResult = (): SideIndexZoomResult => ({ anchor: null, scrollTop: null });

export type SideIndexController = {
  destroy: () => void;
  /**
   * Record the contents anchor and pause the line watcher.
   * `reuse`, when the link is still in this index, keeps that anchor
   * (including the original line Y) instead of capturing a new one.
   */
  beginZoom: (reuse?: ContentsZoomAnchor | null) => SideIndexZoomToken | null;
  /** Scroll the contents anchor back, draw the line once, and resume the watcher. */
  endZoom: (token: SideIndexZoomToken | null) => SideIndexZoomResult;
  /** The contents element this index chose, once it is mounted. */
  contentsElement: () => HTMLElement | null;
  /** Contents scroller scrollTop, or null when the list has no scroller of its own. */
  contentsScrollTop: () => number | null;
};

function scrollsOnY(el: HTMLElement, view: Window): boolean {
  if (el.scrollHeight <= el.clientHeight + 1) return false;
  const oy = view.getComputedStyle(el).overflowY;
  return oy === 'auto' || oy === 'scroll' || oy === 'overlay';
}

/**
 * The contents list's own scroller: the index, or the nearest scrollable
 * ancestor that does not also scroll the main text. The document scroller
 * is the main document's job.
 */
function contentsScroller(index: HTMLElement, doc: Document, pairs: Pair[]): HTMLElement | null {
  const view = doc.defaultView;
  if (!view) return null;
  const root = doc.scrollingElement;
  const holdsMain = (el: HTMLElement) =>
    pairs.some((pair) => !index.contains(pair.target) && el.contains(pair.target));
  let node: HTMLElement | null = index;
  while (node && node !== root && node !== doc.body && node !== doc.documentElement) {
    if (holdsMain(node)) return null;
    if (scrollsOnY(node, view)) return node;
    node = node.parentElement;
  }
  return null;
}

/**
 * Draw the midpoint line. Calls onSync with a function that scrolls the index to that line.
 * `beginZoom` / `endZoom` hold the contents list across a document zoom.
 */
export function attachSideIndex(
  doc: Document,
  pageUrl: string,
  onSync?: (sync: (() => void) | null) => void,
  onLine?: (line: IndexLine | null) => void,
): SideIndexController {
  const view = doc.defaultView;
  if (!view) {
    return {
      destroy() {},
      beginZoom: () => null,
      endZoom: () => emptyZoomResult(),
      contentsElement: () => null,
      contentsScrollTop: () => null,
    };
  }
  let disposed = false;
  let stop = () => {};
  let zoomBegin: (reuse?: ContentsZoomAnchor | null) => SideIndexZoomToken | null = () => null;
  let zoomEnd: (token: SideIndexZoomToken | null) => SideIndexZoomResult = () => emptyZoomResult();
  let zoomContents: () => HTMLElement | null = () => null;
  let zoomScrollTop: () => number | null = () => null;
  const mount = () => {
    if (disposed || doc.querySelector('[data-lhr-index-ui]')) return;
    const index = chooseIndex(doc, collectPairs(doc, pageUrl));
    if (!index) return;
    const pairs = collectPairs(doc, pageUrl).filter(
      (pair) => index.contains(pair.link) && !index.contains(pair.target),
    );
    if (pairs.length < 4) return;

    const marker = doc.createElement('span');
    marker.dataset.lhrIndexUi = 'marker';
    marker.hidden = true;
    doc.body.appendChild(marker);

    const placeLine = () => {
      const mid = (view.innerHeight || doc.documentElement.clientHeight) / 2;
      const marks: IndexMark[] = [];
      for (const pair of pairs) {
        if (!pair.link.isConnected || !pair.target.isConnected) continue;
        const content = targetTop(pair.target);
        const linkBox = pair.link.getBoundingClientRect();
        if (content === null || (linkBox.width < 1 && linkBox.height < 1)) continue;
        marks.push({ content, index: linkBox.top + linkBox.height / 2 });
      }
      const y = indexMarkY(marks, mid);
      const pane = index.getBoundingClientRect();
      const viewH = view.innerHeight || doc.documentElement.clientHeight;
      if (y === null || pane.width < 2 || pane.height < 2) {
        onLine?.(null);
        return;
      }
      const visibleTop = Math.max(pane.top, 0);
      const visibleBottom = Math.min(pane.bottom, viewH);
      if (visibleBottom - visibleTop < 4) {
        onLine?.(null);
        return;
      }
      const clamped = Math.min(Math.max(y, visibleTop), visibleBottom - 3);
      onLine?.({ top: clamped, left: pane.left, width: pane.width });
    };

    const sync = () => {
      placeLine();
      const mid = (view.innerHeight || doc.documentElement.clientHeight) / 2;
      const marks: IndexMark[] = [];
      for (const pair of pairs) {
        const content = targetTop(pair.target);
        if (content === null) continue;
        const linkBox = pair.link.getBoundingClientRect();
        marks.push({ content, index: linkBox.top + linkBox.height / 2 });
      }
      const y = indexMarkY(marks, mid);
      if (y === null) return;
      let closest: HTMLAnchorElement | null = null;
      let bestDist = Infinity;
      for (const pair of pairs) {
        const linkBox = pair.link.getBoundingClientRect();
        const dist = Math.abs(linkBox.top + linkBox.height / 2 - y);
        if (dist < bestDist) {
          bestDist = dist;
          closest = pair.link;
        }
      }
      if (!closest) return;
      const holdsMain = (el: HTMLElement) =>
        pairs.some((pair) => !index.contains(pair.target) && el.contains(pair.target));
      let node: HTMLElement | null = closest.parentElement;
      while (node && node !== doc.body && node !== doc.documentElement) {
        if (!holdsMain(node) && node.scrollHeight > node.clientHeight + 16) {
          const before = node.scrollTop;
          const linkBox = closest.getBoundingClientRect();
          const paneBox = node.getBoundingClientRect();
          const viewH = view.innerHeight || doc.documentElement.clientHeight;
          const delta = linkBox.top + linkBox.height / 2 - visiblePaneCenter(paneBox, viewH);
          // delta is visual pixels. The 2px and 1px gates stay in those pixels.
          if (Math.abs(delta) > 2) {
            node.scrollTop = before + cssPixelsFromVisual(delta, paneBox.height, node.offsetHeight);
            const oneVisual = cssPixelsFromVisual(1, paneBox.height, node.offsetHeight);
            if (Math.abs(node.scrollTop - before) > oneVisual) return;
          }
        }
        node = node.parentElement;
      }
    };

    let frame = 0;
    let paused = false;
    let zoomSeq = 0;
    let zoomHold: {
      id: number;
      scroller: HTMLElement | null;
      anchor: ContentsZoomAnchor | null;
    } | null = null;

    const rawLineY = () => {
      const mid = (view.innerHeight || doc.documentElement.clientHeight) / 2;
      const marks: IndexMark[] = [];
      for (const pair of pairs) {
        if (!pair.link.isConnected || !pair.target.isConnected) continue;
        const content = targetTop(pair.target);
        const linkBox = pair.link.getBoundingClientRect();
        if (content === null || (linkBox.width < 1 && linkBox.height < 1)) continue;
        marks.push({ content, index: linkBox.top + linkBox.height / 2 });
      }
      return indexMarkY(marks, mid);
    };

    const linkUnder = (y: number): { link: HTMLAnchorElement; fraction: number } | null => {
      let containing: { link: HTMLAnchorElement; fraction: number; dist: number } | null = null;
      let closest: { link: HTMLAnchorElement; fraction: number; dist: number } | null = null;
      for (const pair of pairs) {
        if (!pair.link.isConnected) continue;
        const box = pair.link.getBoundingClientRect();
        if (box.height < 1) continue;
        const mid = box.top + box.height / 2;
        const dist = Math.abs(mid - y);
        const fraction = pageFraction(y, box.top, box.height);
        if (!closest || dist < closest.dist) closest = { link: pair.link, fraction, dist };
        if (y >= box.top && y <= box.bottom && (!containing || dist < containing.dist)) {
          containing = { link: pair.link, fraction, dist };
        }
      }
      const picked = containing ?? closest;
      return picked ? { link: picked.link, fraction: picked.fraction } : null;
    };

    const visibleContentsSpan = (scroller: HTMLElement): { top: number; bottom: number } => {
      const pane = scroller.getBoundingClientRect();
      const viewH = view.innerHeight || doc.documentElement.clientHeight;
      return { top: Math.max(pane.top, 0), bottom: Math.min(pane.bottom, viewH) };
    };

    const pauseWatch = () => {
      paused = true;
      if (frame) {
        view.cancelAnimationFrame(frame);
        frame = 0;
      }
    };

    const resumeWatch = () => {
      if (disposed) return;
      paused = false;
      if (!frame) frame = view.requestAnimationFrame(watch);
    };

    const watch = () => {
      frame = 0;
      if (disposed || paused) return;
      placeLine();
      if (disposed || paused) return;
      frame = view.requestAnimationFrame(watch);
    };

    // Hold the blue line's screen Y while the main document centre stays fixed.
    // CSS zoom reflows the main text: the column is narrower in CSS px, so the
    // same sections take more lines. indexMarkY interpolates between those
    // section tops, so it is not scale-invariant (100%→150% grew one section
    // span by about ×1.96, not ×1.5). Holding the link under the line lets the
    // line drift by a few pixels and can flip the active entry. Scrolling the
    // list by d visual px moves every link centre and therefore the interpolated
    // line by d. When the line is missing or outside the visible contents, fall
    // back to the link fraction at the visible centre. A sticky 100vh pane can
    // leave the original Y outside the new span; that step clamps the aim and
    // the session keeps the original lineY0 so the next step can restore it.
    // Zoom does not change the active row and does not run Sync Contents.
    // The watcher stays paused until the correction finishes, then the line
    // is drawn once so an intermediate frame cannot show a different entry.
    zoomBegin = (reuse) => {
      pauseWatch();
      const id = ++zoomSeq;
      const scroller = contentsScroller(index, doc, pairs);
      let anchor: ContentsZoomAnchor | null = null;
      if (reuse?.link.isConnected && index.contains(reuse.link)) {
        anchor = {
          link: reuse.link,
          fraction: reuse.fraction,
          targetY: reuse.targetY,
          lineY0: reuse.lineY0,
        };
      } else if (scroller) {
        const pane = scroller.getBoundingClientRect();
        const span = visibleContentsSpan(scroller);
        const viewH = view.innerHeight || doc.documentElement.clientHeight;
        const lineY = rawLineY();
        const targetY = contentsHoldY(lineY, span.top, span.bottom, visiblePaneCenter(pane, viewH));
        const lineY0 = contentsLineHold(lineY, span.top, span.bottom);
        const found = linkUnder(targetY);
        if (found) anchor = { link: found.link, fraction: found.fraction, targetY, lineY0 };
      }
      zoomHold = { id, scroller, anchor };
      return { id };
    };

    zoomEnd = (token) => {
      if (!token || zoomHold?.id !== token.id) return emptyZoomResult();
      const hold = zoomHold;
      zoomHold = null;
      const { scroller, anchor } = hold;
      if (scroller && anchor?.link.isConnected) {
        const lineY0 = anchor.lineY0;
        if (typeof lineY0 === 'number' && Number.isFinite(lineY0)) {
          // zoomEnd runs after the main-document centre correction, so rawLineY
          // already includes reflow. d visual px of contents scroll moves the line by d.
          for (let i = 0; i < ZOOM_ANCHOR_ITERS; i++) {
            const span = visibleContentsSpan(scroller);
            const aim = clampContentsTarget(lineY0, span.top, span.bottom);
            const lineY = rawLineY();
            const error = lineY === null || !Number.isFinite(lineY) ? Number.NaN : lineY - aim;
            if (zoomAnchorSettled(error)) break;
            const moved = correctScrollByVisual(
              error,
              () => scroller.scrollTop,
              (value) => {
                scroller.scrollTop = value;
              },
              () => rawLineY(),
            );
            if (!moved) break;
          }
        } else {
          const link = anchor.link;
          for (let i = 0; i < ZOOM_ANCHOR_ITERS; i++) {
            const span = visibleContentsSpan(scroller);
            // A sticky 100vh list is shorter under CSS zoom. Aim inside the
            // visible span for this step and keep the original targetY.
            const aim = clampContentsTarget(anchor.targetY, span.top, span.bottom);
            const box = link.getBoundingClientRect();
            if (!(box.height > 0)) break;
            const point = box.top + anchor.fraction * box.height;
            const visualDelta = contentsLinkError(point, aim, 0);
            if (zoomAnchorSettled(visualDelta)) break;
            const moved = correctScrollByVisual(
              visualDelta,
              () => scroller.scrollTop,
              (value) => {
                scroller.scrollTop = value;
              },
              () => {
                const next = link.getBoundingClientRect();
                return next.top + anchor.fraction * next.height;
              },
            );
            if (!moved) break;
          }
        }
      }
      placeLine();
      resumeWatch();
      return {
        anchor: anchor?.link.isConnected ? anchor : null,
        scrollTop: scroller ? scroller.scrollTop : null,
      };
    };

    zoomContents = () => index;
    zoomScrollTop = () => {
      const scroller = contentsScroller(index, doc, pairs);
      return scroller ? scroller.scrollTop : null;
    };
    frame = view.requestAnimationFrame(watch);
    onSync?.(sync);

    stop = () => {
      paused = true;
      if (frame) view.cancelAnimationFrame(frame);
      frame = 0;
      zoomHold = null;
      zoomScrollTop = () => null;
      marker.remove();
      onLine?.(null);
      onSync?.(null);
    };
  };

  let timer = 0;
  let tries = 0;
  const attempt = () => {
    if (disposed || doc.querySelector('[data-lhr-index-ui]')) return;
    mount();
    tries += 1;
    if (!disposed && !doc.querySelector('[data-lhr-index-ui]') && tries < 4) {
      timer = view.setTimeout(attempt, 150 * tries);
    }
  };
  view.requestAnimationFrame(attempt);
  return {
    destroy() {
      disposed = true;
      view.clearTimeout(timer);
      stop();
      zoomBegin = () => null;
      zoomEnd = () => emptyZoomResult();
      zoomContents = () => null;
      zoomScrollTop = () => null;
    },
    beginZoom: (reuse) => (disposed ? null : zoomBegin(reuse)),
    endZoom: (token) => (disposed ? emptyZoomResult() : zoomEnd(token)),
    contentsElement: () => (disposed ? null : zoomContents()),
    contentsScrollTop: () => (disposed ? null : zoomScrollTop()),
  };
}
