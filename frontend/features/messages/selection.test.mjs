import assert from 'node:assert/strict';
import test from 'node:test';
import { cardsWithoutEmail, pageSelectionState, setPageSelection, toggleCard } from './selection.ts';

const a = { id: 1, emails: ['a@x.com'] };
const b = { id: 2, emails: [] };
const c = { id: 3, emails: ['  '] };

test('toggleCard adds then removes without mutating the input', () => {
  const empty = new Map();
  const one = toggleCard(empty, a);
  assert.deepEqual([...one.keys()], [1]);
  assert.equal(empty.size, 0);
  assert.equal(toggleCard(one, a).size, 0);
});

test('setPageSelection only touches the cards on the page', () => {
  const fromOtherPage = new Map([[3, c]]);
  const all = setPageSelection(fromOtherPage, [a, b], true);
  assert.deepEqual([...all.keys()].sort(), [1, 2, 3]);
  const cleared = setPageSelection(all, [a, b], false);
  assert.deepEqual([...cleared.keys()], [3]);
});

test('pageSelectionState reports none / some / all', () => {
  assert.equal(pageSelectionState(new Map(), [a, b]), 'none');
  assert.equal(pageSelectionState(new Map([[1, a]]), [a, b]), 'some');
  assert.equal(pageSelectionState(new Map([[1, a], [2, b]]), [a, b]), 'all');
  assert.equal(pageSelectionState(new Map([[1, a]]), []), 'none');
});

test('cardsWithoutEmail treats blank addresses as missing', () => {
  assert.deepEqual(cardsWithoutEmail([a, b, c]).map((card) => card.id), [2, 3]);
});
