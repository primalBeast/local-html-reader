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

function scrollBox(start: Element, doc: Document): HTMLElement | Window {
  const view = doc.defaultView!;
  let node = start.parentElement;
  while (node && node !== doc.documentElement) {
    const style = view.getComputedStyle(node);
    const overflow = `${style.overflowY} ${style.overflow}`;
    if (/(auto|scroll|overlay)/.test(overflow) && node.scrollHeight > node.clientHeight + 16) return node;
    node = node.parentElement;
  }
  return view;
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

/** Draw the midpoint line and the button that scrolls the index to it. */
export function attachSideIndex(doc: Document, pageUrl: string): () => void {
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
    const main = scrollBox(pairs[0].target, doc);
    const indexScroll = scrollBox(pairs[0].link, doc);
    const madeRelative = view.getComputedStyle(index).position === 'static';
    if (madeRelative) index.style.position = 'relative';

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
      'box-shadow:0 0 0 1px rgba(26,115,232,.35)',
      'pointer-events:none',
      'z-index:2147483646',
      'top:0',
    ].join(';');
    index.appendChild(line);

    const button = doc.createElement('button');
    button.dataset.lhrIndexUi = 'button';
    button.type = 'button';
    button.textContent = 'Index';
    button.title = 'Scroll the index to the place shown in the document';
    button.style.cssText = [
      'position:fixed',
      'z-index:2147483647',
      'background:#1a73e8',
      'color:#fff',
      'border:0',
      'border-radius:4px',
      'font:600 11px/1 "Segoe UI",system-ui,sans-serif',
      'padding:5px 7px',
      'cursor:pointer',
      'box-shadow:0 1px 4px rgba(0,0,0,.28)',
    ].join(';');
    doc.body.appendChild(button);

    const placeButton = () => {
      const independent = indexScroll instanceof HTMLElement && indexScroll !== main;
      if (!independent) {
        button.style.display = 'none';
        return;
      }
      const rect = indexScroll.getBoundingClientRect();
      if (rect.width < 2 || rect.bottom < 8 || rect.top > view.innerHeight - 8) {
        button.style.display = 'none';
        return;
      }
      button.style.display = 'block';
      const top = Math.min(Math.max(rect.top, 0) + 8, Math.max(rect.top, rect.bottom - 28));
      button.style.top = `${top}px`;
      button.style.left = `${Math.min(rect.right, view.innerWidth) - 8}px`;
      button.style.transform = 'translateX(-100%)';
      button.style.width = 'max-content';
    };

    const placeLine = () => {
      const marks: IndexMark[] = [];
      for (const pair of pairs) {
        if (!pair.link.isConnected || !pair.target.isConnected) continue;
        marks.push({
          content: contentY(pair.target, main),
          index: yInIndex(pair.link, index),
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

    let frame = 0;
    const schedule = () => {
      if (disposed || frame) return;
      frame = view.requestAnimationFrame(() => {
        frame = 0;
        if (disposed) return;
        placeLine();
        placeButton();
      });
    };

    const onButton = () => {
      if (!(indexScroll instanceof HTMLElement) || indexScroll === main) return;
      placeLine();
      const lineRect = line.getBoundingClientRect();
      const host = indexScroll.getBoundingClientRect();
      const y = lineRect.top - host.top + indexScroll.scrollTop;
      const top = y - indexScroll.clientHeight / 2;
      indexScroll.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    };

    button.addEventListener('click', onButton);
    const boxes: (HTMLElement | Window)[] = [main, indexScroll, view];
    const seen = new Set<HTMLElement | Window>();
    for (const box of boxes) {
      if (seen.has(box)) continue;
      seen.add(box);
      box.addEventListener('scroll', schedule, { passive: true });
    }
    view.addEventListener('resize', schedule);
    schedule();

    stop = () => {
      if (frame) view.cancelAnimationFrame(frame);
      button.removeEventListener('click', onButton);
      for (const box of seen) box.removeEventListener('scroll', schedule);
      view.removeEventListener('resize', schedule);
      line.remove();
      button.remove();
      if (madeRelative) index.style.position = '';
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
