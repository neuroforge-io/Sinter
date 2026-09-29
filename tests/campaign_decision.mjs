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
  deadline: '2026-10-30', application_window: 'fixed',
  window_source_id: 'a'.repeat(32),
  window_source_url: 'https://example.org/window',
  window_source_quote: 'Applications close at 5pm on 30 October 2026.',
  window_checked_at: '2026-09-29', status: 'open',
  application_mode: 'required', applicant: 'School P&C association',
};
const windowSource = {id: readyRoute.window_source_id,
  url: readyRoute.window_source_url, checked_at: '2026-09-29'};
const decide = (document, today, focusedOpportunityName = '') => campaignDecision({
  ...document,
  sources: document.sources || [windowSource],
}, today, focusedOpportunityName);

test('an empty campaign has no decision, owner or invented date', () => {
  const result = decide({}, '2026-09-29');
  assert.equal(result.state, 'not_assessed');
  assert.match(result.detail, /no go\/no-go decision yet/);
  assert.equal(result.action.source, 'suggested');
  assert.equal(result.action.ownerNeeded, true);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('closed routes produce a time-bounded no-go with evidence-led reopen criteria', () => {
  const result = decide({
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
  const result = decide({opportunities: [{...readyRoute, status: 'submitted'}]},
    '2026-09-29');
  assert.equal(result.state, 'awaiting_decision');
  assert.match(result.detail, /not an award or a rejection/);
  assert.match(result.action.task, /Record the funder’s decision/);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('submitted routes suppress pre-submission tasks until explicitly marked as follow-up', () => {
  const route = {...readyRoute, status: 'submitted'};
  const preSubmit = decide({
    opportunities: [route],
    actions: [{opportunity: route.name, task: 'Submit the application',
      status: 'open', due: '2026-10-01'}],
  }, '2026-09-29');
  assert.equal(preSubmit.state, 'awaiting_decision');
  assert.equal(preSubmit.action.source, 'suggested');
  assert.match(preSubmit.action.task, /Review 1 unfinished pre-submission action/);
  assert.doesNotMatch(preSubmit.action.task, /Submit the application/);

  const followUp = decide({
    opportunities: [route],
    actions: [{opportunity: route.name, submission_phase: 'post_submission',
      task: 'Record the funder decision', status: 'open', due: '2026-10-08'}],
  }, '2026-09-29');
  assert.equal(followUp.action.source, 'recorded');
  assert.equal(followUp.action.task, 'Record the funder decision');
});

test('an active but incompletely screened route is not ready and has no fabricated owner or date', () => {
  const input = {
    opportunities: [{...readyRoute, url: '', deadline: ''}],
    requirements: [{...goodCheck, status: 'unknown', source_quote: ''}],
    actions: [
      {opportunity: '', task: 'Confirm applicant eligibility', owner: 'P&C Treasurer (unassigned)', due: '', status: 'open'},
      {opportunity: '', task: 'Get a quote', owner: '', due: '2026-09-12', status: 'open'},
    ],
  };
  const original = JSON.stringify(input);
  const result = decide(input, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.equal(result.action.task, 'Get a quote');
  assert.equal(result.action.ownerNeeded, true);
  assert.match(result.action.ownerStatus, /Owner needed/);
  assert.equal(result.action.due, '2026-09-12');
  assert.match(result.reopenCriteria, /current official wording/);
  assert.equal(JSON.stringify(input), original);
});

test('complete user-entered screening clearly requires human review and remains unverified', () => {
  const result = decide({
    opportunities: [readyRoute], requirements: [goodCheck],
    actions: [{opportunity: '', task: 'P&C review of evidence', owner: 'Casey Example',
      owner_confirmed: true, due: '2026-10-01', status: 'open'}],
  }, '2026-09-29');
  assert.equal(result.state, 'ready_for_review');
  assert.equal(result.label, 'HUMAN REVIEW REQUIRED');
  assert.match(result.detail, /not verified/);
  assert.match(result.detail, /not clearance to apply/);
  assert.match(result.action.ownerStatus, /Acceptance recorded by user/);
  assert.equal(result.action.due, '2026-10-01');
  assert.match(result.reopenCriteria, /before any submission/);
});

test('an unknown application workflow blocks a route until its application lead is recorded', () => {
  const {application_mode, applicant, ...route} = readyRoute;
  const result = decide({opportunities: [route], requirements: [goodCheck]}, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /Confirm whether this route needs a formal application and who is allowed to apply/);
});

test('a required application without an identified applicant stays blocked', () => {
  const result = decide({
    opportunities: [{...readyRoute, applicant: ''}], requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /Record which organisation or person must submit the application/);
});

test('a past date on a route still marked open requires status confirmation', () => {
  const result = decide({
    opportunities: [{...readyRoute, deadline: '2026-09-28'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /recorded closing date.*has passed/);
  assert.match(result.reopenCriteria, /closing date \(2026-09-28\) has passed/);
});

test('a rolling application window can be ready without inventing a closing date', () => {
  const route = {
    ...readyRoute, deadline: '', application_window: 'rolling',
    window_source_quote: 'Applications are accepted all year round.',
    window_checked_at: '2026-09-29',
  };
  const result = decide({opportunities: [route], requirements: [goodCheck]},
    '2026-09-29');
  assert.equal(result.state, 'ready_for_review');
  assert.equal(result.focusOpportunity, route.name);
});

test('a rolling window still needs dated official wording before human review', () => {
  const route = {
    ...readyRoute, deadline: '', application_window: 'rolling',
    window_source_quote: '', window_checked_at: '',
  };
  const result = decide({opportunities: [route], requirements: [goodCheck]},
    '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /exact official wording that confirms the rolling application window/);
  assert.match(result.action.task, /application window/);
});

test('a source-window check older than 90 days needs refreshing', () => {
  const route = {
    ...readyRoute, application_window: 'rolling', deadline: '',
    window_source_quote: 'Applications are accepted all year round.',
    window_checked_at: '2026-06-30',
  };
  const result = decide({opportunities: [route], requirements: [goodCheck]},
    '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /checked 91 days ago; recheck the official wording/);
  assert.match(result.action.task, /application window/);
});

test('a source-window check exactly 90 days old is still current', () => {
  const route = {
    ...readyRoute, application_window: 'rolling', deadline: '',
    window_source_quote: 'Applications are accepted all year round.',
    window_checked_at: '2026-07-01',
  };
  const result = decide({opportunities: [route], requirements: [goodCheck],
    sources: [{...windowSource, checked_at: '2026-07-01'}]},
    '2026-09-29');
  assert.equal(result.state, 'ready_for_review');
});

test('a future-dated source-window check cannot qualify as current evidence', () => {
  const route = {
    ...readyRoute, application_window: 'rolling', deadline: '',
    window_source_quote: 'Applications are accepted all year round.',
    window_checked_at: '2026-09-30',
  };
  const result = decide({opportunities: [route], requirements: [goodCheck]},
    '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /check date \(2026-09-30\) is in the future/);
});

test('eligibility evidence checked in the future cannot qualify as current', () => {
  const result = decide({opportunities: [readyRoute],
    requirements: [{...goodCheck, checked_at: '2026-09-30'}]}, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /eligibility source check date \(2026-09-30\) is in the future/);
});

test('eligibility evidence becomes stale after 90 days but remains current on day 90', () => {
  const route = {...readyRoute, application_mode: 'required', applicant: 'Applicant'};
  const current = decide({opportunities: [route],
    requirements: [{...goodCheck, checked_at: '2026-07-01'}]}, '2026-09-29');
  assert.equal(current.state, 'ready_for_review');
  const stale = decide({opportunities: [route],
    requirements: [{...goodCheck, checked_at: '2026-06-30'}]}, '2026-09-29');
  assert.equal(stale.state, 'not_ready');
  assert.match(stale.detail, /eligibility source was last checked 91 days ago/);
});

test('an unknown application window is the next action before missing eligibility checks', () => {
  const route = {...readyRoute, deadline: '', application_window: 'unknown',
    window_source_quote: '', window_checked_at: ''};
  const result = decide({opportunities: [route], requirements: []},
    '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /Confirm whether applications use a fixed closing date or a rolling window/);
  assert.match(result.action.task, /Confirm whether applications use a fixed closing date or a rolling window/);
});

test('a fixed date needs its own dated source wording', () => {
  const route = {...readyRoute, window_source_quote: '', window_checked_at: ''};
  const result = decide({opportunities: [route], requirements: [goodCheck]},
    '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /exact official wording that confirms the closing date/);
});

test('the selected route gets its own recorded action before another route or global work', () => {
  const route = {...readyRoute, name: 'Focused route'};
  const result = decide({
    opportunities: [route, {...readyRoute, name: 'Other route'}],
    requirements: [{...goodCheck, opportunity: route.name}],
    actions: [
      {task: 'Other route overdue item', opportunity: 'Other route', due: '2026-09-01'},
      {task: 'Global asset register', opportunity: ''},
      {task: 'Focused eligibility check', opportunity: route.name},
    ],
  }, '2026-09-29', route.name);
  assert.equal(result.action.source, 'recorded');
  assert.equal(result.action.task, 'Focused eligibility check');
  assert.equal(result.action.opportunity, route.name);
});

test('campaign-wide actions outrank actions belonging to a different selected route', () => {
  const route = {...readyRoute, name: 'Focused route'};
  const result = decide({
    opportunities: [route, {...readyRoute, name: 'Other route'}],
    requirements: [{...goodCheck, opportunity: route.name}],
    actions: [
      {task: 'Other route overdue item', opportunity: 'Other route', due: '2026-09-01'},
      {task: 'Global asset register', opportunity: ''},
    ],
  }, '2026-09-29', route.name);
  assert.equal(result.action.task, 'Global asset register');
  assert.equal(result.action.opportunity, '');
});

test('next action is the earliest upcoming deadline before undated work', () => {
  const route = {...readyRoute, name: 'Focused route'};
  const result = decide({
    opportunities: [route],
    actions: [
      {task: 'Undated route work', opportunity: route.name, due: '', status: 'open'},
      {task: 'Later route deadline', opportunity: route.name, due: '2026-10-08', status: 'open'},
      {task: 'First route deadline', opportunity: route.name, due: '2026-10-01', status: 'open'},
    ],
  }, '2026-09-29', route.name);
  assert.equal(result.action.task, 'First route deadline');
  assert.equal(result.action.due, '2026-10-01');
});

test('actions scoped only to closed routes cannot appear as current next steps', () => {
  const closed = {...readyRoute, name: 'Closed route', status: 'closed'};
  const result = decide({
    opportunities: [closed],
    actions: [{task: 'Submit the closed application', opportunity: closed.name,
      due: '2026-09-01', status: 'open'}],
  }, '2026-09-29');
  assert.equal(result.state, 'no_go');
  assert.equal(result.action.source, 'suggested');
  assert.doesNotMatch(result.action.task, /Submit the closed application/);
});

test('a legacy action with no saved scope is never silently treated as campaign-wide', () => {
  const closed = {...readyRoute, name: 'Closed route', status: 'closed'};
  const result = decide({
    opportunities: [closed],
    actions: [{task: 'Submit the closed application', status: 'open'}],
  }, '2026-09-29');
  assert.equal(result.state, 'no_go');
  assert.equal(result.action.source, 'suggested');
  assert.match(result.action.task, /Confirm the scope of 1 older action/);
  assert.doesNotMatch(result.action.task, /Submit the closed application/);
});

test('a closed-route action cannot override the selected active route guidance', () => {
  const route = {...readyRoute, name: 'Active route'};
  const result = decide({
    opportunities: [route, {...readyRoute, name: 'Closed route', status: 'closed'}],
    actions: [{task: 'Submit the closed application', opportunity: 'Closed route',
      due: '2026-09-01', status: 'open'}],
  }, '2026-09-29', route.name);
  assert.equal(result.state, 'not_ready');
  assert.equal(result.action.source, 'suggested');
  assert.match(result.action.task, /open action\(s\) on inactive route\(s\)/);
  assert.doesNotMatch(result.action.task, /Submit the closed application/);
});

test('an active route with no eligibility checks gets a specific, evidence-led next step', () => {
  const result = decide({
    opportunities: [readyRoute], requirements: [],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /Record the applicant eligibility checks/);
  assert.match(result.reopenCriteria, /No applicant eligibility checks are recorded/);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('a route marked needs clarification does not imply that the programme round is closed', () => {
  const result = decide({
    opportunities: [{...readyRoute, status: 'clarification'}],
    requirements: [{...goodCheck, status: 'clarification', source_quote: ''}],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /outstanding clarification/);
  assert.doesNotMatch(result.reopenCriteria, /Confirm the route is open/);
  assert.match(result.reopenCriteria, /outstanding programme clarification/);
});

test('a route with an unresolved clarification cannot be ready even when every check is complete', () => {
  const result = decide({
    opportunities: [{...readyRoute, status: 'clarification'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.equal(result.label, 'NOT READY');
  assert.match(result.detail, /Local fund.*not ready.*outstanding programme clarification/);
  assert.match(result.action.task, /Resolve the outstanding clarification for “Local fund”/);
  assert.match(result.reopenCriteria, /outstanding programme clarification/);
});

test('a complete source record with a clarification status asks for a human resolution, not duplicate evidence', () => {
  const result = decide({
    opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'clarification'}],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /source and applicant-evidence record.*remains marked for clarification/);
  assert.match(result.action.task, /resolve the interpretation and update its status/);
  assert.doesNotMatch(result.detail, /record a source excerpt|a check date/);
  assert.doesNotMatch(result.reopenCriteria, /record a source excerpt|a check date/);
});

test('a complete source record with an unknown status asks for assessment, not duplicate evidence', () => {
  const result = decide({
    opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'unknown'}],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /complete evidence record but remains unassessed/);
  assert.match(result.action.task, /review it and record the applicant-specific status/);
  assert.doesNotMatch(result.detail, /record a source excerpt|a check date/);
});

test('eligibility guidance names only source fields that are actually missing', () => {
  const result = decide({
    opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'unknown', source_quote: ''}],
  }, '2026-09-29');
  assert.match(result.detail, /record a source excerpt/);
  assert.doesNotMatch(result.detail, /applicant-specific evidence|source link|check date/);
});

test('a researching route requires confirmation of a current live round', () => {
  const result = decide({
    opportunities: [{...readyRoute, status: 'researching'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.reopenCriteria, /current official wording.*current round is open/);
});

test('the selected route controls its suggested action and reopen evidence gate', () => {
  const nbn = {...readyRoute, name: 'NBN community grant'};
  const ruic = {...readyRoute, name: 'CSIRO RUIC', status: 'open'};
  const result = decide({
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
  const result = decide({
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

test('open actions on inactive routes are surfaced as held review work', () => {
  const result = decide({
    opportunities: [readyRoute, {...readyRoute, name: 'Closed route', status: 'closed'}],
    actions: [{task: 'Submit the old application', opportunity: 'Closed route',
      scope_confirmed: true, submission_phase: 'pre_submission', status: 'open'}],
  }, '2026-09-29', readyRoute.name);
  assert.equal(result.action.source, 'suggested');
  assert.match(result.action.task, /1 open action\(s\) on inactive route\(s\)/);
  assert.doesNotMatch(result.action.task, /Submit the old application/);
});
