export type FindLayer = 'list' | 'page';
export type FindRoot = Document | HTMLElement;

const STYLE_ID = 'lhr-find-style';

const LAYERS: Record<FindLayer, { mark: string; current: string }> = {
  list: { mark: 'lhr-find-list', current: 'lhr-find-list-current' },
  page: { mark: 'lhr-find-page', current: 'lhr-find-page-current' },
};

function isDocumentNode(root: FindRoot): root is Document {
  return root.nodeType === 9;
}

function ownerDoc(root: FindRoot): Document {
  if (isDocumentNode(root)) return root;
  const doc = (root as HTMLElement).ownerDocument;
  if (doc) return doc;
  return root as unknown as Document;
}

function queryScope(root: FindRoot): ParentNode {
  if (isDocumentNode(root)) {
    return root.body ?? root.documentElement ?? root;
  }
  return root;
}

function injectStyle(root: FindRoot): void {
  const doc = ownerDoc(root);
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement('style');
  style.id = STYLE_ID;
  style.textContent =
    'mark.lhr-find-list{background:#ffe58a;color:inherit;padding:0;}' +
    'mark.lhr-find-list-current{background:#ff9f1a;color:#111;}' +
    'mark.lhr-find-page{background:#a5d8ff;color:inherit;padding:0;}' +
    'mark.lhr-find-page-current{background:#4dabf7;color:#111;}' +
    'mark.lhr-find-list.lhr-find-page{background:#c4e8a8;}' +
    'mark.lhr-find-list-current.lhr-find-page,mark.lhr-find-list.lhr-find-page-current,' +
    'mark.lhr-find-list-current.lhr-find-page-current{background:#ff9f1a;color:#111;}' +
    '.textLayer mark{color:transparent;}';
  (doc.head || doc.documentElement).appendChild(style);
}

function unwrapMarks(root: FindRoot, selector: string): void {
  const doc = ownerDoc(root);
  const marks = Array.from(queryScope(root).querySelectorAll(selector));
  for (const el of marks) {
    const parent = el.parentNode;
    if (!parent) continue;
    parent.replaceChild(doc.createTextNode(el.textContent || ''), el);
    parent.normalize();
  }
}

export function clearFind(root: FindRoot, layer?: FindLayer): void {
  const scope = queryScope(root);
  if (layer) {
    unwrapMarks(root, `mark.${LAYERS[layer].mark}`);
    scope.querySelectorAll(`.lhr-pdf-hl-group.${LAYERS[layer].mark}`).forEach((el) => el.remove());
    return;
  }
  unwrapMarks(root, 'mark.lhr-find-list, mark.lhr-find-page');
  scope.querySelectorAll('.lhr-pdf-hl-group').forEach((el) => el.remove());
}

function isPdfRoot(root: FindRoot): root is HTMLElement {
  if (!(root instanceof HTMLElement)) return false;
  if (root.closest('.pdf-page, .pdf-pages, .pdf-frame')) return true;
  return Boolean(root.querySelector(':scope > .pdf-page, :scope > .textLayer, .pdf-page'));
}

function isSkippedElement(el: Element): boolean {
  const tag = el.tagName;
  if (
    tag === 'SCRIPT' ||
    tag === 'STYLE' ||
    tag === 'NOSCRIPT' ||
    tag === 'TEMPLATE' ||
    tag === 'HEAD'
  ) {
    return true;
  }
  if (el.hasAttribute('hidden')) return true;
  if (el.getAttribute('aria-hidden') === 'true') return true;
  if (tag === 'INPUT' && (el as HTMLInputElement).type === 'hidden') return true;
  return false;
}

function findDisclosureToken(hidden: HTMLElement): HTMLElement | null {
  const prev = hidden.previousElementSibling;
  if (prev instanceof HTMLElement) {
    const token = prev.querySelector('a.token, [aria-expanded="false"]');
    if (token instanceof HTMLElement) return token;
    if (prev.matches('a.token, summary')) return prev;
  }
  const parent = hidden.parentElement;
  if (parent) {
    const token = parent.querySelector(':scope > div a.token, :scope > a.token, :scope > summary');
    if (token instanceof HTMLElement) return token;
  }
  return null;
}

function isCollapsed(node: HTMLElement): boolean {
  if (node.tagName === 'DETAILS' && !(node as HTMLDetailsElement).open) return true;
  try {
    const cs = node.ownerDocument.defaultView?.getComputedStyle(node);
    if (cs && (cs.display === 'none' || cs.visibility === 'hidden')) return true;
  } catch {
    /* ignore */
  }
  return node.classList.contains('height-container');
}

function openCollapsed(node: HTMLElement): void {
  if (node.tagName === 'DETAILS') {
    (node as HTMLDetailsElement).open = true;
  }
  const token = findDisclosureToken(node);
  if (token && token.tagName === 'SUMMARY') {
    const details = token.closest('details');
    if (details) (details as HTMLDetailsElement).open = true;
  } else if (token && !token.classList.contains('token-open')) {
    token.click();
    token.classList.add('token-open');
  }
  node.style.setProperty('display', 'block', 'important');
  node.style.setProperty('visibility', 'visible', 'important');
  node.style.setProperty('height', 'auto', 'important');
  node.style.setProperty('max-height', 'none', 'important');
  node.style.setProperty('overflow', 'visible', 'important');
}

export function expandCollapsedAround(marks: HTMLElement[]): void {
  for (const mark of marks) {
    let node: HTMLElement | null = mark.parentElement;
    while (node && node !== node.ownerDocument.body) {
      if (isCollapsed(node)) openCollapsed(node);
      node = node.parentElement;
    }
  }
}

function collectTextNodes(root: FindRoot): Text[] {
  const scope = queryScope(root);
  const nodes: Text[] = [];
  const walker = ownerDoc(root).createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      let el = node.parentElement;
      while (el) {
        if (isSkippedElement(el)) return NodeFilter.FILTER_REJECT;
        el = el.parentElement;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  return nodes;
}

type NodeSpan = { node: Text; from: number; to: number };

function posAt(spans: NodeSpan[], offset: number, forEnd: boolean): { node: Text; offset: number } | null {
  if (!spans.length) return null;
  for (let i = 0; i < spans.length; i++) {
    const span = spans[i];
    if (forEnd) {
      if (offset <= span.to && offset >= span.from) {
        if (offset === span.from && i > 0) {
          const prev = spans[i - 1];
          return { node: prev.node, offset: prev.to - prev.from };
        }
        return { node: span.node, offset: offset - span.from };
      }
    } else if (offset >= span.from && offset < span.to) {
      return { node: span.node, offset: offset - span.from };
    }
  }
  const last = spans[spans.length - 1];
  return { node: last.node, offset: last.to - last.from };
}

function overlayHit(spans: NodeSpan[], start: number, end: number, className: string): HTMLElement | null {
  const from = posAt(spans, start, false);
  const to = posAt(spans, end, true);
  if (!from || !to) return null;
  const doc = from.node.ownerDocument;
  const range = doc.createRange();
  try {
    range.setStart(from.node, from.offset);
    range.setEnd(to.node, to.offset);
  } catch {
    return null;
  }
  const anchor = (from.node.parentElement as HTMLElement | null)?.closest('.pdf-page');
  if (!(anchor instanceof HTMLElement)) return null;
  const pageRect = anchor.getBoundingClientRect();
  const clientRects = Array.from(range.getClientRects()).filter((r) => r.width >= 0.5 && r.height >= 0.5);
  if (!clientRects.length) return null;

  let minL = Infinity;
  let minT = Infinity;
  let maxR = -Infinity;
  let maxB = -Infinity;
  const boxes = clientRects.map((r) => {
    const padX = Math.max(2, r.width * 0.06);
    const padY = Math.max(3, r.height * 0.18);
    const left = r.left - pageRect.left - padX;
    const top = r.top - pageRect.top - padY;
    const width = r.width + padX * 2;
    const height = r.height + padY * 2;
    minL = Math.min(minL, left);
    minT = Math.min(minT, top);
    maxR = Math.max(maxR, left + width);
    maxB = Math.max(maxB, top + height);
    return { left, top, width, height };
  });

  const group = doc.createElement('div');
  group.className = `lhr-pdf-hl-group ${className}`;
  group.style.left = `${minL}px`;
  group.style.top = `${minT}px`;
  group.style.width = `${maxR - minL}px`;
  group.style.height = `${maxB - minT}px`;
  for (const box of boxes) {
    const hl = doc.createElement('div');
    hl.className = 'lhr-pdf-hl';
    hl.style.left = `${box.left - minL}px`;
    hl.style.top = `${box.top - minT}px`;
    hl.style.width = `${box.width}px`;
    hl.style.height = `${box.height}px`;
    group.appendChild(hl);
  }
  anchor.appendChild(group);
  return group;
}

function wrapSlice(node: Text, start: number, end: number, className: string): HTMLElement | null {
  const text = node.textContent || '';
  if (start < 0 || end > text.length || start >= end) return null;
  const doc = node.ownerDocument;
  if (!doc || !node.parentNode) return null;
  if (end < text.length) node.splitText(end);
  const match = start > 0 ? node.splitText(start) : node;
  const mark = doc.createElement('mark');
  mark.className = className;
  match.parentNode?.insertBefore(mark, match);
  mark.appendChild(match);
  return mark;
}

function yieldUi(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function paintFrame(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
}

import { hitsInText, textSlices, workerCountFor, type FindFlags, type TextHit } from './findMatch';

export type { FindFlags };

let findPool: Worker[] | null = null;
let findJobId = 0;

function findWorkers(): Worker[] {
  if (findPool) return findPool;
  const n = Math.max(1, (navigator.hardwareConcurrency || 8) - 1);
  findPool = Array.from(
    { length: n },
    () => new Worker(new URL('./findWorker.ts', import.meta.url), { type: 'module' }),
  );
  return findPool;
}

function searchText(
  text: string,
  query: string,
  flags: FindFlags,
  onActive?: (count: number) => void,
): Promise<TextHit[]> {
  const parts = workerCountFor(text.length);
  if (parts <= 1) {
    onActive?.(1);
    const hits = hitsInText(text, query, flags);
    onActive?.(0);
    return Promise.resolve(hits);
  }
  const pad = Math.min(4096, Math.max(query.length + 32, 128));
  const slices = textSlices(text.length, parts, pad);
  const pool = findWorkers();
  const id = ++findJobId;
  return new Promise((resolve) => {
    const hits: TextHit[] = [];
    let pending = slices.length;
    let settled = false;
    const inflight = new Map<Worker, number>();
    let active = 0;
    const bump = (worker: Worker, delta: number) => {
      const prev = inflight.get(worker) || 0;
      const next = prev + delta;
      inflight.set(worker, next);
      if (prev === 0 && next > 0) active += 1;
      else if (prev > 0 && next === 0) active -= 1;
      onActive?.(active);
    };
    const finish = (found: TextHit[]) => {
      if (settled) return;
      settled = true;
      for (const worker of pool) {
        worker.removeEventListener('message', onMessage);
        worker.removeEventListener('error', onError);
      }
      onActive?.(0);
      found.sort((a, b) => a.start - b.start);
      resolve(found.slice(0, 8000));
    };
    const onError = () => finish(hitsInText(text, query, flags));
    const onMessage = (event: MessageEvent<{ id: number; hits: TextHit[] }>) => {
      if (event.data.id !== id) return;
      bump(event.currentTarget as Worker, -1);
      hits.push(...event.data.hits);
      pending -= 1;
      if (pending > 0) return;
      finish(hits);
    };
    for (const worker of pool) {
      worker.addEventListener('message', onMessage);
      worker.addEventListener('error', onError);
    }
    slices.forEach((slice, index) => {
      const worker = pool[index % pool.length];
      bump(worker, 1);
      worker.postMessage({
        id,
        text: text.slice(slice.sliceFrom, slice.sliceTo),
        query,
        flags,
        from: slice.from,
        to: slice.to,
        sliceFrom: slice.sliceFrom,
      });
    });
  });
}

function spanIndexAt(spans: NodeSpan[], offset: number): number {
  let lo = 0;
  let hi = spans.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (spans[mid].to <= offset) lo = mid + 1;
    else if (spans[mid].from > offset) hi = mid - 1;
    else return mid;
  }
  return Math.min(lo, spans.length - 1);
}

async function wrapMatches(
  root: FindRoot,
  query: string,
  layer: FindLayer,
  onCount?: (n: number) => void,
  cancelled?: () => boolean,
  flags: FindFlags = {},
  onParallel?: (parallel: boolean) => void,
  onActive?: (count: number) => void,
  byteSize = 0,
): Promise<HTMLElement[]> {
  const q = query.trim();
  if (!q) return [];
  if (byteSize >= 512 * 1024) {
    onParallel?.(true);
    await paintFrame();
  }
  const nodes: Text[] = [];
  const originals: string[] = [];
  const walker = ownerDoc(root).createTreeWalker(queryScope(root), NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = (node as Text).parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      const tag = parent.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'TEXTAREA') {
        return NodeFilter.FILTER_REJECT;
      }
      if (parent.closest('script, style, noscript, textarea')) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let chars = 0;
  let lastCollect = performance.now();
  let toldParallel = byteSize >= 512 * 1024;
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const text = node.textContent || '';
    nodes.push(node);
    originals.push(text);
    chars += text.length;
    if (!toldParallel && (chars >= 80_000 || nodes.length >= 4000)) {
      toldParallel = true;
      onParallel?.(true);
      await paintFrame();
      lastCollect = performance.now();
    } else if (performance.now() - lastCollect > 24) {
      await yieldUi();
      lastCollect = performance.now();
    }
  }
  if (nodes.length === 0) return [];
  const joined = originals.join('');
  onParallel?.(workerCountFor(joined.length) > 1);
  const hits = await searchText(joined, q, flags, onActive);
  if (cancelled?.()) return [];
  if (hits.length === 0) return [];

  const spans: NodeSpan[] = [];
  let pos = 0;
  for (let i = 0; i < nodes.length; i++) {
    const len = originals[i].length;
    spans.push({ node: nodes[i], from: pos, to: pos + len });
    pos += len;
  }

  const markClass = LAYERS[layer].mark;
  const marks: HTMLElement[] = [];
  const pdf = isPdfRoot(root);
  let lastYield = performance.now();
  for (let h = hits.length - 1; h >= 0; h--) {
    if (cancelled?.()) return [];
    onCount?.(h + 1);
    const { start, end } = hits[h];
    if (pdf) {
      const group = overlayHit(spans, start, end, markClass);
      if (group) marks.unshift(group);
    } else {
      const created: HTMLElement[] = [];
      const first = spanIndexAt(spans, start);
      let last = first;
      while (last < spans.length && spans[last].from < end) last += 1;
      for (let s = last - 1; s >= first; s--) {
        const span = spans[s];
        if (span.to <= start || span.from >= end) continue;
        const localStart = Math.max(0, start - span.from);
        const localEnd = Math.min(span.to, end) - span.from;
        const mark = wrapSlice(span.node, localStart, localEnd, markClass);
        if (mark) created.push(mark);
      }
      created.reverse();
      marks.unshift(...created);
    }
    if (performance.now() - lastYield > 24) {
      await yieldUi();
      lastYield = performance.now();
    }
  }
  return marks;
}

async function wrapPerNode(
  nodes: Text[],
  needle: string,
  matchLen: number,
  markClass: string,
  onCount?: (n: number) => void,
  cancelled?: () => boolean,
  pdf = false,
): Promise<HTMLElement[]> {
  const marks: HTMLElement[] = [];
  let found = 0;
  for (let n = nodes.length - 1; n >= 0; n--) {
    if (cancelled?.()) return [];
    const node = nodes[n];
    const lower = (node.textContent || '').toLowerCase();
    const localHits: number[] = [];
    let idx = lower.indexOf(needle);
    while (idx !== -1) {
      localHits.push(idx);
      found += 1;
      onCount?.(found);
      idx = lower.indexOf(needle, idx + matchLen);
    }
    for (let i = localHits.length - 1; i >= 0; i--) {
      if (pdf) {
        const span: NodeSpan = { node, from: 0, to: (node.textContent || '').length };
        const group = overlayHit([span], localHits[i], localHits[i] + matchLen, markClass);
        if (group) marks.unshift(group);
      } else {
        const mark = wrapSlice(node, localHits[i], localHits[i] + matchLen, markClass);
        if (mark) marks.unshift(mark);
      }
    }
    if (found % 8 === 0) await yieldUi();
  }
  return marks;
}

export async function applyFinds(
  root: FindRoot,
  listQuery: string,
  pageQuery: string,
  onProgress?: (layer: FindLayer, count: number) => void,
  cancelled?: () => boolean,
  options?: { list?: FindFlags; page?: FindFlags; byteSize?: number },
  onParallel?: (layer: FindLayer, parallel: boolean) => void,
  onActive?: (layer: FindLayer, count: number) => void,
): Promise<{ list: HTMLElement[]; page: HTMLElement[] }> {
  injectStyle(root);
  clearFind(root);
  const listQ = listQuery.trim();
  const pageQ = pageQuery.trim();
  const listFlags = options?.list ?? {};
  const pageFlags = options?.page ?? {};
  const sameQuery =
    Boolean(listQ) &&
    Boolean(pageQ) &&
    listQ === pageQ &&
    Boolean(listFlags.regex) === Boolean(pageFlags.regex) &&
    Boolean(listFlags.matchCase) === Boolean(pageFlags.matchCase) &&
    Boolean(listFlags.wholeWord) === Boolean(pageFlags.wholeWord);
  if (sameQuery) {
    const marks = await wrapMatches(root, listQ, 'list', (n) => {
      onProgress?.('list', n);
      onProgress?.('page', n);
    }, cancelled, listFlags, (parallel) => {
      onParallel?.('list', parallel);
      onParallel?.('page', parallel);
    }, (count) => {
      onActive?.('list', count);
      onActive?.('page', count);
    }, options?.byteSize ?? 0);
    for (const mark of marks) mark.classList.add(LAYERS.page.mark);
    expandCollapsedAround(marks);
    return { list: marks, page: marks };
  }
  const list = await wrapMatches(
    root,
    listQ,
    'list',
    (n) => onProgress?.('list', n),
    cancelled,
    listFlags,
    (parallel) => onParallel?.('list', parallel),
    (count) => onActive?.('list', count),
    options?.byteSize ?? 0,
  );
  const page = await wrapMatches(
    root,
    pageQ,
    'page',
    (n) => onProgress?.('page', n),
    cancelled,
    pageFlags,
    (parallel) => onParallel?.('page', parallel),
    (count) => onActive?.('page', count),
    options?.byteSize ?? 0,
  );
  expandCollapsedAround([...list, ...page]);
  return { list, page };
}

export function reveal(
  marks: HTMLElement[],
  index: number,
  layer: FindLayer = 'page',
  scroll = true,
): number {
  if (marks.length === 0) return 0;
  const i = ((index % marks.length) + marks.length) % marks.length;
  const currentClass = LAYERS[layer].current;
  for (const mark of marks) mark.classList.remove(currentClass);
  const current = marks[i];
  if (!current.isConnected) return i;
  current.classList.add(currentClass);
  expandCollapsedAround([current]);
  if (scroll) current.scrollIntoView({ block: 'center', inline: 'nearest' });
  return i;
}
