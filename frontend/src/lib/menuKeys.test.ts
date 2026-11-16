import { describe, expect, it } from 'vitest';
import { nextMenuIndex } from './menuKeys';

describe('nextMenuIndex', () => {
  it('starts at the end when moving up from nothing', () => {
    expect(nextMenuIndex(-1, 4, -1)).toBe(3);
    expect(nextMenuIndex(-1, 4, 1)).toBe(0);
  });

  it('wraps', () => {
    expect(nextMenuIndex(3, 4, 1)).toBe(0);
    expect(nextMenuIndex(0, 4, -1)).toBe(3);
  });
});
