import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignEvidenceCounts} from '../src/sinter/web/reports.js';

test('campaign evidence summary counts linked records and recorded excerpts once', () => {
  const campaign = {
    opportunities: [
      {window_source_id: 'source-a', window_source_quote: 'Rolling intake.'},
      {window_source_id: 'source-a', window_source_quote: '  '},
      {window_source_id: '', window_source_quote: 'Fixed date.'},
    ],
    requirements: [
      {source_id: 'source-a', source_quote: 'GST is required.'},
      {source_id: 'source-b', source_quote: ''},
      {source_url: 'https://example.test/rule', source_quote: 'ABN is required.'},
    ],
    assets: [{references: [
      {source_id: 'source-b', excerpt: 'A prior-art lead.'},
      {source_id: 'source-c', excerpt: ''},
    ]}],
  };

  assert.deepEqual(campaignEvidenceCounts(campaign), {sources: 3, excerpts: 4});
});

test('campaign evidence summary handles missing or malformed registers', () => {
  assert.deepEqual(campaignEvidenceCounts(null), {sources: 0, excerpts: 0});
  assert.deepEqual(campaignEvidenceCounts({opportunities: {}, requirements: null,
    assets: [{references: 'not an array'}]}), {sources: 0, excerpts: 0});
});
