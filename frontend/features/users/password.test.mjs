import assert from 'node:assert/strict';
import test from 'node:test';
import { generateSecurePassword } from './password.ts';

test('generates a 16-character password containing every required character group', () => {
  const password = generateSecurePassword();

  assert.equal(password.length, 16);
  assert.match(password, /[a-z]/);
  assert.match(password, /[A-Z]/);
  assert.match(password, /[0-9]/);
  assert.match(password, /[!@#$%&*+\-=?]/);
});

test('honours a requested length and produces fresh values', () => {
  const values = new Set(Array.from({ length: 20 }, () => generateSecurePassword(24)));

  assert.equal(values.size, 20);
  for (const password of values) assert.equal(password.length, 24);
});

test('rejects lengths too short to include every required group', () => {
  assert.throws(() => generateSecurePassword(3), RangeError);
});
