import { describe, expect, it } from 'vitest';
import {
  applyWheelZoom,
  clampDocZoom,
  pdfWheelOrigin,
  scrollAfterZoom,
  wheelZoomDelta,
  zoomAfterOpen,
  zoomFromDrag,
  zoomFromKey,
  zoomKeyCommand,
  zoomPercent,
  zoomReadout,
} from './docZoom';

describe('clampDocZoom', () => {
  it('snaps to an integer percent inside 50%–200%', () => {
    expect(clampDocZoom(1)).toBe(1);
    expect(clampDocZoom(1.234)).toBe(1.23);
    expect(clampDocZoom(1.235)).toBe(1.24);
    expect(clampDocZoom(1.5)).toBe(1.5);
    expect(clampDocZoom(0.1)).toBe(0.5);
    expect(clampDocZoom(3)).toBe(2);
    expect(clampDocZoom(Number.NaN)).toBe(1);
    expect(clampDocZoom(Number.POSITIVE_INFINITY)).toBe(1);
  });
});

describe('zoomAfterOpen', () => {
  it('resets a user open, including the same document, and keeps a reload', () => {
    expect(zoomAfterOpen('user', 1.5)).toBe(1);
    expect(zoomAfterOpen('user', 1)).toBe(1);
    expect(zoomAfterOpen('reload', 1.5)).toBe(1.5);
    expect(zoomAfterOpen('reload', 1.234)).toBe(1.23);
    expect(zoomAfterOpen('reload', 4)).toBe(2);
    expect(zoomAfterOpen('reload', Number.NaN)).toBe(1);
  });

  it('zooms to 150%, then opening another document shows 100%', () => {
    let zoom = clampDocZoom(1);
    zoom = clampDocZoom(1.5);
    expect(zoom).toBe(1.5);
    expect(zoomPercent(zoom)).toBe(150);
    expect(zoomReadout(zoom)).toBe('zoom 150%');

    // A different file, the list, the tree, or search: same user-open rule.
    zoom = zoomAfterOpen('user', zoom);
    expect(zoom).toBe(1);
    expect(zoomPercent(zoom)).toBe(100);
    expect(zoomReadout(zoom)).toBe('zoom 100%');

    zoom = clampDocZoom(1.5);
    expect(zoomReadout(zoom)).toBe('zoom 150%');
    // Clicking the file that is already open is still a user open.
    zoom = zoomAfterOpen('user', zoom);
    expect(zoomReadout(zoom)).toBe('zoom 100%');

    zoom = clampDocZoom(1.5);
    // Disk watch / in-app refresh of that same document keeps the zoom.
    zoom = zoomAfterOpen('reload', zoom);
    expect(zoom).toBe(1.5);
    expect(zoomReadout(zoom)).toBe('zoom 150%');
  });
});

describe('wheel zoom', () => {
  it('treats one notch as 10 points for pixels, lines, and pages', () => {
    expect(wheelZoomDelta(100, 0)).toBeCloseTo(-0.1);
    expect(wheelZoomDelta(-100, 0)).toBeCloseTo(0.1);
    expect(wheelZoomDelta(3, 1)).toBeCloseTo(-0.1);
    expect(wheelZoomDelta(-3, 1)).toBeCloseTo(0.1);
    expect(wheelZoomDelta(1, 2)).toBeCloseTo(-0.1);
    expect(wheelZoomDelta(-1, 2)).toBeCloseTo(0.1);
    expect(wheelZoomDelta(0, 0)).toBe(0);
  });

  it('snaps a mouse notch and accumulates small trackpad deltas', () => {
    expect(applyWheelZoom(1, 100, 0, 0)).toEqual({ zoom: 0.9, remainder: 0 });
    expect(applyWheelZoom(1, -100, 0, 0)).toEqual({ zoom: 1.1, remainder: 0 });
    expect(applyWheelZoom(1.95, -100, 0, 0)).toEqual({ zoom: 2, remainder: 0 });
    expect(applyWheelZoom(0.55, 100, 0, 0)).toEqual({ zoom: 0.5, remainder: 0 });

    let zoom = 1;
    let remainder = 0;
    for (let i = 0; i < 10; i += 1) {
      const step = applyWheelZoom(zoom, 4, 0, remainder);
      zoom = step.zoom;
      remainder = step.remainder;
    }
    // 4px is 0.4 point. Ten of them are 4 points, so 100% becomes 96%.
    expect(zoom).toBe(0.96);
    expect(remainder).toBeCloseTo(0, 8);
  });
});

describe('zoomFromKey', () => {
  it('steps 10 points and resets to 100%', () => {
    expect(zoomFromKey(1, 'in')).toBe(1.1);
    expect(zoomFromKey(1, 'out')).toBe(0.9);
    expect(zoomFromKey(1.5, 'reset')).toBe(1);
    expect(zoomFromKey(2, 'in')).toBe(2);
    expect(zoomFromKey(0.5, 'out')).toBe(0.5);
  });

  it('maps Ctrl +/-/0 and ignores Ctrl+F', () => {
    expect(zoomKeyCommand({ ctrlKey: true, key: '=' })).toBe('in');
    expect(zoomKeyCommand({ ctrlKey: true, key: '+' })).toBe('in');
    expect(zoomKeyCommand({ metaKey: true, key: '-' })).toBe('out');
    expect(zoomKeyCommand({ ctrlKey: true, key: '0' })).toBe('reset');
    expect(zoomKeyCommand({ ctrlKey: true, key: 'Numpad0' })).toBe('reset');
    expect(zoomKeyCommand({ ctrlKey: true, key: 'f' })).toBeNull();
    expect(zoomKeyCommand({ ctrlKey: true, key: 'F' })).toBeNull();
    expect(zoomKeyCommand({ ctrlKey: true, altKey: true, key: '+' })).toBeNull();
    expect(zoomKeyCommand({ key: '+' })).toBeNull();
  });
});

describe('zoomFromDrag', () => {
  it('uses vertical movement only, 1% per 2px, with no jump at the dead zone', () => {
    expect(zoomFromDrag(1.5, 0)).toBeNull();
    expect(zoomFromDrag(1.5, -2)).toBeNull();
    expect(zoomFromDrag(1.5, 2)).toBeNull();
    // The dead-zone pixels are not part of the zoom, so the first step is flat.
    expect(zoomFromDrag(1.5, -3)).toBe(1.5);
    expect(zoomFromDrag(1.5, 3)).toBe(1.5);
    expect(zoomFromDrag(1, -5)).toBe(1.01);
    expect(zoomFromDrag(1, 7)).toBe(0.98);
    expect(zoomFromDrag(1.5, -203)).toBe(2);
    expect(zoomFromDrag(0.6, 203)).toBe(0.5);
  });
});

describe('pdfWheelOrigin', () => {
  it('puts the pointer in the scroller offset coordinates pdf.js subtracts', () => {
    // Title bar and file list move the page off the window origin.
    // The scroller's offset parent is the PDF frame, so offsetLeft is the contents width.
    expect(pdfWheelOrigin(420, 260, { left: 320, top: 90 }, { left: 264, top: 0 })).toEqual([364, 170]);
    // Already in the same space as client coordinates: leave the point alone.
    expect(pdfWheelOrigin(420, 260, { left: 320, top: 90 }, { left: 320, top: 90 })).toEqual([420, 260]);
  });
});

describe('scrollAfterZoom', () => {
  it('keeps the pointer fixed and otherwise keeps the top line', () => {
    expect(
      scrollAfterZoom({
        scrollLeft: 40,
        scrollTop: 100,
        oldZoom: 1,
        newZoom: 2,
        anchor: { x: 10, y: 50 },
      }),
    ).toEqual({ scrollLeft: 90, scrollTop: 250 });
    expect(
      scrollAfterZoom({ scrollLeft: 40, scrollTop: 100, oldZoom: 1, newZoom: 2 }),
    ).toEqual({ scrollLeft: 80, scrollTop: 200 });
    expect(
      scrollAfterZoom({ scrollLeft: 10, scrollTop: 20, oldZoom: 1.5, newZoom: 1.5, anchor: { x: 5, y: 5 } }),
    ).toEqual({ scrollLeft: 10, scrollTop: 20 });
  });
});


