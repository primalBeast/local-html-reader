export type OutlineNode = {
  title?: string;
  dest?: string | unknown[] | null;
  items?: OutlineNode[];
};

export type TocRow = {
  id: number;
  title: string;
  depth: number;
  page: number | null;
  label: string;
  key: number | null;
  dest: string | unknown[] | null;
};

export type PageSpan = { pageNumber: number; top: number; bottom: number };

/** PDF destination arrays store the vertical spot in different slots. */
export function destTop(dest: unknown[]): number | null {
  const mode = dest[1];
  const name =
    mode && typeof mode === 'object' && mode !== null && 'name' in mode
      ? String((mode as { name: unknown }).name)
      : '';
  const slot = name === 'XYZ' ? dest[3] : name === 'FitH' || name === 'FitBH' ? dest[2] : name === 'FitR' ? dest[5] : null;
  return typeof slot === 'number' && Number.isFinite(slot) ? slot : null;
}

/** 0 at the top of the page, 1 at the bottom. */
export function topFraction(view: number[], top: number | null): number {
  if (top === null || view.length < 4) return 0;
  const height = view[3] - view[1];
  if (!(height > 0)) return 0;
  return Math.min(1, Math.max(0, (view[3] - top) / height));
}

export function contentKey(pageIndex: number, fraction: number): number {
  return pageIndex + Math.min(1, Math.max(0, fraction));
}

/** Where the middle of the PDF pane sits, as a page index plus a fraction. */
export function readingKeyFromPages(mid: number, pages: PageSpan[]): number | null {
  if (!pages.length) return null;
  const ordered = [...pages].sort((a, b) => a.pageNumber - b.pageNumber);
  for (const page of ordered) {
    if (mid < page.top || mid >= page.bottom) continue;
    const span = page.bottom - page.top;
    const fraction = span > 0 ? (mid - page.top) / span : 0;
    return contentKey(page.pageNumber - 1, fraction);
  }
  if (mid < ordered[0].top) return ordered[0].pageNumber - 1;
  return ordered[ordered.length - 1].pageNumber;
}

export async function buildToc(
  nodes: OutlineNode[],
  resolve: (dest: string | unknown[] | null) => Promise<{ page: number; fraction: number } | null>,
  labelFor: (page: number) => string,
): Promise<TocRow[]> {
  const rows: TocRow[] = [];
  async function walk(list: OutlineNode[], depth: number) {
    for (const node of list) {
      const title = (node.title || '').replace(/\s+/g, ' ').trim();
      const dest = node.dest ?? null;
      const spot = dest ? await resolve(dest) : null;
      if (title) {
        rows.push({
          id: rows.length,
          title,
          depth,
          page: spot?.page ?? null,
          label: spot ? labelFor(spot.page) : '',
          key: spot ? contentKey(spot.page - 1, spot.fraction) : null,
          dest,
        });
      }
      if (node.items?.length) await walk(node.items, depth + (title ? 1 : 0));
    }
  }
  await walk(nodes, 0);
  let nextKey: number | null = null;
  for (let i = rows.length - 1; i >= 0; i--) {
    if (rows[i].key === null && nextKey !== null) rows[i].key = nextKey;
    else if (rows[i].key !== null) nextKey = rows[i].key;
  }
  return rows;
}
