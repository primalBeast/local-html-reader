import { describe, expect, it } from 'vitest';
import { indexMarkY } from './sideIndex';

describe('indexMarkY', () => {
  const marks = [
    { content: 0, index: 10 },
    { content: 100, index: 30 },
    { content: 300, index: 80 },
  ];

  it('uses the first index row above the first section', () => {
    expect(indexMarkY(marks, -20)).toBe(10);
  });

  it('sits halfway between two index rows when the midpoint is halfway between those sections', () => {
    expect(indexMarkY(marks, 50)).toBe(20);
    expect(indexMarkY(marks, 200)).toBe(55);
  });

  it('uses the last index row below the last section', () => {
    expect(indexMarkY(marks, 900)).toBe(80);
  });
});
