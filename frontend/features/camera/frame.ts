// Geometry for the live-camera card guide: where the guide rectangle sits on
// screen, and which part of the camera frame it covers (so the captured photo
// is cropped to the card).

// ISO/IEC 7810 ID-1 — the standard business-card proportions (85.6 × 54 mm).
export const CARD_ASPECT = 85.6 / 54;

export type Orientation = 'landscape' | 'portrait';

export type Rect = { x: number; y: number; w: number; h: number };

/** The guide rectangle, centred in a `viewW` × `viewH` preview. */
export function guideRect(viewW: number, viewH: number, orientation: Orientation = 'landscape'): Rect {
  const aspect = orientation === 'landscape' ? CARD_ASPECT : 1 / CARD_ASPECT;
  const maxW = viewW * 0.88;
  const maxH = viewH * 0.72;
  const w = Math.min(maxW, maxH * aspect);
  const h = w / aspect;
  return { x: (viewW - w) / 2, y: (viewH - h) / 2, w, h };
}

/**
 * Map a rectangle drawn over the preview to source-pixel coordinates of the
 * video, for a `<video>` rendered with `object-fit: cover` (scaled to fill the
 * preview and centred, so its edges may be cropped off-screen).
 *
 * `margin` grows the crop by that fraction of the guide on every side, so a
 * card held slightly outside the lines keeps its edges. The result is clamped
 * to the video and rounded to whole pixels.
 */
export function guideToVideoRect(
  guide: Rect,
  viewW: number,
  viewH: number,
  videoW: number,
  videoH: number,
  margin = 0.04,
): Rect {
  const scale = Math.max(viewW / videoW, viewH / videoH);
  const offsetX = (viewW - videoW * scale) / 2;
  const offsetY = (viewH - videoH * scale) / 2;

  const padX = guide.w * margin;
  const padY = guide.h * margin;
  const left = Math.max(0, (guide.x - padX - offsetX) / scale);
  const top = Math.max(0, (guide.y - padY - offsetY) / scale);
  const right = Math.min(videoW, (guide.x + guide.w + padX - offsetX) / scale);
  const bottom = Math.min(videoH, (guide.y + guide.h + padY - offsetY) / scale);

  const x = Math.round(left);
  const y = Math.round(top);
  return { x, y, w: Math.round(right) - x, h: Math.round(bottom) - y };
}

/** Output size for a crop, scaled down so its long side is at most `maxSide`. */
export function outputSize(crop: Rect, maxSide = 2000): { w: number; h: number } {
  const ratio = Math.min(1, maxSide / Math.max(crop.w, crop.h));
  return { w: Math.round(crop.w * ratio), h: Math.round(crop.h * ratio) };
}
