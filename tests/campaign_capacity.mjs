import test from 'node:test';
import assert from 'node:assert/strict';
import {campaignCapacity, CAMPAIGN_TEXT_LIMIT, CAMPAIGN_BYTE_LIMIT}
  from '../src/sinter/web/campaign-capacity.js';

test('nested products and snapshot copies count once per retained occurrence', () => {
  const document = Object.freeze({signatory: 'A🌱', assets: Object.freeze([
    Object.freeze({name: 'B', notes: 'same', references: Object.freeze([
      Object.freeze({notes: 'same'})])})])});
  assert.equal(campaignCapacity(document).characters, 11);
  assert.equal(campaignCapacity(document).state, 'within');
});
test('code points, UTF-8 bytes and JSON punctuation have distinct budgets', () => {
  const result = campaignCapacity({title: '🌱'.repeat(100)});
  assert.equal(result.characters, 100);
  assert.equal(result.bytes, 412);
});
test('near and exact text boundaries warn before the final server validation', () => {
  assert.equal(campaignCapacity({notes: 'x'.repeat(CAMPAIGN_TEXT_LIMIT * .9 - 1)}).state, 'within');
  assert.equal(campaignCapacity({notes: 'x'.repeat(CAMPAIGN_TEXT_LIMIT * .9)}).state, 'near');
  assert.equal(campaignCapacity({notes: '🌱'.repeat(CAMPAIGN_TEXT_LIMIT)}).state, 'near');
  assert.equal(campaignCapacity({notes: 'x'.repeat(CAMPAIGN_TEXT_LIMIT + 1)}).state, 'over');
});
test('encoded budget also warns when keys and punctuation consume the space', () => {
  const document = {["key".repeat(340_000)]: ''};
  const result = campaignCapacity(document);
  assert.equal(result.characters, 0);
  assert.ok(result.bytes > CAMPAIGN_BYTE_LIMIT);
  assert.equal(result.state, 'over');
});
