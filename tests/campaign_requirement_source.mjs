import assert from 'node:assert/strict';
import test from 'node:test';
import {selectRequirementSource} from '../src/sinter/web/campaign-requirement-source.js';

const first = Object.freeze({id: 'source-1', url: 'https://example.invalid/first',
  checked_at: '2026-09-28'});
const second = Object.freeze({id: 'source-2', url: 'https://example.invalid/second',
  checked_at: '2026-09-30'});
const note = 'Costs remain unclear. No approval or owner is confirmed. e\u0301 🐝 <literal>';
const requirement = (changes = {}) => Object.freeze({opportunity: 'Fictional route',
  rule: 'Permitted costs', status: 'clarification', evidence: note, source_id: '',
  source_url: '', source_quote: '', checked_at: '', ...changes});

test('first explicit link keeps the entered clarification and exact explanatory note', () => {
  const row = requirement();
  const before = structuredClone(row);
  const {requirement: linked, changedSource, resetAssessment} = selectRequirementSource(row, first);
  assert.deepEqual(linked, {...row, source_id: first.id, source_url: first.url,
    checked_at: ''});
  assert.equal(changedSource, true);
  assert.equal(resetAssessment, false);
  assert.deepEqual(row, before);
  assert.equal(linked.evidence, note);
});

test('unknown and clarification stay explicit on replacement and unlinking', () => {
  for (const status of ['unknown', 'clarification']) {
    const row = requirement({status, source_id: first.id, source_url: first.url,
      source_quote: 'Previous exact wording.', checked_at: first.checked_at});
    for (const source of [second, null]) {
      const result = selectRequirementSource(row, source);
      assert.equal(result.requirement.status, status);
      assert.equal(result.requirement.evidence, note);
      assert.equal(result.requirement.source_quote, '');
      assert.equal(result.requirement.checked_at, '');
      assert.equal(result.requirement.source_url, source?.url || '');
      assert.equal(result.resetAssessment, false);
      assert.deepEqual(result.requirement.source_history, [{state: 'historical',
        reason: source ? 'replaced' : 'cleared', record: beforeRecord(row)}]);
      assert.equal(row.source_quote, 'Previous exact wording.');
    }
  }
});

test('changing a met or not-met assessment source still requires a fresh assessment', () => {
  for (const status of ['met', 'not_met']) {
    const row = requirement({status, source_id: first.id, source_url: first.url,
      source_quote: 'Previous exact wording.', checked_at: first.checked_at});
    for (const source of [second, null]) {
      const result = selectRequirementSource(row, source);
      assert.equal(result.requirement.status, 'unknown');
      assert.equal(result.requirement.evidence, note);
      assert.equal(result.requirement.source_quote, '');
      assert.equal(result.requirement.checked_at, '');
      assert.equal(result.resetAssessment, true);
      assert.deepEqual(result.requirement.source_history[0].record, beforeRecord(row));
      assert.equal(row.status, status);
    }
  }
});

function beforeRecord(row) { return structuredClone(row); }

test('a refreshed URL at the same stable source ID archives the exact old snapshot', () => {
  const row = requirement({status: 'met', source_id: first.id, source_url: first.url,
    source_quote: 'Original café 中文 e\u0301 🐝\r\n<literal>', checked_at: '2026-09-10'});
  const result = selectRequirementSource(row, {...first, url: 'https://example.invalid/refreshed'});
  assert.equal(result.changedSource, true);
  assert.equal(result.requirement.status, 'unknown');
  assert.equal(result.requirement.source_quote, '');
  assert.equal(result.requirement.checked_at, '');
  assert.deepEqual(result.requirement.source_history[0].record, row);
});

test('successive changes preserve non-recursive chronological snapshots', () => {
  const old = requirement({status: 'met', source_id: first.id, source_url: first.url,
    source_quote: 'First wording.', checked_at: first.checked_at});
  const middle = selectRequirementSource(old, second).requirement;
  middle.source_quote = 'Second wording.'; middle.checked_at = second.checked_at;
  const result = selectRequirementSource(middle, first).requirement;
  assert.equal(result.source_history.length, 2);
  assert.deepEqual(result.source_history[0].record, old);
  const previous = {...middle}; delete previous.source_history;
  assert.deepEqual(result.source_history[1].record, previous);
  assert.equal(Object.hasOwn(result.source_history[1].record, 'source_history'), false);
  result.source_history[0].record.source_quote = 'Changed copy only.';
  assert.equal(middle.source_history[0].record.source_quote, 'First wording.');
});

test('first link invalidates an existing manual met assessment without erasing its note', () => {
  const row = requirement({status: 'met', source_url: 'https://example.invalid/manual',
    source_quote: 'Previously reviewed manual wording.', checked_at: '2026-09-20'});
  const result = selectRequirementSource(row, second);
  assert.equal(result.requirement.status, 'unknown');
  assert.equal(result.requirement.evidence, note);
  assert.equal(result.requirement.source_quote, '');
  assert.equal(result.resetAssessment, true);
});

test('selecting the same source preserves its quote, assessment and retained older date', () => {
  const row = requirement({status: 'met', source_id: first.id, source_url: first.url,
    source_quote: 'Exact retained wording. e\u0301 🐝', checked_at: '2026-09-10'});
  const result = selectRequirementSource(row, first);
  assert.deepEqual(result.requirement, row);
  assert.notEqual(result.requirement, row);
  assert.equal(result.changedSource, false);
  assert.equal(result.resetAssessment, false);
});

test('a source with no recorded date stays undated and unrelated requirement fields survive', () => {
  const source = Object.freeze({...second, checked_at: ''});
  const row = requirement({status: 'unknown', future_metadata: Object.freeze({owner: 'unassigned'})});
  const result = selectRequirementSource(row, source);
  assert.equal(result.requirement.checked_at, '');
  assert.equal(result.requirement.evidence, note);
  assert.equal(result.requirement.future_metadata, row.future_metadata);
  assert.equal(source.checked_at, '');
});

test('clearing an already unlinked requirement does not discard manual source details', () => {
  const row = requirement({source_url: 'https://example.invalid/manual',
    source_quote: 'Exact manual wording.', checked_at: '2026-09-20'});
  const result = selectRequirementSource(row, null);
  assert.deepEqual(result.requirement, row);
  assert.equal(result.changedSource, false);
});
