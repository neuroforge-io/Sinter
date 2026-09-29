import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignDecision} from '../src/sinter/web/campaign-decision.js';

const goodCheck = {
  opportunity: 'Local fund', rule: 'Applicant type accepted', status: 'met',
  evidence: 'P&C applicant status confirmed in the current register.',
  source_url: 'https://example.org/rules',
  source_quote: 'Eligible applicants include school P&C associations.',
  checked_at: '2026-09-20',
};
const readyRoute = {
  name: 'Local fund', funder: 'Example', url: 'https://example.org/fund',
  deadline: '2026-10-30', status: 'open',
};

test('an empty campaign has no decision, owner or invented date', () => {
  const result = campaignDecision({}, '2026-09-29');
  assert.equal(result.state, 'not_assessed');
  assert.match(result.detail, /no go\/no-go decision yet/);
  assert.equal(result.action.source, 'suggested');
  assert.equal(result.action.ownerNeeded, true);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('closed routes produce a time-bounded no-go with evidence-led reopen criteria', () => {
  const result = campaignDecision({
    opportunities: [{...readyRoute, status: 'closed', deadline: '2026-09-28'}],
    requirements: [{...goodCheck, status: 'not_met',
      evidence: 'The applicant category is excluded by the current rule.'}],
  }, '2026-09-29');
  assert.equal(result.state, 'no_go');
  assert.equal(result.label, 'NO-GO FOR NOW');
  assert.match(result.reopenCriteria, /publishes a future round/);
  assert.match(result.reopenCriteria, /Applicant type accepted/);
  assert.match(result.reopenCriteria, /user-entered and unverified/);
});

test('submitted routes wait for a decision and never read as rejected or awarded', () => {
  const result = campaignDecision({opportunities: [{...readyRoute, status: 'submitted'}]},
    '2026-09-29');
  assert.equal(result.state, 'awaiting_decision');
  assert.match(result.detail, /not an award or a rejection/);
  assert.match(result.action.task, /Record the funder’s decision/);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('an active but incompletely screened route is not ready and has no fabricated owner or date', () => {
  const input = {
    opportunities: [{...readyRoute, url: '', deadline: ''}],
    requirements: [{...goodCheck, status: 'unknown', source_quote: ''}],
    actions: [
      {task: 'Confirm applicant eligibility', owner: 'P&C Treasurer (unassigned)', due: '', status: 'open'},
      {task: 'Get a quote', owner: '', due: '2026-09-12', status: 'open'},
    ],
  };
  const original = JSON.stringify(input);
  const result = campaignDecision(input, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.equal(result.action.task, 'Get a quote');
  assert.equal(result.action.ownerNeeded, true);
  assert.match(result.action.ownerStatus, /Owner needed/);
  assert.equal(result.action.due, '2026-09-12');
  assert.match(result.reopenCriteria, /current official wording/);
  assert.equal(JSON.stringify(input), original);
});

test('complete user-entered screening is labelled ready for human review only', () => {
  const result = campaignDecision({
    opportunities: [readyRoute], requirements: [goodCheck],
    actions: [{task: 'P&C review of evidence', owner: 'Casey Example',
      owner_confirmed: true, due: '2026-10-01', status: 'open'}],
  }, '2026-09-29');
  assert.equal(result.state, 'ready_for_review');
  assert.equal(result.label, 'READY FOR HUMAN REVIEW');
  assert.match(result.detail, /not verified/);
  assert.match(result.detail, /not clearance to apply/);
  assert.match(result.action.ownerStatus, /Acceptance recorded by user/);
  assert.equal(result.action.due, '2026-10-01');
  assert.match(result.reopenCriteria, /before any submission/);
});

test('a past date on a route still marked open requires status confirmation', () => {
  const result = campaignDecision({
    opportunities: [{...readyRoute, deadline: '2026-09-28'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /Confirm the current official programme page/);
  assert.match(result.reopenCriteria, /closing date \(2026-09-28\) has passed/);
});

test('an active route with no eligibility checks gets a specific, evidence-led next step', () => {
  const result = campaignDecision({
    opportunities: [readyRoute], requirements: [],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /Record the applicant eligibility checks/);
  assert.match(result.reopenCriteria, /No applicant eligibility checks are recorded/);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('a route marked needs clarification does not imply that the programme round is closed', () => {
  const result = campaignDecision({
    opportunities: [{...readyRoute, status: 'clarification'}],
    requirements: [{...goodCheck, status: 'clarification', source_quote: ''}],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /outstanding clarification/);
  assert.doesNotMatch(result.reopenCriteria, /Confirm the route is open/);
  assert.match(result.reopenCriteria, /outstanding programme clarification/);
});

test('a route with an unresolved clarification cannot be ready even when every check is complete', () => {
  const result = campaignDecision({
    opportunities: [{...readyRoute, status: 'clarification'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.equal(result.label, 'NOT READY');
  assert.match(result.detail, /Local fund.*not ready.*outstanding programme clarification/);
  assert.match(result.action.task, /Resolve the outstanding clarification for “Local fund”/);
  assert.match(result.reopenCriteria, /outstanding programme clarification/);
});

test('a researching route requires confirmation of a current live round', () => {
  const result = campaignDecision({
    opportunities: [{...readyRoute, status: 'researching'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.reopenCriteria, /current official wording.*current round is open/);
});

test('the selected route controls its suggested action and reopen evidence gate', () => {
  const nbn = {...readyRoute, name: 'NBN community grant'};
  const ruic = {...readyRoute, name: 'CSIRO RUIC', status: 'open'};
  const result = campaignDecision({
    opportunities: [nbn, ruic],
    requirements: [
      {opportunity: nbn.name, rule: 'Applicant location is regional or remote', status: 'unknown'},
      {opportunity: ruic.name, rule: 'Company operating-age rule', status: 'clarification'},
    ],
  }, '2026-09-29', ruic.name);
  assert.equal(result.focusOpportunity, ruic.name);
  assert.match(result.action.task, /Company operating-age rule/);
  assert.match(result.reopenCriteria, /Company operating-age rule/);
  assert.doesNotMatch(result.action.task, /regional or remote/i);
  assert.doesNotMatch(result.reopenCriteria, /regional or remote/i);
});

test('an incomplete selected route stays not ready when another route is complete', () => {
  const focused = {...readyRoute, name: 'Focused route'};
  const complete = {...readyRoute, name: 'Other complete route'};
  const result = campaignDecision({
    opportunities: [focused, complete],
    requirements: [
      {...goodCheck, opportunity: focused.name, rule: 'Focused route eligibility', status: 'unknown', source_quote: ''},
      {...goodCheck, opportunity: complete.name},
    ],
  }, '2026-09-29', focused.name);
  assert.equal(result.state, 'not_ready');
  assert.equal(result.label, 'NOT READY');
  assert.equal(result.focusOpportunity, focused.name);
  assert.match(result.detail, /Focused route.*not ready.*Focused route eligibility/);
  assert.match(result.action.task, /Focused route eligibility/);
  assert.match(result.reopenCriteria, /Focused route eligibility/);
  assert.doesNotMatch(result.detail, /Other complete route/);
  assert.doesNotMatch(result.action.task, /Other complete route/);
  assert.doesNotMatch(result.reopenCriteria, /Other complete route/);
});
