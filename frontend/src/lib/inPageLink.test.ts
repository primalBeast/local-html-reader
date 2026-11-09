import { describe, expect, it } from 'vitest';
import { hashForSameFile } from './inPageLink';

const page = 'http://127.0.0.1:8766/view/root/guide/index.html';

describe('hashForSameFile', () => {
  it('keeps a fragment link on the open file', () => {
    expect(hashForSameFile('#setup', `${page.replace(/index\.html$/, '')}#setup`, page)).toBe('#setup');
    expect(hashForSameFile('./#setup', page, page)).toBe('#setup');
  });

  it('keeps a same-file link that names the file', () => {
    expect(hashForSameFile('index.html#setup', `${page}#setup`, page)).toBe('#setup');
    expect(hashForSameFile('Index.HTML#Setup', `${page.replace('index.html', 'Index.HTML')}#Setup`, page)).toBe('#Setup');
  });

  it('leaves links to another file alone', () => {
    expect(hashForSameFile('other.html#setup', page.replace('index.html', 'other.html') + '#setup', page)).toBeNull();
    expect(hashForSameFile('https://example.com/#x', 'https://example.com/#x', page)).toBeNull();
    expect(hashForSameFile('index.html', page, page)).toBeNull();
  });
});
