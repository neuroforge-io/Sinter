import assert from 'node:assert/strict';
import test from 'node:test';
import {CAMPAIGN_OPPORTUNITY_LIMIT, OPPORTUNITY_PAGE_SIZE,
  canAddCampaignOpportunity, campaignOpportunityView}
  from '../src/sinter/web/campaign-opportunity-view.js';

const fixtures = count => Array.from({length: count}, (_, index) => ({
  name: `Fictional route ${String(index + 1).padStart(2, '0')}`,
  funder: index % 2 ? 'Example Foundation' : 'Example Community Fund',
  status: index % 2 ? 'closed' : 'open',
  route_type: 'cash_grant', url: `https://example.invalid/round_${index + 1}`,
  fit: 'Fictional saved fit note; no new claims are inferred.',
}));

test('default and subsequent pages retain original row references/indexes without clipping data', () => {
  const rows = fixtures(35), before = structuredClone(rows);
  const first = campaignOpportunityView(rows), second = campaignOpportunityView(rows, {page: 1});
  assert.equal(OPPORTUNITY_PAGE_SIZE, 20);
  assert.equal(first.total, 35); assert.equal(first.matched, 35);
  assert.equal(first.pages, 2); assert.equal(first.entries.length, 20);
  assert.deepEqual(first.entries.map(entry => entry.index), Array.from({length: 20}, (_, index) => index));
  assert.equal(second.entries.length, 15); assert.equal(second.start, 21); assert.equal(second.end, 35);
  assert.equal(second.entries[14].index, 34);
  assert.equal(second.entries[14].row, rows[34]);
  assert.deepEqual(rows, before);
});

test('name/funder/notes/status classification search is case-insensitive and presentation-only', () => {
  const rows = fixtures(35), before = structuredClone(rows);
  assert.deepEqual(campaignOpportunityView(rows, {query: '  ROUTE 35  '}).entries.map(row => row.index), [34]);
  assert.equal(campaignOpportunityView(rows, {query: 'example foundation'}).matched, 17);
  assert.equal(campaignOpportunityView(rows, {query: 'saved fit note'}).matched, 35);
  assert.equal(campaignOpportunityView(rows, {query: 'cash grant'}).matched, 35);
  assert.equal(campaignOpportunityView(rows, {query: 'round_35'}).entries[0].index, 34);
  assert.deepEqual(rows, before);
});

test('status filter and search keep canonical indexes rather than assigning visible positions', () => {
  const rows = fixtures(65), before = structuredClone(rows);
  const closed = campaignOpportunityView(rows, {status: 'closed', page: 1});
  assert.equal(closed.total, 65); assert.equal(closed.matched, 32);
  assert.equal(closed.entries[0].index, 41);
  assert.equal(closed.entries[0].row, rows[41]);
  assert.deepEqual(campaignOpportunityView(rows, {query: 'route 42', status: 'open'}).entries, []);
  assert.deepEqual(campaignOpportunityView(rows, {query: 'route 42', status: 'closed'}).entries.map(row => row.index), [41]);
  assert.deepEqual(rows, before);
});

test('empty results and stale/out-of-range page requests are bounded and retain the full total', () => {
  const rows = fixtures(35), empty = campaignOpportunityView(rows, {query: 'no such fictional route', page: 900});
  assert.equal(empty.total, 35); assert.equal(empty.matched, 0);
  assert.equal(empty.page, 0); assert.equal(empty.pages, 0);
  assert.equal(empty.start, 0); assert.equal(empty.end, 0);
  assert.deepEqual(empty.entries, []);
  assert.equal(campaignOpportunityView(rows, {page: 900}).page, 1);
  for (const page of [-1, 1.5, '1', NaN, Infinity]) {
    assert.equal(campaignOpportunityView(rows, {page}).page, 0);
  }
  assert.equal(rows.length, 35);
});

test('all 200 bounded routes remain available across ten pages and add admission stops at the cap', () => {
  assert.equal(CAMPAIGN_OPPORTUNITY_LIMIT, 200);
  const rows = fixtures(CAMPAIGN_OPPORTUNITY_LIMIT), found = [];
  for (let page = 0; page < 10; page++) {
    const view = campaignOpportunityView(rows, {page});
    assert.equal(view.entries.length, 20);
    assert.equal(view.total, 200);
    found.push(...view.entries.map(row => row.index));
  }
  assert.deepEqual(found, Array.from({length: 200}, (_, index) => index));
  assert.equal(canAddCampaignOpportunity(rows.slice(0, 199)), true);
  assert.equal(canAddCampaignOpportunity(rows), false);
  assert.equal(canAddCampaignOpportunity([...rows, rows[0]]), false);
  assert.equal(rows.length, 200);
});

test('absent rows produce an empty view without synthesising or mutating a document', () => {
  assert.deepEqual(campaignOpportunityView(undefined), {entries: [], matchedIndexes: [],
    total: 0, matched: 0, page: 0, pages: 0, start: 0, end: 0});
  assert.equal(canAddCampaignOpportunity([]), true);
});
