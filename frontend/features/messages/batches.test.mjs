import assert from 'node:assert/strict';
import test from 'node:test';
import { isSettled, planSend, summaryTone } from './batches.ts';

const card = (id, emails, person_name = `P${id}`) => ({ id, emails, person_name });

test('splits sendable cards into batches in selection order', () => {
  const cards = [1, 2, 3, 4, 5, 6, 7].map((id) => card(id, [`p${id}@x.com`]));
  const plan = planSend(cards, 3);
  assert.deepEqual(plan.batches, [[1, 2, 3], [4, 5, 6], [7]]);
  assert.deepEqual(plan.skipped, []);
});

test('settles cards without email and repeated addresses without a request', () => {
  const plan = planSend([
    card(1, ['Same@x.com']),
    card(2, []),
    card(3, ['  ']),
    card(4, ['same@X.com']),
    card(5, ['other@x.com']),
  ], 5);
  assert.deepEqual(plan.batches, [[1, 5]]);
  assert.deepEqual(plan.skipped.map((r) => [r.card_id, r.status]), [
    [2, 'no_email'],
    [3, 'no_email'],
    [4, 'duplicate_email'],
  ]);
  assert.equal(plan.skipped[2].email, 'same@X.com');
});

test('duplicates are caught across batch boundaries', () => {
  const plan = planSend([card(1, ['a@x.com']), card(2, ['b@x.com']), card(3, ['a@x.com'])], 1);
  assert.deepEqual(plan.batches, [[1], [2]]);
  assert.equal(plan.skipped[0].status, 'duplicate_email');
});

test('an empty selection plans nothing', () => {
  assert.deepEqual(planSend([]), { batches: [], skipped: [] });
});

test('failed and not-sent cards stay selected for a retry', () => {
  assert.equal(isSettled('sent'), true);
  assert.equal(isSettled('no_email'), true);
  assert.equal(isSettled('duplicate_email'), true);
  assert.equal(isSettled('failed'), false);
  assert.equal(isSettled('not_sent'), false);
  assert.equal(isSettled('unknown'), true);
});

test('summary is green only when nothing went wrong', () => {
  assert.equal(summaryTone(['sent', 'sent', 'no_email']), 'success');
  assert.equal(summaryTone(['sent', 'failed']), 'warning');
  assert.equal(summaryTone(['sent', 'unknown', 'not_sent']), 'warning');
  assert.equal(summaryTone(['failed']), 'error');
  assert.equal(summaryTone(['no_email']), 'error');
  assert.equal(summaryTone([]), 'error');
});
