/** Document zoom shared by HTML pages and PDFs.
 *
 * One unitless scale: 1 is 100%. The range is 50%–200% (0.5–2). pdf.js can
 * go wider, but page-fit is not used, so every control stays inside this
 * range and 100% is pdf.js actual size (`currentScale = 1`). Values are
 * always snapped to an integer percent. Zoom is not stored; a full page
 * load starts at 100%.
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

/** Pointer position in the document viewport, for wheel anchoring. */
export type DocZoomAnchor = { x: number; y: number };

/** Wheel origin passed to pdf.js. `id` lets the viewer apply each gesture once. */
export type PdfScaleOrigin = { x: number; y: number; id: number };

export type ZoomKeyCommand = 'in' | 'out' | 'reset';

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

/**
 * Wheel origin for pdf.js `updateScale`. pdf.js subtracts
 * `container.offsetLeft/Top` (relative to the offset parent) from `origin`.
 * A wheel event reports viewport `clientX/Y`. Passing those through unchanged
 * keeps the pointer fixed only when the scroller's offset parent is the
 * viewport. The document pane is not: it sits below the title bar and to the
 * right of the file list, and its offset parent is the PDF frame.
 *
 * `box` is the scroller's border box (`getBoundingClientRect`). `offset` is
 * `offsetLeft` / `offsetTop`.
 */
export function pdfWheelOrigin(
  clientX: number,
  clientY: number,
  box: { left: number; top: number },
  offset: { left: number; top: number },
): [number, number] {
  const x =
    Number.isFinite(clientX) && Number.isFinite(box.left) && Number.isFinite(offset.left)
      ? clientX - box.left + offset.left
      : clientX;
  const y =
    Number.isFinite(clientY) && Number.isFinite(box.top) && Number.isFinite(offset.top)
      ? clientY - box.top + offset.top
      : clientY;
  return [x, y];
}

/**
 * Scroll offsets that keep the same content under the pointer (or the top
 * line, when `anchor` is omitted) after a CSS zoom change.
 *
 * Layout coordinates scale with the zoom factor. `anchor` is the pointer
 * position inside the viewport, in the same pixels as the scroll offsets.
 */
export function scrollAfterZoom(input: {
  scrollLeft: number;
  scrollTop: number;
  oldZoom: number;
  newZoom: number;
  anchor?: DocZoomAnchor | null;
}): { scrollLeft: number; scrollTop: number } {
  const oldZoom = input.oldZoom > 0 && Number.isFinite(input.oldZoom) ? input.oldZoom : 1;
  const newZoom = Number.isFinite(input.newZoom) ? input.newZoom : oldZoom;
  const ratio = newZoom / oldZoom;
  const left = Number.isFinite(input.scrollLeft) ? input.scrollLeft : 0;
  const top = Number.isFinite(input.scrollTop) ? input.scrollTop : 0;
  if (!Number.isFinite(ratio)) return { scrollLeft: left, scrollTop: top };
  const anchor = input.anchor;
  if (anchor && Number.isFinite(anchor.x) && Number.isFinite(anchor.y)) {
    return {
      scrollLeft: (left + anchor.x) * ratio - anchor.x,
      scrollTop: (top + anchor.y) * ratio - anchor.y,
    };
  }
  return { scrollLeft: left * ratio, scrollTop: top * ratio };
}
