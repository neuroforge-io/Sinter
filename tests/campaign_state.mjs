import assert from 'node:assert/strict';
import {ACTIONABLE_OPPORTUNITY_STATES, isOpportunityActionable}
  from '../src/sinter/web/campaign-state.js';

const expected = ['researching', 'open', 'upcoming', 'clarification'];
assert.deepEqual(ACTIONABLE_OPPORTUNITY_STATES, expected);
for (const status of expected) assert.equal(isOpportunityActionable(status), true, status);
for (const status of ['paused', 'not_pursuing', 'submitted', 'closed']) {
  assert.equal(isOpportunityActionable(status), false, status);
}
assert.equal(isOpportunityActionable('unknown-status'), false);
console.log('campaign state policy: 9 checks passed');
