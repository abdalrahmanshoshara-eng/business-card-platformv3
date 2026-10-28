import assert from 'node:assert/strict';
import test from 'node:test';
import { firstImageFile, messageImageError, MESSAGE_IMAGE_MAX_MB } from './image.ts';

test('firstImageFile picks the first image and ignores other files', () => {
  const text = { type: 'text/plain', size: 10 };
  const png = { type: 'image/png', size: 10 };
  assert.equal(firstImageFile([text, png]), png);
  assert.equal(firstImageFile([text]), null);
  assert.equal(firstImageFile(null), null);
});

test('messageImageError accepts supported images within the size limit', () => {
  assert.equal(messageImageError({ type: 'image/jpeg', size: 1024 }), '');
  assert.equal(messageImageError({ type: 'image/png', size: MESSAGE_IMAGE_MAX_MB * 1024 * 1024 }), '');
});

test('messageImageError rejects other types and oversized files', () => {
  assert.match(messageImageError({ type: 'image/svg+xml', size: 10 }), /غير مدعوم/);
  assert.match(messageImageError({ type: 'image/png', size: MESSAGE_IMAGE_MAX_MB * 1024 * 1024 + 1 }), /يتجاوز/);
});
