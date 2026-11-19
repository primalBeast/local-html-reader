import { describe, expect, it } from 'vitest';
import { cssPixelsFromVisual, indexMarkY, visiblePaneCenter } from './sideIndex';

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

describe('cssPixelsFromVisual', () => {
  it('returns the same value at 100%', () => {
    expect(cssPixelsFromVisual(40, 200, 200)).toBe(40);
    expect(cssPixelsFromVisual(-12, 80, 80)).toBe(-12);
  });

  it('doubles at 50%', () => {
    expect(cssPixelsFromVisual(40, 100, 200)).toBe(80);
    expect(cssPixelsFromVisual(-25, 50, 100)).toBe(-50);
  });

  it('divides by 1.5 at 150%', () => {
    expect(cssPixelsFromVisual(30, 150, 100)).toBe(20);
    expect(cssPixelsFromVisual(-15, 300, 200)).toBe(-10);
  });

  it('returns the input when css height is 0 or NaN', () => {
    expect(cssPixelsFromVisual(40, 100, 0)).toBe(40);
    expect(cssPixelsFromVisual(-8, 100, 0)).toBe(-8);
    expect(cssPixelsFromVisual(40, 100, Number.NaN)).toBe(40);
  });

  it('returns the input when the scale is not a positive finite number', () => {
    expect(cssPixelsFromVisual(40, 0, 200)).toBe(40);
    expect(cssPixelsFromVisual(40, -10, 200)).toBe(40);
    expect(cssPixelsFromVisual(40, Number.NaN, 200)).toBe(40);
    expect(cssPixelsFromVisual(40, Infinity, 200)).toBe(40);
    expect(cssPixelsFromVisual(40, 100, -5)).toBe(40);
    expect(cssPixelsFromVisual(40, 100, Infinity)).toBe(40);
  });
});

describe('visiblePaneCenter', () => {
  it('uses the box center when the pane sits fully in the viewport', () => {
    expect(visiblePaneCenter({ top: 20, height: 200, bottom: 220 }, 800)).toBe(120);
  });

  it('uses the visible middle when a sticky 100vh pane is 1.5× the viewport', () => {
    // 150% zoom: height 100vh paints 918px in a 612px viewport. Box center is 459, 153px below the visible center.
    const pane = { top: 0, height: 918, bottom: 918 };
    expect(visiblePaneCenter(pane, 612)).toBe(306);
    expect(pane.top + pane.height / 2 - visiblePaneCenter(pane, 612)).toBe(153);
  });

  it('clips a pane that starts below a header and runs past the viewport', () => {
    expect(visiblePaneCenter({ top: 48, height: 1200, bottom: 1248 }, 800)).toBe(424);
  });

  it('clips the top when the pane starts above the viewport', () => {
    expect(visiblePaneCenter({ top: -100, height: 400, bottom: 300 }, 800)).toBe(150);
  });

  it('uses the viewport middle when the pane overhangs both edges', () => {
    expect(visiblePaneCenter({ top: -40, height: 1000, bottom: 960 }, 800)).toBe(400);
  });

  it('keeps a 4px slice on the visible center', () => {
    expect(visiblePaneCenter({ top: -20, height: 24, bottom: 4 }, 800)).toBe(2);
  });

  it('falls back to the box center when the visible slice is under 4px', () => {
    expect(visiblePaneCenter({ top: -20, height: 23, bottom: 3 }, 500)).toBe(-8.5);
    expect(visiblePaneCenter({ top: 900, height: 200, bottom: 1100 }, 800)).toBe(1000);
  });
});
