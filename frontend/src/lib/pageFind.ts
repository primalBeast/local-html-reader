export type FindLayer = 'list' | 'page';

const STYLE_ID = 'lhr-find-style';

const LAYERS: Record<FindLayer, { mark: string; current: string }> = {
  list: { mark: 'lhr-find-list', current: 'lhr-find-list-current' },
  page: { mark: 'lhr-find-page', current: 'lhr-find-page-current' },
};

function injectStyle(doc: Document): void {
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
    'mark.lhr-find-list-current.lhr-find-page-current{background:#ff9f1a;color:#111;}';
  (doc.head || doc.documentElement).appendChild(style);
}

function unwrapMarks(doc: Document, selector: string): void {
  const marks = Array.from(doc.querySelectorAll(selector));
  for (const el of marks) {
    const parent = el.parentNode;
    if (!parent) continue;
    parent.replaceChild(doc.createTextNode(el.textContent || ''), el);
    parent.normalize();
  }
}

export function clearFind(doc: Document, layer?: FindLayer): void {
  if (layer) {
    unwrapMarks(doc, `mark.${LAYERS[layer].mark}`);
    return;
  }
  unwrapMarks(doc, 'mark.lhr-find-list, mark.lhr-find-page');
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

function collectTextNodes(doc: Document): Text[] {
  if (!doc.body) return [];
  const nodes: Text[] = [];
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, {
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

function wrapMatches(doc: Document, query: string, layer: FindLayer): HTMLElement[] {
  const q = query.trim();
  if (!q || !doc.body) return [];
  const needle = q.toLowerCase();
  const nodes = collectTextNodes(doc);
  if (nodes.length === 0) return [];

  const originals = nodes.map((n) => n.textContent || '');
  const joined = originals.join('');
  const haystack = joined.toLowerCase();
  if (joined.length !== haystack.length) {
    return wrapPerNode(nodes, needle, q.length, LAYERS[layer].mark);
  }

  const hits: number[] = [];
  let idx = haystack.indexOf(needle);
  while (idx !== -1) {
    hits.push(idx);
    idx = haystack.indexOf(needle, idx + needle.length);
  }
  if (hits.length === 0) return [];

  const spans: Array<{ node: Text; from: number; to: number }> = [];
  let pos = 0;
  for (let i = 0; i < nodes.length; i++) {
    const len = originals[i].length;
    spans.push({ node: nodes[i], from: pos, to: pos + len });
    pos += len;
  }

  const markClass = LAYERS[layer].mark;
  const marks: HTMLElement[] = [];
  const matchLen = needle.length;
  for (let h = hits.length - 1; h >= 0; h--) {
    const start = hits[h];
    const end = start + matchLen;
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

function wrapPerNode(nodes: Text[], needle: string, matchLen: number, markClass: string): HTMLElement[] {
  const marks: HTMLElement[] = [];
  for (let n = nodes.length - 1; n >= 0; n--) {
    const node = nodes[n];
    const lower = (node.textContent || '').toLowerCase();
    const localHits: number[] = [];
    let idx = lower.indexOf(needle);
    while (idx !== -1) {
      localHits.push(idx);
      idx = lower.indexOf(needle, idx + matchLen);
    }
    for (let i = localHits.length - 1; i >= 0; i--) {
      const mark = wrapSlice(node, localHits[i], localHits[i] + matchLen, markClass);
      if (mark) marks.unshift(mark);
    }
  }
  return marks;
}

export function applyFinds(
  doc: Document,
  listQuery: string,
  pageQuery: string,
): { list: HTMLElement[]; page: HTMLElement[] } {
  injectStyle(doc);
  clearFind(doc);
  const listQ = listQuery.trim();
  const pageQ = pageQuery.trim();
  if (listQ && pageQ && listQ.toLowerCase() === pageQ.toLowerCase()) {
    const marks = wrapMatches(doc, listQ, 'list');
    for (const mark of marks) mark.classList.add(LAYERS.page.mark);
    expandCollapsedAround(marks);
    return { list: marks, page: marks };
  }
  const list = wrapMatches(doc, listQ, 'list');
  const page = wrapMatches(doc, pageQ, 'page');
  expandCollapsedAround([...list, ...page]);
  return { list, page };
}

export function findInDocument(doc: Document, query: string, layer: FindLayer = 'page'): HTMLElement[] {
  injectStyle(doc);
  clearFind(doc, layer);
  return wrapMatches(doc, query, layer);
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
