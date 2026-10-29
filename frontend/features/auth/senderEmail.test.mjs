import assert from 'node:assert/strict';
import test from 'node:test';
import { senderEmailError } from './senderEmail.ts';

test('accepts a normal address, ignoring surrounding spaces', () => {
  assert.equal(senderEmailError('khaled@mei.gov.sy'), '');
  assert.equal(senderEmailError('  a.b@example.com '), '');
});

test('asks for an address when empty', () => {
  assert.match(senderEmailError(''), /اكتب/);
  assert.match(senderEmailError('   '), /اكتب/);
});

test('rejects malformed addresses', () => {
  for (const bad of ['khaled', 'khaled@', '@mei.gov.sy', 'khaled@mei', 'a b@x.com']) {
    assert.match(senderEmailError(bad), /صالح/, bad);
  }
});
