/** Document zoom shared by HTML pages and PDFs.
 *
 * One unitless scale: 1 is 100%. The range is 50%–200% (0.5–2). pdf.js can
 * go wider, but page-fit is not used, so every control stays inside this
 * range and 100% is pdf.js actual size (`currentScale = 1`). Values are
 * always snapped to an integer percent. Zoom is not stored; a full page
 * load starts at 100%. Gestures keep the centre of the visible pane in
 * place. The pointer is not an anchor.
 */

export const DOC_ZOOM_MIN = 0.5;
export const DOC_ZOOM_MAX = 2;
export const DOC_ZOOM_DEFAULT = 1;

/** Ctrl +/- and one mouse-wheel notch. Ten percentage points. */
export const KEY_ZOOM_STEP = 0.1;

/** Pixel deltaY that counts as one mouse notch. */
export const WHEEL_NOTCH_PX = 100;

/** deltaMode 1: a notch is about three lines. */
export const WHEEL_LINES_PER_NOTCH = 3;

/** Pointer drag on the readout. Movement inside this does not change zoom. */
export const DRAG_DEAD_ZONE_PX = 3;

/** Vertical drag rate: 1 percentage point per 2px. Up increases zoom. */
export const DRAG_PX_PER_PERCENT = 2;

export type DocZoomOpenKind = 'user' | 'reload';

export type ZoomKeyCommand = 'in' | 'out' | 'reset';

/** Stop correcting once the anchor is this close, in visual pixels. */
export const ZOOM_ANCHOR_TOLERANCE_PX = 0.5;

/** Measure-then-correct passes after the zoom changes. */
export const ZOOM_ANCHOR_ITERS = 3;

/** Scroll probe used to measure visual pixels per scroll unit. */
export const ZOOM_SCROLL_PROBE = 20;

/** Snap to an integer percent inside {@link DOC_ZOOM_MIN}..{@link DOC_ZOOM_MAX}. */
export function clampDocZoom(value: number): number {
  if (!Number.isFinite(value)) return DOC_ZOOM_DEFAULT;
  const clamped = Math.min(DOC_ZOOM_MAX, Math.max(DOC_ZOOM_MIN, value));
  const percent = Math.round(clamped * 100 + 1e-6);
  return percent / 100;
}

export function zoomPercent(zoom: number): number {
  return Math.round(clampDocZoom(zoom) * 100);
}

/** Readout text. N is Math.round(docZoom * 100) of the visible document. */
export function zoomReadout(zoom: number): string {
  return `zoom ${zoomPercent(zoom)}%`;
}

/**
 * `user` — opened from the list, tree, or search, including the file that
 * is already open. Zoom returns to 100%.
 * `reload` — the same open document was loaded again without a new open
 * (iframe/PDF refresh after a disk change, or an in-app F5/reload of that
 * frame). Zoom stays where it is.
 *
 * A full application reload has no saved zoom, so it starts at 100%.
 * `reload` only keeps the in-memory value for a refresh of the open document.
 */
export function zoomAfterOpen(kind: DocZoomOpenKind, current: number): number {
  if (kind === 'reload') return clampDocZoom(current);
  return DOC_ZOOM_DEFAULT;
}

/** Map deltaMode 0 (px), 1 (lines), and 2 (pages) onto pixels. */
export function normaliseWheelPixels(deltaY: number, deltaMode = 0): number {
  if (!Number.isFinite(deltaY)) return 0;
  if (deltaMode === 1) return deltaY * (WHEEL_NOTCH_PX / WHEEL_LINES_PER_NOTCH);
  if (deltaMode === 2) return deltaY * WHEEL_NOTCH_PX;
  return deltaY;
}

/** Zoom change for one wheel event. Positive deltaY (wheel down) zooms out. */
export function wheelZoomDelta(deltaY: number, deltaMode = 0): number {
  const pixels = normaliseWheelPixels(deltaY, deltaMode);
  if (!Number.isFinite(pixels) || pixels === 0) return 0;
  return (-pixels / WHEEL_NOTCH_PX) * KEY_ZOOM_STEP;
}

/**
 * Apply one wheel step. `remainder` carries the fraction of a percent that
 * an integer snap dropped, so small trackpad deltas add up.
 * At the min/max clamp the leftover is dropped.
 */
export function applyWheelZoom(
  current: number,
  deltaY: number,
  deltaMode = 0,
  remainder = 0,
): { zoom: number; remainder: number } {
  const base = clampDocZoom(current);
  const carried = Number.isFinite(remainder) ? remainder : 0;
  const raw = base + carried + wheelZoomDelta(deltaY, deltaMode);
  const zoom = clampDocZoom(raw);
  let nextRemainder = raw - zoom;
  if (!Number.isFinite(nextRemainder)) nextRemainder = 0;
  if ((zoom <= DOC_ZOOM_MIN && raw < DOC_ZOOM_MIN) || (zoom >= DOC_ZOOM_MAX && raw > DOC_ZOOM_MAX)) {
    nextRemainder = 0;
  }
  return { zoom, remainder: nextRemainder };
}

export function zoomFromKey(current: number, command: ZoomKeyCommand): number {
  if (command === 'reset') return DOC_ZOOM_DEFAULT;
  const delta = command === 'in' ? KEY_ZOOM_STEP : -KEY_ZOOM_STEP;
  return clampDocZoom(clampDocZoom(current) + delta);
}

/** Ctrl/Cmd +/-/0. Null for anything else, including Ctrl+F. */
export function zoomKeyCommand(event: {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
}): ZoomKeyCommand | null {
  if ((!event.ctrlKey && !event.metaKey) || event.altKey) return null;
  switch (event.key) {
    case '=':
    case '+':
    case 'Add':
    case 'NumpadAdd':
      return 'in';
    case '-':
    case '_':
    case 'Subtract':
    case 'NumpadSubtract':
      return 'out';
    case '0':
    case 'Numpad0':
      return 'reset';
    default:
      return null;
  }
}

/**
 * Vertical drag relative to the zoom at pointerdown.
 * Returns null while `dy` is inside the dead zone so the value does not jump
 * when the drag starts. Horizontal movement is not an input.
 * Up (negative dy) increases zoom, 1% per {@link DRAG_PX_PER_PERCENT} px
 * past the dead zone.
 */
export function zoomFromDrag(
  startZoom: number,
  dy: number,
  deadZonePx = DRAG_DEAD_ZONE_PX,
): number | null {
  if (!Number.isFinite(dy) || !Number.isFinite(startZoom)) return null;
  if (Math.abs(dy) < deadZonePx) return null;
  const adjusted = dy - Math.sign(dy) * deadZonePx;
  const delta = -adjusted / DRAG_PX_PER_PERCENT / 100;
  return clampDocZoom(startZoom + delta);
}

/** Centre of a viewport. Width and height are visual pixels. */
export function paneCentre(width: number, height: number): { x: number; y: number } {
  const w = Number.isFinite(width) && width > 0 ? width : 0;
  const h = Number.isFinite(height) && height > 0 ? height : 0;
  return { x: w / 2, y: h / 2 };
}

/**
 * How far `point` is from the recorded anchor (`centre + offset`), in visual
 * pixels. Positive means the anchor is too far down or to the right.
 */
export function anchorPointError(
  point: { x: number; y: number },
  centre: { x: number; y: number },
  offset: { x: number; y: number },
): { x: number; y: number } {
  const px = Number.isFinite(point.x) ? point.x : 0;
  const py = Number.isFinite(point.y) ? point.y : 0;
  const cx = Number.isFinite(centre.x) ? centre.x : 0;
  const cy = Number.isFinite(centre.y) ? centre.y : 0;
  const ox = Number.isFinite(offset.x) ? offset.x : 0;
  const oy = Number.isFinite(offset.y) ? offset.y : 0;
  return { x: px - (cx + ox), y: py - (cy + oy) };
}

/** True when a visual error is close enough to leave the scroll alone. */
export function zoomAnchorSettled(visualDelta: number, tolerance = ZOOM_ANCHOR_TOLERANCE_PX): boolean {
  return !Number.isFinite(visualDelta) || Math.abs(visualDelta) <= tolerance;
}

/**
 * Visual pixels the anchor moves toward the origin per +1 scroll unit.
 * `scrollDelta` is the scroll change that was applied. Positions are the
 * anchor's visual coordinate before and after that change.
 */
export function visualPerScrollUnit(
  positionBefore: number,
  positionAfter: number,
  scrollDelta: number,
): number {
  if (!Number.isFinite(positionBefore) || !Number.isFinite(positionAfter)) return 0;
  if (!Number.isFinite(scrollDelta) || scrollDelta === 0) return 0;
  return (positionBefore - positionAfter) / scrollDelta;
}

/**
 * Scroll units that cancel a visual error.
 * `visualDelta` is current − desired (visual px). Positive means the anchor
 * is too far down or to the right, so a normal scroller increases scrollTop
 * or scrollLeft.
 * `visualPerScroll` is {@link visualPerScrollUnit}. At 50% CSS zoom, scrollTop
 * 100 moves content 50 visual px, so the ratio is 0.5 and a 50px error needs
 * 100 scroll units. Returns 0 when the ratio was not measured.
 */
export function scrollDeltaForVisual(visualDelta: number, visualPerScroll: number): number {
  if (!Number.isFinite(visualDelta) || visualDelta === 0) return 0;
  if (!Number.isFinite(visualPerScroll) || visualPerScroll === 0) return 0;
  return visualDelta / visualPerScroll;
}

/**
 * Measure {@link visualPerScrollUnit} by scrolling, reading, and restoring.
 * Tries `+probe` first and the opposite direction when that is clamped.
 * `setScroll` receives an absolute scroll offset.
 */
export function measureVisualPerScroll(
  read: () => number | null,
  getScroll: () => number,
  setScroll: (value: number) => void,
  probe = ZOOM_SCROLL_PROBE,
): number {
  const start = getScroll();
  const before = read();
  if (!Number.isFinite(start) || before === null || !Number.isFinite(before)) return 0;
  const magnitude = Number.isFinite(probe) && Math.abs(probe) > 0 ? Math.abs(probe) : ZOOM_SCROLL_PROBE;
  let ratio = 0;
  try {
    setScroll(start + magnitude);
    let moved = getScroll() - start;
    if (!Number.isFinite(moved) || moved === 0) {
      setScroll(start - magnitude);
      moved = getScroll() - start;
    }
    if (!Number.isFinite(moved) || moved === 0) return 0;
    const after = read();
    if (after === null || !Number.isFinite(after)) return 0;
    ratio = visualPerScrollUnit(before, after, moved);
  } finally {
    setScroll(start);
  }
  return ratio;
}

/**
 * Apply one scroll correction for a visual error. The probe is restored
 * before the real write. Returns false when the scroll offset does not change.
 */
export function correctScrollByVisual(
  visualDelta: number,
  getScroll: () => number,
  setScroll: (value: number) => void,
  read: () => number | null,
): boolean {
  if (zoomAnchorSettled(visualDelta)) return false;
  const ratio = measureVisualPerScroll(read, getScroll, setScroll);
  const step = scrollDeltaForVisual(visualDelta, ratio);
  if (step === 0) return false;
  const before = getScroll();
  if (!Number.isFinite(before)) return false;
  setScroll(before + step);
  const after = getScroll();
  return Number.isFinite(after) && after !== before;
}

/**
 * Origin for pdf.js `updateScale` that zooms about the centre of the visible
 * viewer container. pdf.js subtracts `container.offsetLeft/Top` (`offset`)
 * from this origin. `box` is the container border box in viewport coordinates.
 * `client` is the visible area inside the border (`clientLeft/Top/Width/Height`),
 * so the centre excludes scrollbars. The container's offset parent is the PDF
 * frame, not the viewport.
 */
export function pdfCentreOrigin(
  box: { left: number; top: number },
  client: { left: number; top: number; width: number; height: number },
  offset: { left: number; top: number },
): [number, number] {
  const mid = paneCentre(client.width, client.height);
  const clientLeft = Number.isFinite(client.left) ? client.left : 0;
  const clientTop = Number.isFinite(client.top) ? client.top : 0;
  const centreX = (Number.isFinite(box.left) ? box.left : 0) + clientLeft + mid.x;
  const centreY = (Number.isFinite(box.top) ? box.top : 0) + clientTop + mid.y;
  const x =
    Number.isFinite(centreX) && Number.isFinite(box.left) && Number.isFinite(offset.left)
      ? centreX - box.left + offset.left
      : centreX;
  const y =
    Number.isFinite(centreY) && Number.isFinite(box.top) && Number.isFinite(offset.top)
      ? centreY - box.top + offset.top
      : centreY;
  return [x, y];
}

/**
 * Fraction of a page under a viewport point. 0 is the page's start edge,
 * 1 is the end edge. A point outside the page is outside 0..1.
 */
export function pageFraction(point: number, start: number, size: number): number {
  if (!Number.isFinite(point) || !Number.isFinite(start) || !Number.isFinite(size) || size === 0) return 0;
  return (point - start) / size;
}

/**
 * Visual error of a stored page fraction. Positive when that point on the
 * page is below or to the right of `viewportPoint`. A zero size has no point
 * to place, so the error is 0 and the scroll is left alone.
 */
export function pageFractionVisualDelta(
  fraction: number,
  pageStart: number,
  pageSize: number,
  viewportPoint: number,
): number {
  if (![fraction, pageStart, pageSize, viewportPoint].every((n) => Number.isFinite(n))) return 0;
  if (pageSize === 0) return 0;
  return pageStart + fraction * pageSize - viewportPoint;
}

/**
 * True when a scroller can still move on this axis.
 * A non-zero offset counts even if `scrollSize` was reported equal to
 * `clientSize` (CSS zoom on the root can do that for the horizontal axis
 * while `scrollLeft` is still set). The +1px gate ignores a subpixel remainder.
 */
export function axisCanScroll(offset: number, scrollSize: number, clientSize: number): boolean {
  if (Number.isFinite(offset) && Math.abs(offset) > 0.5) return true;
  if (!Number.isFinite(scrollSize) || !Number.isFinite(clientSize)) return false;
  return scrollSize > clientSize + 1;
}

/**
 * Scroll positions taken after a zoom correction.
 * Null means that scroller is not part of the open document (no contents
 * list, or the other viewer). A number, including 0, is a real position.
 */
export type ZoomSessionPositions = {
  documentTop: number | null;
  documentLeft: number | null;
  contentsTop: number | null;
  pdfTop: number | null;
  pdfLeft: number | null;
};

/** Document identity plus the scroll positions that keep a zoom session. */
export type ZoomSessionSnapshot = {
  id: string;
  scroll: ZoomSessionPositions;
};

function sessionAxisNear(prev: number | null, now: number | null, tol: number): boolean {
  if (prev === null || now === null) return prev === now;
  if (!Number.isFinite(prev) || !Number.isFinite(now)) return false;
  return Math.abs(prev - now) <= tol;
}

/**
 * True when `now` is still the zoom gesture stored in `prev`.
 * The document id must match and every scroll position must be within `tol`
 * (default 1px). A new document, a reload (caller passes null), or any
 * scroll past `tol` starts a fresh capture.
 */
export function sameZoomSession(
  prev: ZoomSessionSnapshot | null | undefined,
  now: ZoomSessionSnapshot | null | undefined,
  tol = 1,
): boolean {
  if (!prev || !now) return false;
  if (!prev.id || prev.id !== now.id) return false;
  const limit = Number.isFinite(tol) ? Math.abs(tol) : 1;
  const a = prev.scroll;
  const b = now.scroll;
  if (!a || !b) return false;
  return (
    sessionAxisNear(a.documentTop, b.documentTop, limit) &&
    sessionAxisNear(a.documentLeft, b.documentLeft, limit) &&
    sessionAxisNear(a.contentsTop, b.contentsTop, limit) &&
    sessionAxisNear(a.pdfTop, b.pdfTop, limit) &&
    sessionAxisNear(a.pdfLeft, b.pdfLeft, limit)
  );
}
