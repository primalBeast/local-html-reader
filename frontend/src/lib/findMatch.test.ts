import { describe, expect, it } from 'vitest';
import { hitsInText, textSlices } from './findMatch';

describe('textSlices', () => {
  it('covers the whole string and overlaps the cuts', () => {
    const slices = textSlices(1000, 7, 10);
    expect(slices[0].from).toBe(0);
    expect(slices[slices.length - 1].to).toBe(1000);
    for (let i = 1; i < slices.length; i++) {
      expect(slices[i].from).toBe(slices[i - 1].to);
      expect(slices[i].sliceFrom).toBeLessThan(slices[i].from);
    }
  });
});

describe('hitsInText', () => {
  it('finds a literal inside one slice the way workers stitch offsets', () => {
    const text = `${'a'.repeat(100)}65C0138E${'b'.repeat(100)}`;
    const slices = textSlices(text.length, 4, 8);
    const hits = slices.flatMap((slice) =>
      hitsInText(text.slice(slice.sliceFrom, slice.sliceTo), '65C0138E', {}).flatMap((hit) => {
        const start = hit.start + slice.sliceFrom;
        return start >= slice.from && start < slice.to ? [{ start, end: hit.end + slice.sliceFrom }] : [];
      }),
    );
    expect(hits).toEqual([{ start: 100, end: 108 }]);
  });
});
