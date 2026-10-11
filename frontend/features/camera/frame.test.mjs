import assert from 'node:assert/strict';
import test from 'node:test';
import { CARD_ASPECT, guideRect, guideToVideoRect, outputSize } from './frame.ts';

const close = (a, b) => Math.abs(a - b) < 0.01;

test('guide keeps business-card proportions and is centred', () => {
  const g = guideRect(400, 800, 'landscape');
  assert.ok(close(g.w / g.h, CARD_ASPECT));
  assert.ok(close(g.x * 2 + g.w, 400));
  assert.ok(close(g.y * 2 + g.h, 800));
  assert.ok(close(g.w, 400 * 0.88)); // a phone in portrait: width-limited
});

test('portrait guide is the same card turned upright', () => {
  const g = guideRect(400, 800, 'portrait');
  assert.ok(close(g.h / g.w, CARD_ASPECT));
  assert.ok(g.h <= 800 * 0.72 + 0.01);
});

test('guide is height-limited on a wide, short preview', () => {
  const g = guideRect(1600, 400, 'landscape');
  assert.ok(close(g.h, 400 * 0.72));
  assert.ok(close(g.w / g.h, CARD_ASPECT));
});

test('crop maps through object-fit: cover', () => {
  // A 1920×1080 camera shown in a 400×800 preview: scaled ×(800/1080) and its
  // sides cut off, so the centred guide maps to the middle of the frame.
  const guide = { x: 50, y: 300, w: 300, h: 200 };
  const crop = guideToVideoRect(guide, 400, 800, 1920, 1080, 0);
  const scale = 800 / 1080;
  const offsetX = (400 - 1920 * scale) / 2;
  assert.equal(crop.x, Math.round((50 - offsetX) / scale));
  assert.equal(crop.y, Math.round(300 / scale));
  assert.ok(Math.abs(crop.w - 300 / scale) <= 1);
  assert.ok(Math.abs(crop.h - 200 / scale) <= 1);
  // The crop stays centred horizontally in the camera frame.
  assert.ok(Math.abs(crop.x + crop.w / 2 - 960) <= 1);
});

test('margin widens the crop and is clamped to the video', () => {
  const guide = { x: 0, y: 0, w: 640, h: 480 };
  const plain = guideToVideoRect(guide, 640, 480, 640, 480, 0);
  assert.deepEqual(plain, { x: 0, y: 0, w: 640, h: 480 });
  const padded = guideToVideoRect(guide, 640, 480, 640, 480, 0.1);
  assert.deepEqual(padded, { x: 0, y: 0, w: 640, h: 480 });

  const inner = { x: 100, y: 100, w: 200, h: 100 };
  const grown = guideToVideoRect(inner, 640, 480, 640, 480, 0.1);
  assert.deepEqual(grown, { x: 80, y: 90, w: 240, h: 120 });
});

test('output is scaled down to the maximum side only when larger', () => {
  assert.deepEqual(outputSize({ x: 0, y: 0, w: 4000, h: 2500 }, 2000), { w: 2000, h: 1250 });
  assert.deepEqual(outputSize({ x: 0, y: 0, w: 800, h: 500 }, 2000), { w: 800, h: 500 });
});
