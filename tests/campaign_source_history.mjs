import assert from 'node:assert/strict';
import test from 'node:test';
import {assetSourceReplacement, sourceHistoryReferences, sourceHistoryCount, captureSourceReplacementGuard}
  from '../src/sinter/web/campaign-source-history.js';

const oldSource = {id: '1'.repeat(32), title: 'Old public source',
  url: 'https://example.invalid/old', checked_at: '2026-09-12'};
const newSource = {id: '2'.repeat(32), title: 'New public source',
  url: 'https://example.invalid/new', checked_at: '2026-10-09'};
const reference = {kind: 'prior_art', source_id: oldSource.id, title: oldSource.title,
  url: oldSource.url, excerpt: 'Old café 中文 e\u0301 🐝\r\n<literal>',
  checked_at: oldSource.checked_at, notes: 'A lead only. Nothing established.'};
const asset = {stage: 'released', prior_art_status: 'preliminary_screen',
  prior_art_checked_at: '2026-09-12', rights_status: 'records_to_check',
  contributors_status: 'unknown', disclosure_status: 'date_recorded', first_public_date: '2026-08-01'};

test('replacing a product reference archives its exact record and related assessment only', () => {
  const before = structuredClone({reference, asset});
  const result = assetSourceReplacement(reference, newSource, asset);
  assert.deepEqual(result.assetChanges, {prior_art_status: 'not_started', prior_art_checked_at: ''});
  assert.deepEqual(result.reference.source_history, [{state: 'historical', reason: 'replaced',
    record: reference, assessment: {status_field: 'prior_art_status', status: 'preliminary_screen',
      date_field: 'prior_art_checked_at', date: '2026-09-12'}}]);
  assert.equal(result.reference.source_id, newSource.id);
  assert.equal(result.reference.title, newSource.title);
  assert.equal(result.reference.url, newSource.url);
  assert.equal(result.reference.excerpt, '');
  assert.equal(result.reference.checked_at, '');
  assert.equal(result.reference.notes, reference.notes);
  assert.deepEqual({reference, asset}, before);
});

test('an unchanged selection is a no-op even when the source register date changed', () => {
  const result = assetSourceReplacement(reference, {...oldSource, checked_at: '2026-10-09'}, asset);
  assert.equal(result.changedSource, false);
  assert.deepEqual(result.reference, reference);
  assert.deepEqual(result.assetChanges, {});
});

test('a refreshed title or URL at the same source ID retains the previous snapshot', () => {
  for (const source of [{...oldSource, title: 'Refreshed title'}, {...oldSource, url: newSource.url}]) {
    const result = assetSourceReplacement(reference, source, asset);
    assert.equal(result.changedSource, true);
    assert.deepEqual(result.reference.source_history[0].record, reference);
    assert.equal(result.reference.checked_at, '');
  }
});

test('clearing retains history and never leaves old wording attached as current evidence', () => {
  const result = assetSourceReplacement(reference, null, asset);
  assert.equal(result.reference.source_id, '');
  assert.equal(result.reference.url, '');
  assert.equal(result.reference.excerpt, '');
  assert.equal(result.reference.checked_at, '');
  assert.equal(result.reference.source_history[0].reason, 'cleared');
  assert.equal(sourceHistoryReferences(result.reference, oldSource.id), true);
  assert.equal(sourceHistoryReferences(result.reference, newSource.id), false);
  assert.equal(sourceHistoryCount([result.reference]), 2);
  assert.equal(sourceHistoryCount([reference]), 1);
});

test('all IP workstreams capture their old assessment without changing other fields', () => {
  for (const [kind, field, initial, dateField] of [
    ['contributors', 'contributors_status', 'unknown'], ['rights', 'rights_status', 'unknown'],
    ['disclosure', 'disclosure_status', 'unknown', 'first_public_date'],
    ['prior_art', 'prior_art_status', 'not_started', 'prior_art_checked_at'],
  ]) {
    const result = assetSourceReplacement({...reference, kind}, newSource, asset);
    assert.equal(result.assetChanges[field], initial);
    assert.equal(result.reference.source_history[0].assessment.status, asset[field]);
    assert.equal(Object.hasOwn(result.assetChanges, 'stage'), false);
    if (dateField) assert.equal(result.assetChanges[dateField], '');
    assert.equal(Object.keys(result.assetChanges).length, dateField ? 2 : 1);
  }
});

test('first linking an empty reference does not manufacture an earlier historical record', () => {
  const empty = {kind: 'other', source_id: '', title: '', url: '', excerpt: '', checked_at: '', notes: ''};
  const result = assetSourceReplacement(empty, newSource, asset);
  assert.equal(Object.hasOwn(result.reference, 'source_history'), false);
  assert.equal(result.reference.checked_at, '');
  assert.deepEqual(result.assetChanges, {});
  assert.deepEqual(assetSourceReplacement(empty, null, asset).reference, empty);
});

test('first linking an empty IP reference preserves a sibling-supported assessment and date', () => {
  const empty = {kind: 'prior_art', source_id: '', title: '', url: '', excerpt: '', checked_at: '', notes: ''};
  const product = {...structuredClone(asset), references: [structuredClone(reference), empty]};
  const before = structuredClone(product);
  const result = assetSourceReplacement(empty, newSource, product);
  assert.deepEqual(result.assetChanges, {});
  assert.equal(Object.hasOwn(result.reference, 'source_history'), false);
  assert.equal(result.reference.source_id, newSource.id);
  assert.equal(result.reference.excerpt, '');
  assert.equal(result.reference.checked_at, '');
  assert.deepEqual(product, before);
});

test('delayed selection approval belongs to the exact live editor document and row', () => {
  const row = {source_id: ''};
  const original = {requirements: [row], assets: []};
  let current = original, active = true;
  const guard = captureSourceReplacementGuard(original, row, () => current, () => active);
  assert.equal(guard(), true);
  // An identical Save/apply result is a different editor, not this approval.
  current = structuredClone(original);
  assert.equal(guard(), false);
  current = original; active = false;
  assert.equal(guard(), false);
  active = true; original.requirements = [{...row}];
  assert.equal(guard(), false);
});

test('product selection approval requires the original owning asset and reference', () => {
  const row = {source_id: ''}, product = {references: [row]};
  const original = {requirements: [], assets: [product]};
  const guard = captureSourceReplacementGuard(original, row, () => original, () => true, product);
  assert.equal(guard(), true);
  product.references = [{...row}];
  assert.equal(guard(), false);
  product.references = [row]; original.assets = [{references: [row]}];
  assert.equal(guard(), false);
});

test('two ready admissions must recheck the exact values at their final commit boundary', async () => {
  const first = {source_id: ''}, second = {source_id: ''};
  const document = {requirements: [first, second], assets: []};
  const firstGuard = captureSourceReplacementGuard(document, first, () => document, () => true);
  const secondGuard = captureSourceReplacementGuard(document, second, () => document, () => true);
  const admissions = await Promise.all([Promise.resolve(firstGuard()), Promise.resolve(secondGuard())]);
  assert.deepEqual(admissions, [true, true]);
  assert.equal(firstGuard(), true);
  first.source_id = 'first explicitly applied selection';
  assert.equal(secondGuard(), false);
  assert.equal(second.source_id, '');
});
