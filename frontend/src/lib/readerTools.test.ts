import { describe, expect, it } from 'vitest';
import type { TreeNode } from './api';
import { filterTree, kindOf, lockdownHtml, readingStats } from './readerTools';

const tree: TreeNode[] = [
  {
    name: 'guides',
    rel: 'guides',
    kind: 'dir',
    root_id: 'a',
    root_path: '/docs',
    children: [
      { name: 'intro.htm', rel: 'guides/intro.htm', kind: 'file', root_id: 'a', root_path: '/docs' },
      { name: 'notes.md', rel: 'guides/notes.md', kind: 'file', root_id: 'a', root_path: '/docs' },
    ],
  },
  { name: 'book.pdf', rel: 'book.pdf', kind: 'file', root_id: 'a', root_path: '/docs' },
];

describe('reader tools', () => {
  it('classifies extensions', () => {
    expect(kindOf('Page.HTML')).toBe('html');
    expect(kindOf('notes.md')).toBe('md');
    expect(kindOf('book.pdf')).toBe('pdf');
    expect(kindOf('sheet.xlsx')).toBe('office');
    expect(kindOf('plain.txt')).toBe('text');
  });

  it('filters a tree and drops empty folders', () => {
    const html = filterTree(tree, 'html');
    expect(html).toHaveLength(1);
    expect(html[0].children?.map((node) => node.name)).toEqual(['intro.htm']);
    expect(filterTree(tree, 'pdf').map((node) => node.name)).toEqual(['book.pdf']);
  });

  it('estimates reading time', () => {
    expect(readingStats('')).toEqual({ words: 0, minutes: 0 });
    expect(readingStats('one two three')).toEqual({ words: 3, minutes: 1 });
  });

  it('injects a strict content security policy', () => {
    const locked = lockdownHtml('<html><head><title>t</title></head><body>Hi</body></html>', false);
    expect(locked).toContain("script-src 'none'");
    expect(locked).toContain("connect-src 'none'");
    expect(locked).not.toContain('https:');
    const generated = lockdownHtml('<html><body>Hi</body></html>', true);
    expect(generated).toContain('https:');
  });
});
