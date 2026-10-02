import assert from 'node:assert/strict';
import test from 'node:test';
import {createFundingSummaryState, editFundingTracking, FUNDING_AMOUNT_KEYS,
  fundingGroupText, fundingReferencesSource, fundingTrackingView,
  selectFundingAmountSource, selectFundingClaimSource} from '../src/sinter/web/campaign-funding.js';

const packet = marker => ({schema: 'sinter-funding-summary/v1', marker});

test('viewing legacy ceilings does not add tracking or infer status, benefit or currency', () => {
  const legacy = {name: 'Fictional route', route_type: 'cash_grant', status: 'submitted',
    ceiling: '10000', ceiling_currency: 'AUD'};
  const before = structuredClone(legacy), view = fundingTrackingView(legacy);
  assert.deepEqual(legacy, before);
  assert.equal(Object.hasOwn(legacy, 'funding_tracking'), false);
  assert.equal(view.round_key, '');
  for (const key of ['benefit_type', 'eligibility', 'ceiling_scope', 'application_status',
    'award_status', 'receipt_status', 'closure_reason']) assert.equal(view[key], 'unknown');
  for (const key of FUNDING_AMOUNT_KEYS) {
    assert.equal(view[key].amount, null);
    assert.equal(view[key].currency, 'unconfirmed');
  }
  view.target.amount = '123.45';
  assert.deepEqual(legacy, before);
});

test('a deliberate edit creates tracking while preserving explicit zero and decimal text', () => {
  const row = {name: 'Fictional programme'};
  editFundingTracking(row, ['target', 'amount'], '0');
  assert.equal(row.funding_tracking.target.amount, '0');
  assert.equal(row.funding_tracking.target.currency, 'unconfirmed');
  assert.equal(row.funding_tracking.award_status, 'unknown');
  editFundingTracking(row, ['requested', 'amount'], '1000000000.00');
  editFundingTracking(row, ['requested', 'currency'], 'USD');
  editFundingTracking(row, ['target', 'amount'], null);
  assert.equal(row.funding_tracking.target.amount, null);
  assert.equal(row.funding_tracking.requested.amount, '1000000000.00');
  assert.equal(row.funding_tracking.requested.currency, 'USD');
  assert.deepEqual(JSON.parse(JSON.stringify(row)), row);
});

test('editing one field preserves existing amount provenance and other recorded stages', () => {
  const row = {funding_tracking: {benefit_type: 'credits', received: {
    amount: '500.25', currency: 'USD', source_id: 'a'.repeat(32),
    source_url: 'https://example.invalid/receipt', source_quote: 'Fictional receipt.',
    checked_at: '2026-10-02', notes: 'Fictional cumulative receipt only.'}}};
  const before = structuredClone(row.funding_tracking.received);
  const view = fundingTrackingView(row);
  view.received.notes = 'Detached preview';
  editFundingTracking(row, ['target', 'amount'], '25.50');
  assert.deepEqual(row.funding_tracking.received, before);
  assert.equal(row.funding_tracking.benefit_type, 'credits');
  assert.equal(row.funding_tracking.target.currency, 'unconfirmed');
});

test('changed claim source clears wording/date without importing a checked date or asserting eligibility', () => {
  const row = {};
  editFundingTracking(row, ['eligibility_evidence', 'evidence'], 'Fictional explanatory note');
  selectFundingClaimSource(row, 'eligibility_evidence', {id: 'a'.repeat(32),
    url: 'https://example.invalid/first', checked_at: '2026-10-02'});
  assert.equal(row.funding_tracking.eligibility_evidence.checked_at, '');
  assert.equal(row.funding_tracking.eligibility, 'unknown');
  editFundingTracking(row, ['eligibility_evidence', 'source_quote'], 'Fictional wording');
  editFundingTracking(row, ['eligibility_evidence', 'checked_at'], '2026-10-02');
  assert.equal(selectFundingClaimSource(row, 'eligibility_evidence', {id: 'a'.repeat(32),
    url: 'https://example.invalid/first'}), false);
  assert.equal(row.funding_tracking.eligibility_evidence.source_quote, 'Fictional wording');
  assert.equal(selectFundingClaimSource(row, 'eligibility_evidence', {id: 'a'.repeat(32),
    url: 'https://example.invalid/revised'}), true);
  assert.equal(row.funding_tracking.eligibility_evidence.source_quote, '');
  assert.equal(row.funding_tracking.eligibility_evidence.checked_at, '');
  assert.equal(row.funding_tracking.eligibility_evidence.evidence, 'Fictional explanatory note');
  assert.equal(selectFundingClaimSource(row, 'eligibility_evidence', null), true);
  assert.equal(row.funding_tracking.eligibility_evidence.source_url, '');
});

test('all amount and availability claim links protect their saved campaign sources', () => {
  for (const key of [...FUNDING_AMOUNT_KEYS, 'eligibility_evidence', 'ceiling_evidence']) {
    const row = {funding_tracking: {[key]: {source_id: 'b'.repeat(32)}}};
    assert.equal(fundingReferencesSource(row, 'b'.repeat(32)), true, key);
    assert.equal(fundingReferencesSource(row, 'c'.repeat(32)), false, key);
  }
  assert.equal(fundingReferencesSource({}, 'b'.repeat(32)), false);
});

test('amount source selection copies metadata, clears obsolete wording and preserves cumulative amount', () => {
  const row = {};
  editFundingTracking(row, ['received', 'amount'], '500.25');
  selectFundingAmountSource(row, 'received', {id: 'a'.repeat(32),
    url: 'https://example.invalid/receipt', checked_at: '2026-10-02',
    notes: 'These fictional page notes must not become an exact amount quote.'});
  assert.equal(row.funding_tracking.received.checked_at, '2026-10-02');
  assert.equal(row.funding_tracking.received.source_quote, '');
  assert.equal(row.funding_tracking.receipt_status, 'unknown');
  editFundingTracking(row, ['received', 'source_quote'], 'Fictional USD 500.25 receipt');
  selectFundingAmountSource(row, 'received', {id: 'b'.repeat(32),
    url: 'https://example.invalid/revised-receipt', checked_at: '2026-10-03'});
  assert.equal(row.funding_tracking.received.source_quote, '');
  assert.equal(row.funding_tracking.received.checked_at, '2026-10-03');
  assert.equal(row.funding_tracking.received.amount, '500.25');
  selectFundingAmountSource(row, 'received', null);
  assert.equal(row.funding_tracking.received.source_url, '');
  assert.equal(row.funding_tracking.received.checked_at, '');
});

test('edits retain a stale cached summary and reject delayed responses for the previous document', () => {
  const state = createFundingSummaryState(), accepted = state.begin();
  assert.equal(state.accept(accepted, packet('first')), true);
  assert.equal(state.finish(accepted), true);
  const delayed = state.begin();
  state.edited();
  assert.equal(state.stale, true);
  assert.equal(state.accept(delayed, packet('obsolete')), false);
  assert.equal(state.summary.marker, 'first');
  assert.equal(state.finish(delayed), true);
  assert.equal(state.pending, false);
  const current = state.begin();
  assert.equal(state.accept(current, packet('current')), true);
  assert.equal(state.stale, false);
});

test('new requests, campaign replacement and close/reopen reject old summary replies', () => {
  const state = createFundingSummaryState(), old = state.begin(), newer = state.begin();
  assert.equal(state.accept(old, packet('old request')), false);
  assert.equal(state.finish(old), false);
  assert.equal(state.pending, true);
  assert.equal(state.accept(newer, packet('latest request')), true);
  state.reset();
  assert.equal(state.summary, null);
  assert.equal(state.accept(newer, packet('old campaign')), false);
  const closing = state.begin(); state.close();
  assert.equal(state.accept(closing, packet('closed view')), false);
  assert.equal(state.finish(closing), false);
  const reopened = createFundingSummaryState(), live = reopened.begin();
  assert.equal(reopened.accept(closing, packet('old view')), false);
  assert.equal(reopened.finish(closing), false);
  assert.equal(reopened.accept(live, packet('reopened')), true);
});

test('unexpected summary schemas leave the cached summary intact', () => {
  const state = createFundingSummaryState(), first = state.begin();
  state.accept(first, packet('retained')); state.finish(first);
  const next = state.begin();
  assert.throws(() => state.accept(next, {schema: 'another/v2'}), /not supported/);
  assert.equal(state.summary.marker, 'retained');
});

test('group labels present server decimals without computing totals or treating credits as cash', () => {
  const credits = fundingGroupText({benefit_type: 'credits', currency: 'USD',
    known_total: '1234567890.50', total: null});
  assert.equal(credits.label, 'Credits · USD');
  assert.equal(credits.known, 'USD 1,234,567,890.50 known subtotal');
  assert.match(credits.completeness, /unknown or excluded/);
  const unsupported = fundingGroupText({benefit_type: 'unknown', currency: 'unconfirmed',
    known_total: null, total: null});
  assert.match(unsupported.label, /Benefit not confirmed.*Currency not confirmed/);
  assert.equal(unsupported.known, 'Known subtotal unavailable');
  const zero = fundingGroupText({benefit_type: 'cash', currency: 'AUD',
    known_total: '0.00', total: '0.00'});
  assert.equal(zero.known, 'AUD 0.00 known subtotal');
  assert.match(zero.completeness, /complete/);
});
