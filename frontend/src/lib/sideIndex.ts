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

/** Draw the midpoint line. Calls onSync with a function that scrolls the index to that line. */
export function attachSideIndex(
  doc: Document,
  pageUrl: string,
  onSync?: (sync: (() => void) | null) => void,
  onLine?: (line: IndexLine | null) => void,
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
      if (y === null || pane.width < 2 || pane.bottom < 0 || pane.top > view.innerHeight) {
        onLine?.(null);
        return;
      }
      onLine?.({ top: y - 1, left: pane.left, width: pane.width });
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
          const delta = linkBox.top + linkBox.height / 2 - (paneBox.top + paneBox.height / 2);
          if (Math.abs(delta) > 2) {
            node.scrollTop = before + delta;
            if (Math.abs(node.scrollTop - before) > 1) return;
          }
        }
        node = node.parentElement;
      }
    };

    let frame = 0;
    const watch = () => {
      if (disposed) return;
      placeLine();
      frame = view.requestAnimationFrame(watch);
    };
    frame = view.requestAnimationFrame(watch);
    onSync?.(sync);

    stop = () => {
      if (frame) view.cancelAnimationFrame(frame);
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
  return () => {
    disposed = true;
    view.clearTimeout(timer);
    stop();
  };
}
