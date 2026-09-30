import assert from 'node:assert/strict';
import test from 'node:test';
import {CEILING_CURRENCY_OPTIONS, campaignCeilingCurrency,
  campaignFundingAmount, campaignCurrencyComparisonNote} from '../src/sinter/web/campaign-currency.js';
import {campaignDecision} from '../src/sinter/web/campaign-decision.js';

test('absent AUD remains legacy AUD; all other denominations are explicit', () => {
  assert.equal(campaignCeilingCurrency({}), 'AUD');
  assert.equal(campaignFundingAmount({ceiling: '50000'}), 'Up to A$50,000');
  assert.equal(campaignFundingAmount({ceiling: '50000.50', ceiling_currency: 'USD'}),
    'Up to USD 50,000.50');
  for (const [value] of CEILING_CURRENCY_OPTIONS) {
    assert.equal(campaignCeilingCurrency({ceiling_currency: value}), value);
  }
  for (const value of [null, true, [], 'usd', 'JPY', '']) {
    assert.throws(() => campaignCeilingCurrency({ceiling_currency: value}));
  }
});

test('mismatched funding currencies are not represented as project AUD amounts', () => {
  for (const currency of ['USD', 'EUR', 'GBP', 'NZD', 'CAD', 'unconfirmed', 'other']) {
    const row = {ceiling: '50000', ceiling_currency: currency};
    assert.doesNotMatch(campaignFundingAmount(row), /A\$/);
    assert.match(campaignCurrencyComparisonNote(row), /project costs are AUD/);
    assert.match(campaignCurrencyComparisonNote(row), /No currency conversion or ceiling comparison/);
  }
  assert.match(campaignFundingAmount({ceiling: '0', ceiling_currency: 'unconfirmed'}),
    /0 \(currency unconfirmed\)/);
  assert.match(campaignFundingAmount({ceiling: null, ceiling_currency: 'other'}),
    /other currency \(unsupported\)/);
  assert.equal(campaignCurrencyComparisonNote({ceiling: null, ceiling_currency: 'USD'}), '');
  assert.equal(campaignCurrencyComparisonNote({ceiling: '50000'}), '');
  assert.equal(campaignFundingAmount({route_type: 'non_cash_support', ceiling: '50000',
    ceiling_currency: 'USD'}), 'No grant cash');
  assert.equal(campaignCurrencyComparisonNote({route_type: 'non_cash_support',
    ceiling: '50000', ceiling_currency: 'USD'}), '');
});

test('currency adds a review gap while retaining user unmet checks and recorded next actions', () => {
  const document = {opportunities: [{name: 'Fictional USD route', status: 'open',
    ceiling: '50000', ceiling_currency: 'USD'}], requirements: [{
    opportunity: 'Fictional USD route', rule: 'Recorded cash hold', status: 'not_met'}],
    actions: [{task: 'Recorded task must remain', owner: 'Example Person',
      owner_kind: 'person', owner_confirmed: true, scope_confirmed: true, status: 'open'}]};
  const before = JSON.stringify(document);
  const decision = campaignDecision(document, '2026-09-30');
  assert.match(decision.detail, /marked not met in the user-entered record/);
  assert.match(campaignCurrencyComparisonNote(document.opportunities[0]),
    /project costs are AUD/);
  assert.equal(decision.action.task, 'Recorded task must remain');
  assert.equal(JSON.stringify(document), before);
});

test('otherwise complete recorded screening retains a currency review blocker', () => {
  const source = {id: 'fictional-source', url: 'https://example.invalid/rules',
    checked_at: '2026-09-30'};
  const opportunity = {name: 'Fictional USD route', status: 'open',
    ceiling: '50000', ceiling_currency: 'USD', url: source.url,
    application_mode: 'not_required', application_window: 'rolling',
    window_source_id: source.id, window_source_url: source.url,
    window_source_quote: 'Fictional rolling applications only.',
    window_checked_at: source.checked_at};
  const input = {sources: [source], opportunities: [opportunity], requirements: [{
    opportunity: opportunity.name, rule: 'Fictional applicant rule', status: 'met',
    evidence: 'Fictional entered applicant record', source_id: source.id,
    source_url: source.url, source_quote: 'Fictional source wording.',
    checked_at: source.checked_at}], actions: []};
  const result = campaignDecision(input, '2026-09-30');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /project costs are AUD/);
  assert.match(result.action.task, /No currency conversion or ceiling comparison/);
  delete opportunity.ceiling_currency;
  assert.equal(campaignDecision(input, '2026-09-30').state, 'ready_for_review');
});
