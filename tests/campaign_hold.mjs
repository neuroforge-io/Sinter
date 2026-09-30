import assert from 'node:assert/strict';
import test from 'node:test';
import {isCampaignActionCurrent, isCampaignActionOpen} from '../src/sinter/web/campaign-state.js';
import {campaignDecision} from '../src/sinter/web/campaign-decision.js';
import {campaignActionRowsForCalendar, campaignActionRowsForPlan} from '../src/sinter/web/campaign-plan.js';

const row = Object.freeze({task: 'Retain the earlier scope 🐝', status: 'held',
  opportunity: 'Fictional route', scope_confirmed: true, submission_phase: 'pre_submission',
  owner: 'Example role', owner_kind: 'role', owner_confirmed: false, due: '2026-09-01'});

test('held work is excluded without changing canonical fields, even after route changes', () => {
  for (const status of ['open', 'clarification', 'closed', 'paused', 'submitted']) {
    const routes = Object.freeze([Object.freeze({name: row.opportunity, status})]);
    assert.equal(isCampaignActionOpen(row), false);
    assert.equal(isCampaignActionCurrent(row, routes), false);
    assert.deepEqual(campaignActionRowsForCalendar([row], routes), []);
    const result = campaignDecision({opportunities: routes, actions: [row]}, '2026-09-30');
    assert.notEqual(result.action.source, 'recorded');
    assert.ok(!result.action.task.includes(row.task));
    assert.equal(row.status, 'held');
  }
});

test('held CSV adapter retains exact task, owner, date and status, not completion', () => {
  const [record] = campaignActionRowsForPlan([row], [{name: row.opportunity, status: 'open'}]);
  assert.equal(record.action, row.task);
  assert.equal(record.status, 'held');
  assert.equal(record.due, row.due);
  assert.match(record.owner, /Example role.*suggested role/);
});

test('explicit resume still respects scope and before/after-submission gates', () => {
  const resumed = {...row, status: 'open'};
  assert.equal(isCampaignActionCurrent(resumed, [{name: row.opportunity, status: 'open'}]), true);
  assert.equal(isCampaignActionCurrent(resumed, [{name: row.opportunity, status: 'closed'}]), false);
  assert.equal(isCampaignActionCurrent(resumed, [{name: row.opportunity, status: 'submitted'}]), false);
  assert.equal(isCampaignActionCurrent({...resumed, submission_phase: 'post_submission'},
    [{name: row.opportunity, status: 'submitted'}]), true);
  assert.equal(isCampaignActionCurrent({...resumed, scope_confirmed: false}, []), false);
  assert.equal(isCampaignActionCurrent({...resumed, opportunity: ''}, []), true);
});

test('held legacy scope needs no review until explicitly resumed and cannot win next action', () => {
  const held = {...row, opportunity: '', scope_confirmed: false};
  const current = {...row, status: 'open', task: 'Confirm the current scope', due: '', opportunity: ''};
  const decision = campaignDecision({opportunities: [{name: row.opportunity, status: 'open'}],
    actions: [held, current]}, '2026-09-30');
  assert.equal(decision.action.source, 'recorded');
  assert.equal(decision.action.actionIndex, 1);
  assert.equal(decision.action.task, current.task);
  assert.equal(isCampaignActionOpen({status: 'open'}), true);
  assert.equal(isCampaignActionOpen({status: 'done'}), false);
});
