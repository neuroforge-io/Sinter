import assert from 'node:assert/strict';
import test from 'node:test';
import {selectWindowSource} from '../src/sinter/web/campaign-window-source.js';

const original = {
  name: 'Fictional route', status: 'clarification', deadline: '2026-10-15',
  window_source_id: 'first', window_source_url: 'https://example.invalid/first',
  window_source_quote: 'Existing exact wording.', window_checked_at: '2026-09-28',
  fit: 'Authority and costs remain unknown.', history: [{date: '2026-09-12'}],
};

test('another source invalidates only its quote snapshot, without mutating history', () => {
  const before = structuredClone(original);
  const result = selectWindowSource(original, {id: 'second', url: 'https://example.invalid/second'});
  assert.equal(result.changedSource, true);
  assert.deepEqual(result.opportunity, {...before,
    window_source_id: 'second', window_source_url: 'https://example.invalid/second',
    window_source_quote: '', window_checked_at: ''});
  assert.deepEqual(original, before);
});

test('the same saved source preserves the exact old quote and check date', () => {
  const result = selectWindowSource(original, {id: 'first',
    url: 'https://example.invalid/first', checked_at: '2026-10-01'});
  assert.equal(result.changedSource, false);
  assert.deepEqual(result.opportunity, original);
});

test('a changed URL for the same identity needs a fresh operator quote', () => {
  const result = selectWindowSource(original, {id: 'first', url: 'https://example.invalid/new'});
  assert.equal(result.changedSource, true);
  assert.equal(result.opportunity.window_source_quote, '');
  assert.equal(result.opportunity.window_checked_at, '');
  assert.equal(result.opportunity.deadline, original.deadline);
});

test('clearing a source keeps the route and its recorded closing date', () => {
  const result = selectWindowSource(original, null);
  assert.equal(result.changedSource, true);
  assert.equal(result.opportunity.window_source_id, '');
  assert.equal(result.opportunity.window_source_url, '');
  assert.equal(result.opportunity.window_source_quote, '');
  assert.equal(result.opportunity.window_checked_at, '');
  assert.equal(result.opportunity.deadline, original.deadline);
  assert.equal(result.opportunity.status, 'clarification');
});
