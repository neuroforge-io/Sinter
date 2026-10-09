import test from 'node:test';
import assert from 'node:assert/strict';
import {campaignBudgetRowState, campaignQuotedBudget, quotedAmount, QUOTED_BUDGET_NOTE}
  from '../src/sinter/web/campaign-budget.js';

test('mixed quote bases never become an application amount', () => {
  const rows = [
    {item: 'Fictional inclusive quote', quantity: 1, unit_cost: '110.00', quote_reference: 'Including GST'},
    {item: 'Fictional exclusive quote', quantity: 1, unit_cost: '100.00', quote_reference: 'Excluding GST'},
    {item: 'Production', quantity: 1, unit_cost: null, quote_reference: ''},
  ];
  const original = structuredClone(rows);
  const value = campaignQuotedBudget(rows);
  assert.equal(value.knownCents, 21000n);
  assert.equal(value.total, null);
  assert.equal(value.complete, false);
  assert.equal(value.nextIndex, 2);
  assert.match(value.label, /Recorded cost subtotal \(AUD\): A\$210\.00.*total incomplete/);
  assert.equal(value.amountBasisNote, QUOTED_BUDGET_NOTE);
  assert.match(value.amountBasisNote, /GST basis may be unknown or mixed/);
  assert.match(value.amountBasisNote, /not an eligibility or application-ceiling decision/);
  assert.deepEqual(rows, original);
});

test('zero is a recorded price; a blank budget has no complete zero total', () => {
  const empty = campaignQuotedBudget([]);
  assert.equal(empty.total, null);
  assert.equal(empty.complete, false);
  const value = campaignQuotedBudget([{quantity: 2, unit_cost: '0', quote_reference: 'Volunteer estimate'}]);
  assert.equal(value.total, 0n);
  assert.equal(value.complete, true);
  assert.equal(value.nextIndex, -1);
  assert.equal(value.label, 'Recorded cost subtotal (AUD): A$0.00');
});

test('planning estimates keep their references without becoming supplier quotes or a grant request', () => {
  const rows = [1000, 2000, 3000, 1500, 2500, 1000, 1500, 1000, 1500].map((cost, index) => ({
    item: `Fictional planning cost ${index + 1}`,
    quantity: 1,
    unit_cost: `${cost}.00`,
    quote_reference: `Planning estimate ${index + 1} e\u0301 🐝; quote required; GST unspecified`,
  }));
  const original = structuredClone(rows);
  const value = campaignQuotedBudget(rows);
  assert.equal(value.knownCents, 1500000n);
  assert.equal(value.total, 1500000n);
  assert.equal(value.unknownCosts, 0);
  assert.equal(value.missingReferences, 0);
  assert.equal(value.label, 'Recorded cost subtotal (AUD): A$15,000.00');
  assert.match(value.amountBasisNote, /may be quotes or planning estimates/);
  assert.match(value.amountBasisNote, /grant request and applicant cash or in-kind contributions separately/);
  assert.match(value.amountBasisNote, /subtotal does not establish them/);
  assert.ok(rows.every(row => campaignBudgetRowState(row).reference === 'Reference recorded · unverified'));
  assert.deepEqual(rows, original);
});

test('integer cents preserve quantity and the admitted maximum exactly', () => {
  const value = campaignQuotedBudget([
    {quantity: 3, unit_cost: '0.10', quote_reference: 'Example'},
    {quantity: 100000, unit_cost: '1000000000.00', quote_reference: 'Maximum test'},
  ]);
  assert.equal(value.knownCents, 10000000000000030n);
  assert.equal(quotedAmount(value.knownCents), 'A$100,000,000,000,000.30');
});

test('missing references remain useful next work even when the amount is priced', () => {
  const value = campaignQuotedBudget([
    {quantity: 1, unit_cost: '25', quote_reference: '   '},
    {quantity: 1, unit_cost: '50', quote_reference: 'Supplier estimate'}]);
  assert.equal(value.missingReferences, 1);
  assert.equal(value.nextIndex, 0);
  assert.equal(campaignBudgetRowState({quantity: 1, unit_cost: '25'}).reference, 'Reference needed');
});

for (const unit_cost of [null, '', undefined, true, '-1', '1e2', '1.001', '1000000000.01', '9'.repeat(31)]) {
  test(`invalid draft cost ${String(unit_cost).slice(0, 35)} stays unknown`, () => {
    const value = campaignQuotedBudget([{quantity: 1, unit_cost, quote_reference: ''}]);
    assert.equal(value.total, null);
    assert.equal(value.unknownCosts, 1);
    assert.equal(value.nextIndex, 0);
  });
}
for (const quantity of [null, '', undefined, true, 0, -1, 1.5, 100001, '0000001']) {
  test(`invalid draft quantity ${String(quantity)} stays unknown`, () => {
    const value = campaignBudgetRowState({quantity, unit_cost: '5.00'});
    assert.equal(value.lineCents, null);
    assert.equal(value.amount, 'Quantity needs checking');
  });
}
