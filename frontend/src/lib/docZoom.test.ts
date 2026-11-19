import { describe, expect, it } from 'vitest';
import {
  anchorPointError,
  applyWheelZoom,
  clampDocZoom,
  correctScrollByVisual,
  measureVisualPerScroll,
  axisCanScroll,
  pageFraction,
  pageFractionVisualDelta,
  paneCentre,
  pdfCentreOrigin,
  sameZoomSession,
  scrollDeltaForVisual,
  visualPerScrollUnit,
  wheelZoomDelta,
  zoomAfterOpen,
  zoomAnchorSettled,
  zoomFromDrag,
  zoomFromKey,
  zoomKeyCommand,
  zoomPercent,
  zoomReadout,
  type ZoomSessionPositions,
  type ZoomSessionSnapshot,
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

describe('paneCentre', () => {
  it('uses the middle of the visible viewport', () => {
    expect(paneCentre(800, 600)).toEqual({ x: 400, y: 300 });
    expect(paneCentre(612, 612)).toEqual({ x: 306, y: 306 });
  });

  it('treats a missing size as an empty pane', () => {
    expect(paneCentre(0, 400)).toEqual({ x: 0, y: 200 });
    expect(paneCentre(Number.NaN, Number.POSITIVE_INFINITY)).toEqual({ x: 0, y: 0 });
  });
});

describe('anchorPointError', () => {
  it('is the change in the anchor offset from the pane centre', () => {
    // Recorded when the caret sat 4px left and 6px above the centre.
    const centre = { x: 400, y: 300 };
    const offset = { x: -4, y: -6 };
    expect(anchorPointError({ x: 396, y: 294 }, centre, offset)).toEqual({ x: 0, y: 0 });
    // After zoom the caret is 10px too low and 2px too far right.
    expect(anchorPointError({ x: 398, y: 304 }, centre, offset)).toEqual({ x: 2, y: 10 });
  });
});

describe('visual scroll correction', () => {
  it('turns a visual error into scroll units from a measured ratio', () => {
    // scrollTop 100 moves content 50 visual px at 50%: ratio 0.5.
    expect(visualPerScrollUnit(200, 150, 100)).toBeCloseTo(0.5);
    expect(scrollDeltaForVisual(50, 0.5)).toBe(100);
    expect(scrollDeltaForVisual(-25, 1)).toBe(-25);
    expect(scrollDeltaForVisual(10, 0)).toBe(0);
    expect(scrollDeltaForVisual(Number.NaN, 1)).toBe(0);
  });

  it('settles at half a pixel', () => {
    expect(zoomAnchorSettled(0.5)).toBe(true);
    expect(zoomAnchorSettled(-0.5)).toBe(true);
    expect(zoomAnchorSettled(0.51)).toBe(false);
    expect(zoomAnchorSettled(Number.NaN)).toBe(true);
  });

  it('measures the ratio with a probe and restores the scroll offset', () => {
    let scroll = 80;
    let pos = 400;
    const setScroll = (value: number) => {
      const next = Math.min(200, Math.max(0, value));
      pos -= (next - scroll) * 0.5;
      scroll = next;
    };
    expect(measureVisualPerScroll(() => pos, () => scroll, setScroll)).toBeCloseTo(0.5);
    expect(scroll).toBe(80);
    expect(pos).toBe(400);
  });

  it('probes the other way when the scroller is at the end', () => {
    let scroll = 100;
    let pos = 800;
    const setScroll = (value: number) => {
      const next = Math.min(100, Math.max(0, value));
      pos -= (next - scroll) * 2;
      scroll = next;
    };
    expect(measureVisualPerScroll(() => pos, () => scroll, setScroll, 20)).toBeCloseTo(2);
    expect(scroll).toBe(100);
    expect(pos).toBe(800);
  });

  it('corrects a 50% zoom error and leaves a clamped scroller alone', () => {
    let scroll = 0;
    let pos = 100;
    const setScroll = (value: number) => {
      const next = Math.max(0, value);
      pos -= (next - scroll) * 0.5;
      scroll = next;
    };
    expect(correctScrollByVisual(50, () => scroll, setScroll, () => pos)).toBe(true);
    expect(scroll).toBeCloseTo(100);
    expect(pos).toBeCloseTo(50);

    expect(correctScrollByVisual(0.4, () => scroll, setScroll, () => pos)).toBe(false);
    expect(scroll).toBeCloseTo(100);
  });
});

describe('pdfCentreOrigin', () => {
  it('converts the visible centre into the origin pdf.js subtracts offset from', () => {
    // The scroller's offset parent is the PDF frame, so offsetLeft is the contents width.
    const box = { left: 320, top: 90 };
    const client = { left: 0, top: 0, width: 800, height: 600 };
    const offset = { left: 264, top: 0 };
    const [x, y] = pdfCentreOrigin(box, client, offset);
    expect([x, y]).toEqual([664, 300]);
    // pdf.js uses origin − offsetLeft/Top as the point inside the container.
    expect(x - offset.left).toBe(400);
    expect(y - offset.top).toBe(300);
  });

  it('keeps a border and a scrollbar out of the centre', () => {
    const box = { left: 320, top: 90 };
    const client = { left: 2, top: 4, width: 780, height: 560 };
    const offset = { left: 264, top: 0 };
    const [x, y] = pdfCentreOrigin(box, client, offset);
    expect(x - offset.left).toBe(2 + 390);
    expect(y - offset.top).toBe(4 + 280);
  });

  it('matches viewport coordinates when the offset parent is the viewport', () => {
    const box = { left: 320, top: 90 };
    const client = { left: 0, top: 0, width: 200, height: 340 };
    expect(pdfCentreOrigin(box, client, { left: 320, top: 90 })).toEqual([420, 260]);
  });
});

describe('axisCanScroll', () => {
  it('counts a real offset even when CSS zoom reports no overflow', () => {
    expect(axisCanScroll(12, 800, 800)).toBe(true);
    expect(axisCanScroll(-4, 800, 800)).toBe(true);
    expect(axisCanScroll(0, 800, 800)).toBe(false);
    expect(axisCanScroll(0.4, 800, 800)).toBe(false);
  });

  it('scrolls when the content is more than a pixel larger than the pane', () => {
    expect(axisCanScroll(0, 901, 800)).toBe(true);
    expect(axisCanScroll(0, 801, 800)).toBe(false);
    expect(axisCanScroll(0, Number.NaN, 800)).toBe(false);
  });
});

function session(id: string, scroll: Partial<ZoomSessionPositions> = {}): ZoomSessionSnapshot {
  return {
    id,
    scroll: {
      documentTop: 120,
      documentLeft: 40,
      contentsTop: 80,
      pdfTop: null,
      pdfLeft: null,
      ...scroll,
    },
  };
}

describe('sameZoomSession', () => {
  it('keeps the gesture when the document and every scroll position stay within 1px', () => {
    const prev = session('doc');
    expect(sameZoomSession(prev, session('doc'))).toBe(true);
    expect(sameZoomSession(prev, session('doc', { documentTop: 121, pdfTop: null }))).toBe(true);
    expect(sameZoomSession(prev, session('doc', { contentsTop: 79.2 }))).toBe(true);
  });

  it('starts a fresh capture after a scroll, a new document, or a reload', () => {
    const prev = session('doc');
    expect(sameZoomSession(prev, session('doc', { documentLeft: 42 }))).toBe(false);
    expect(sameZoomSession(prev, session('other'))).toBe(false);
    expect(sameZoomSession(null, session('doc'))).toBe(false);
    expect(sameZoomSession(prev, null)).toBe(false);
    expect(sameZoomSession(prev, session('doc', { contentsTop: null }))).toBe(false);
    const pdf = session('pdf', {
      documentTop: null,
      documentLeft: null,
      contentsTop: null,
      pdfTop: 10,
      pdfLeft: 0,
    });
    expect(sameZoomSession(pdf, pdf)).toBe(true);
  });
});

describe('page fraction', () => {
  it('records where the centre sits in the page and the error after scaling', () => {
    const centre = 180;
    const fraction = pageFraction(centre, 100, 200);
    expect(fraction).toBeCloseTo(0.4);
    // Page grew and its top moved. The same fraction is 30px below the centre.
    expect(pageFractionVisualDelta(fraction, 50, 400, centre)).toBeCloseTo(30);
    expect(scrollDeltaForVisual(pageFractionVisualDelta(fraction, 50, 400, centre), 1)).toBeCloseTo(30);
  });

  it('returns 0 when the page size cannot divide', () => {
    expect(pageFraction(10, 0, 0)).toBe(0);
    expect(pageFractionVisualDelta(Number.NaN, 0, 10, 5)).toBe(0);
  });
});


