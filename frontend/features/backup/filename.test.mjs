import assert from 'node:assert/strict';
import test from 'node:test';
import { filenameFromDisposition } from './filename.ts';

test('reads the quoted filename Django sends', () => {
  assert.equal(
    filenameFromDisposition('attachment; filename="business-cards-backup-20261011-1200.sql"', 'x.sql'),
    'business-cards-backup-20261011-1200.sql',
  );
});

test('prefers the RFC 5987 encoded form', () => {
  assert.equal(
    filenameFromDisposition("attachment; filename=\"a.sql\"; filename*=UTF-8''backup%20one.sql", 'x.sql'),
    'backup one.sql',
  );
});

test('falls back when the header is missing or has no name', () => {
  assert.equal(filenameFromDisposition(null, 'x.sql'), 'x.sql');
  assert.equal(filenameFromDisposition('attachment', 'x.sql'), 'x.sql');
});
