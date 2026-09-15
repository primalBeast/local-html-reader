const WORD_CHAR = /[\p{L}\p{N}_]/u;

function isWordChar(ch: string | undefined): boolean {
  return Boolean(ch) && WORD_CHAR.test(ch as string);
}

function caretAtPoint(doc: Document, x: number, y: number): { node: Text; offset: number } | null {
  const anyDoc = doc as Document & {
    caretPositionFromPoint?: (cx: number, cy: number) => { offsetNode: Node; offset: number } | null;
    caretRangeFromPoint?: (cx: number, cy: number) => Range | null;
  };
  if (typeof anyDoc.caretPositionFromPoint === 'function') {
    const pos = anyDoc.caretPositionFromPoint(x, y);
    if (pos?.offsetNode?.nodeType === Node.TEXT_NODE) {
      return { node: pos.offsetNode as Text, offset: pos.offset };
    }
  }
  if (typeof anyDoc.caretRangeFromPoint === 'function') {
    const range = anyDoc.caretRangeFromPoint(x, y);
    if (range?.startContainer?.nodeType === Node.TEXT_NODE) {
      return { node: range.startContainer as Text, offset: range.startOffset };
    }
  }
  return null;
}

function walkText(from: Node, dir: -1 | 1): Text | null {
  const next = (n: Node) => (dir < 0 ? n.previousSibling : n.nextSibling);
  const child = (n: Node) => (dir < 0 ? n.lastChild : n.firstChild);
  let node: Node | null = from;
  while (node) {
    const sib = next(node);
    if (sib) {
      node = sib;
      while (child(node)) node = child(node) as Node;
      if (node.nodeType === Node.TEXT_NODE && (node.textContent || '').length) return node as Text;
      continue;
    }
    node = node.parentNode;
    if (!node || node.nodeType === Node.DOCUMENT_NODE) break;
  }
  return null;
}

export function selectedTextIn(root: Node | null): string {
  if (!root) return '';
  const doc = root.nodeType === 9 ? (root as Document) : root.ownerDocument;
  const sel = doc?.getSelection?.();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return '';
  const node = sel.anchorNode;
  if (!node) return '';
  const el = node instanceof Element ? node : node.parentElement;
  if (!el || !root.contains(el)) return '';
  return sel.toString();
}

export function wordAtPoint(doc: Document, clientX: number, clientY: number): string {
  const caret = caretAtPoint(doc, clientX, clientY);
  if (!caret) {
    const el = doc.elementFromPoint(clientX, clientY);
    const raw = (el?.textContent || '').trim();
    const match = raw.match(/[\p{L}\p{N}_]+/u);
    return match ? match[0] : '';
  }
  let prefix = '';
  let node: Text | null = walkText(caret.node, -1);
  while (node && prefix.length < 80) {
    prefix = (node.textContent || '') + prefix;
    node = walkText(node, -1);
  }
  let suffix = '';
  node = walkText(caret.node, 1);
  while (node && suffix.length < 80) {
    suffix += node.textContent || '';
    node = walkText(node, 1);
  }
  const combined = prefix + (caret.node.textContent || '') + suffix;
  const index = Math.min(combined.length, Math.max(0, prefix.length + caret.offset));
  let start = index;
  let end = index;
  while (start > 0 && isWordChar(combined[start - 1])) start -= 1;
  while (end < combined.length && isWordChar(combined[end])) end += 1;
  return combined.slice(start, end);
}

export async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
}

export async function copyImageToClipboard(img: HTMLImageElement): Promise<void> {
  const blob = await (await fetch(img.src)).blob();
  await navigator.clipboard.write([new ClipboardItem({ [blob.type || 'image/png']: blob })]);
}
