import type { TreeNode } from './api';

export type DocKind = 'all' | 'html' | 'md' | 'pdf' | 'office' | 'text';

const HTML_EXT = new Set(['html', 'htm', 'xhtml']);
const MD_EXT = new Set(['md', 'markdown']);
const PDF_EXT = new Set(['pdf']);
const OFFICE_EXT = new Set([
  'docx',
  'dotx',
  'xlsx',
  'xlsm',
  'pptx',
  'odt',
  'ods',
  'odp',
  'rtf',
  'epub',
  'csv',
  'tsv',
]);
const TEXT_EXT = new Set(['txt', 'text', 'log', 'json', 'xml', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'ipynb']);

export function extensionOf(name: string): string {
  const base = (name || '').split(/[/\\]/).pop() || '';
  const dot = base.lastIndexOf('.');
  if (dot <= 0) return '';
  return base.slice(dot + 1).toLowerCase();
}

export function kindOf(name: string): Exclude<DocKind, 'all'> | 'other' {
  const ext = extensionOf(name);
  if (HTML_EXT.has(ext)) return 'html';
  if (MD_EXT.has(ext)) return 'md';
  if (PDF_EXT.has(ext)) return 'pdf';
  if (OFFICE_EXT.has(ext)) return 'office';
  if (TEXT_EXT.has(ext)) return 'text';
  return 'other';
}

export function isHtmlName(name: string): boolean {
  return kindOf(name) === 'html';
}

export function filterTree(nodes: TreeNode[], kind: DocKind): TreeNode[] {
  if (kind === 'all') return nodes;
  const out: TreeNode[] = [];
  for (const node of nodes) {
    if (node.kind === 'file') {
      if (kindOf(node.name) === kind) out.push(node);
      continue;
    }
    const children = filterTree(node.children || [], kind);
    if (children.length) out.push({ ...node, children });
  }
  return out;
}

export function flatFiles(nodes: TreeNode[]): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (list: TreeNode[]) => {
    for (const node of list) {
      if (node.kind === 'file') out.push(node);
      else if (node.children?.length) walk(node.children);
    }
  };
  walk(nodes);
  return out;
}

export function readingStats(text: string): { words: number; minutes: number } {
  const words = (text || '').trim().match(/\S+/g)?.length ?? 0;
  if (!words) return { words: 0, minutes: 0 };
  return { words, minutes: Math.max(1, Math.round(words / 220)) };
}

const CSP_BASE =
  "default-src 'none'; style-src 'unsafe-inline'; font-src 'self' data:; media-src 'self' data: blob:; " +
  "connect-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'self'; " +
  "form-action 'none'; frame-ancestors 'self'; script-src 'none'; ";

export function lockdownHtml(html: string, generated: boolean): string {
  const images = generated ? "img-src 'self' data: blob: https:" : "img-src 'self' data: blob:";
  const meta = `<meta http-equiv="Content-Security-Policy" content="${CSP_BASE}${images}">`;
  if (/<head[^>]*>/i.test(html)) {
    return html.replace(/<head([^>]*)>/i, (open) => `${open}${meta}`);
  }
  return `<!doctype html><head>${meta}</head>${html}`;
}

export function readerChromeCss(theme: 'paper' | 'sepia' | 'night', scale: number): string {
  const size = Math.min(1.6, Math.max(0.85, scale));
  const rules = [`html { font-size: ${Math.round(size * 100)}% !important; }`];
  if (theme === 'sepia') {
    rules.push(
      'html, body { background: #f4ecd8 !important; color: #3b2f1e !important; }',
      'a { color: #8a4b08 !important; }',
    );
  } else if (theme === 'night') {
    rules.push(
      'html { filter: invert(1) hue-rotate(180deg); background: #111 !important; }',
      'img, video, picture, canvas, svg, iframe { filter: invert(1) hue-rotate(180deg); }',
    );
  }
  return rules.join('\n');
}
