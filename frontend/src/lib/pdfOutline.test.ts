import { describe, expect, it } from 'vitest';
import { buildToc, contentKey, destTop, readingKeyFromPages, topFraction } from './pdfOutline';

describe('destTop', () => {
  it('reads the vertical spot from the usual destination kinds', () => {
    expect(destTop([{}, { name: 'XYZ' }, 0, 720, 0])).toBe(720);
    expect(destTop([{}, { name: 'FitH' }, 400])).toBe(400);
    expect(destTop([{}, { name: 'FitR' }, 0, 10, 100, 500])).toBe(500);
    expect(destTop([{}, { name: 'Fit' }])).toBeNull();
  });
});

describe('topFraction', () => {
  it('is 0 at the top of the page and 1 at the bottom', () => {
    expect(topFraction([0, 0, 600, 800], 800)).toBe(0);
    expect(topFraction([0, 0, 600, 800], 0)).toBe(1);
    expect(topFraction([0, 0, 600, 800], 400)).toBe(0.5);
  });
});

describe('readingKeyFromPages', () => {
  const pages = [
    { pageNumber: 1, top: 0, bottom: 100 },
    { pageNumber: 2, top: 120, bottom: 220 },
  ];

  it('uses the page under the middle of the pane', () => {
    expect(readingKeyFromPages(50, pages)).toBe(contentKey(0, 0.5));
    expect(readingKeyFromPages(170, pages)).toBe(contentKey(1, 0.5));
  });

  it('stays on the first page above the document and the last page below it', () => {
    expect(readingKeyFromPages(-10, pages)).toBe(0);
    expect(readingKeyFromPages(400, pages)).toBe(2);
  });
});

describe('buildToc', () => {
  it('keeps nested sections and fills a heading from the next page', async () => {
    const rows = await buildToc(
      [
        {
          title: 'Guide',
          dest: null,
          items: [{ title: 'Start', dest: ['start'] }],
        },
      ],
      async (dest) => (dest ? { page: 3, fraction: 0 } : null),
      (page) => String(page),
    );
    expect(rows.map((row) => [row.title, row.depth, row.page, row.key])).toEqual([
      ['Guide', 0, null, 2],
      ['Start', 1, 3, 2],
    ]);
  });
});
