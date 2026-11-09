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

function canScroll(el: HTMLElement, view: Window): boolean {
  const oy = view.getComputedStyle(el).overflowY;
  if (oy !== 'auto' && oy !== 'scroll' && oy !== 'overlay' && oy !== 'hidden') return false;
  return el.scrollHeight > el.clientHeight + 24 && el.clientHeight > 80;
}

function scrollerFrom(start: Element | null, doc: Document): HTMLElement | Window {
  const view = doc.defaultView!;
  let node: Element | null = start;
  while (node) {
    if (node instanceof view.HTMLElement && canScroll(node, view)) return node;
    node = node.parentElement;
  }
  return view;
}

function mainScroller(doc: Document, index: HTMLElement, pairs: Pair[]): HTMLElement | Window {
  const view = doc.defaultView!;
  const counts = new Map<HTMLElement | Window, number>();
  for (const pair of pairs) {
    if (index.contains(pair.target)) continue;
    const scroller = scrollerFrom(pair.target, doc);
    counts.set(scroller, (counts.get(scroller) || 0) + 1);
  }
  let best: HTMLElement | Window = view;
  let bestN = 0;
  for (const [scroller, n] of counts) {
    if (n > bestN) {
      best = scroller;
      bestN = n;
    }
  }
  const viewport = view.innerHeight || doc.documentElement.clientHeight || 1;
  if (best instanceof view.HTMLElement && best.clientHeight < viewport * 0.55) {
    let node = best.parentElement;
    while (node) {
      if (node instanceof view.HTMLElement && canScroll(node, view) && node.clientHeight >= viewport * 0.55) {
        return node;
      }
      node = node.parentElement;
    }
    return view;
  }
  return best;
}

function bestIndexScroller(index: HTMLElement, doc: Document, main: HTMLElement | Window): HTMLElement | null {
  const view = doc.defaultView!;
  const skip = (el: HTMLElement) =>
    el === main || el === doc.body || el === doc.documentElement;
  let best: HTMLElement | null = null;
  let bestSpan = 0;
  const consider = (el: HTMLElement) => {
    if (skip(el) || !canScroll(el, view)) return;
    const span = el.scrollHeight - el.clientHeight;
    if (span > bestSpan) {
      best = el;
      bestSpan = span;
    }
  };
  consider(index);
  for (const node of index.querySelectorAll('*')) {
    if (node instanceof view.HTMLElement) consider(node);
  }
  if (best) return best;
  let node = index.parentElement;
  while (node) {
    consider(node);
    if (best) return best;
    node = node.parentElement;
  }
  return null;
}

function contentY(el: Element, scroller: HTMLElement | Window): number {
  const box = el.getBoundingClientRect();
  if (scroller instanceof Window) return box.top + scroller.scrollY;
  const host = scroller.getBoundingClientRect();
  return box.top - host.top + scroller.scrollTop;
}

function midpointY(scroller: HTMLElement | Window): number {
  if (scroller instanceof Window) return scroller.scrollY + scroller.innerHeight / 2;
  return scroller.scrollTop + scroller.clientHeight / 2;
}

function yInIndex(el: Element, index: HTMLElement): number {
  const host = index.getBoundingClientRect();
  const box = el.getBoundingClientRect();
  return box.top - host.top + index.scrollTop + box.height / 2;
}

/** Draw the midpoint line. Calls onSync with a function that scrolls the index to that line. */
export function attachSideIndex(
  doc: Document,
  pageUrl: string,
  onSync?: (sync: (() => void) | null) => void,
): () => void {
  const view = doc.defaultView;
  if (!view) return () => {};
  let disposed = false;
  let stop = () => {};
  const mount = () => {
    if (disposed || doc.querySelector('[data-lhr-index-ui]')) return;
    const index = chooseIndex(doc, collectPairs(doc, pageUrl));
    if (!index) return;
    const pairs = collectPairs(doc, pageUrl).filter(
      (pair) => index.contains(pair.link) && !index.contains(pair.target),
    );
    if (pairs.length < 4) return;
    const mainAtMount = mainScroller(doc, index, pairs);
    const scroller = bestIndexScroller(index, doc, mainAtMount);
    const host = scroller && scroller.contains(pairs[0].link) ? scroller : index;
    const madeRelative = view.getComputedStyle(host).position === 'static';
    if (madeRelative) host.style.position = 'relative';

    const line = doc.createElement('div');
    line.dataset.lhrIndexUi = 'line';
    line.setAttribute('aria-hidden', 'true');
    line.style.cssText = [
      'position:absolute',
      'left:0',
      'right:0',
      'height:3px',
      'margin:0',
      'padding:0',
      'border:0',
      'background:#1a73e8',
      'box-shadow:0 0 0 1px rgba(26,115,232,.45)',
      'pointer-events:none',
      'z-index:2147483646',
      'top:0',
    ].join(';');
    host.appendChild(line);

    const placeLine = () => {
      const main = mainScroller(doc, index, pairs);
      const marks: IndexMark[] = [];
      for (const pair of pairs) {
        if (!pair.link.isConnected || !pair.target.isConnected) continue;
        marks.push({
          content: contentY(pair.target, main),
          index: yInIndex(pair.link, host),
        });
      }
      const y = indexMarkY(marks, midpointY(main));
      if (y === null) {
        line.style.display = 'none';
        return;
      }
      line.style.display = 'block';
      line.style.top = `${y}px`;
    };

    const sync = () => {
      placeLine();
      const box = scroller ?? bestIndexScroller(index, doc, mainScroller(doc, index, pairs));
      if (!box) return;
      const lineRect = line.getBoundingClientRect();
      const boxRect = box.getBoundingClientRect();
      const y = lineRect.top - boxRect.top + box.scrollTop;
      box.scrollTo({ top: Math.max(0, y - box.clientHeight / 2), behavior: 'smooth' });
    };

    let frame = 0;
    const schedule = () => {
      if (disposed || frame) return;
      frame = view.requestAnimationFrame(() => {
        frame = 0;
        if (disposed) return;
        placeLine();
      });
    };

    doc.addEventListener('scroll', schedule, { capture: true, passive: true });
    doc.addEventListener('wheel', schedule, { capture: true, passive: true });
    view.addEventListener('scroll', schedule, { capture: true, passive: true });
    view.addEventListener('resize', schedule);
    schedule();
    onSync?.(sync);

    stop = () => {
      if (frame) view.cancelAnimationFrame(frame);
      doc.removeEventListener('scroll', schedule, { capture: true });
      doc.removeEventListener('wheel', schedule, { capture: true });
      view.removeEventListener('scroll', schedule, { capture: true });
      view.removeEventListener('resize', schedule);
      line.remove();
      if (madeRelative) host.style.position = '';
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
  return () => {
    disposed = true;
    view.clearTimeout(timer);
    stop();
  };
}
