export type FindLayer = 'list' | 'page';
export type FindRoot = Document | HTMLElement;

const STYLE_ID = 'lhr-find-style';

const LAYERS: Record<FindLayer, { mark: string; current: string }> = {
  list: { mark: 'lhr-find-list', current: 'lhr-find-list-current' },
  page: { mark: 'lhr-find-page', current: 'lhr-find-page-current' },
};

function ownerDoc(root: FindRoot): Document {
  return root instanceof Document ? root : root.ownerDocument;
}

function queryScope(root: FindRoot): ParentNode {
  const doc = root as Document & { body?: HTMLElement };
  if (root instanceof Document || (doc && doc.nodeType === 9 && doc.body)) {
    return doc.body ?? doc.documentElement ?? root;
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

async function wrapMatches(
  root: FindRoot,
  query: string,
  layer: FindLayer,
  onCount?: (n: number) => void,
  cancelled?: () => boolean,
): Promise<HTMLElement[]> {
  const q = query.trim();
  if (!q) return [];
  const needle = q.toLowerCase();
  const nodes = collectTextNodes(root);
  if (nodes.length === 0) return [];

  const originals = nodes.map((n) => n.textContent || '');
  const joined = originals.join('');
  const haystack = joined.toLowerCase();
  if (joined.length !== haystack.length) {
    return wrapPerNode(nodes, needle, q.length, LAYERS[layer].mark, onCount, cancelled, isPdfRoot(root));
  }

  const hits: number[] = [];
  let idx = haystack.indexOf(needle);
  while (idx !== -1) {
    if (cancelled?.()) return [];
    hits.push(idx);
    onCount?.(hits.length);
    idx = haystack.indexOf(needle, idx + needle.length);
    if (hits.length % 8 === 0) await yieldUi();
  }
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
  const matchLen = needle.length;
  const pdf = isPdfRoot(root);
  for (let h = hits.length - 1; h >= 0; h--) {
    const start = hits[h];
    const end = start + matchLen;
    if (pdf) {
      const group = overlayHit(spans, start, end, markClass);
      if (group) marks.unshift(group);
      continue;
    }
    const created: HTMLElement[] = [];
    for (let s = spans.length - 1; s >= 0; s--) {
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
): Promise<{ list: HTMLElement[]; page: HTMLElement[] }> {
  injectStyle(root);
  clearFind(root);
  const listQ = listQuery.trim();
  const pageQ = pageQuery.trim();
  if (listQ && pageQ && listQ.toLowerCase() === pageQ.toLowerCase()) {
    const marks = await wrapMatches(root, listQ, 'list', (n) => {
      onProgress?.('list', n);
      onProgress?.('page', n);
    }, cancelled);
    for (const mark of marks) mark.classList.add(LAYERS.page.mark);
    expandCollapsedAround(marks);
    return { list: marks, page: marks };
  }
  const list = await wrapMatches(root, listQ, 'list', (n) => onProgress?.('list', n), cancelled);
  const page = await wrapMatches(root, pageQ, 'page', (n) => onProgress?.('page', n), cancelled);
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
