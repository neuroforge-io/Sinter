import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {campaignDecision, CAMPAIGN_DECISION_NOTE} from '../src/sinter/web/campaign-decision.js';

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
  applicant_confirmed: true,
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
  assert.match(CAMPAIGN_DECISION_NOTE, /Sinter has not verified sources, eligibility or authority/);
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
      owner_kind: 'person', owner_confirmed: true, due: '2026-10-01', status: 'open'}],
  }, '2026-09-29');
  assert.equal(result.state, 'ready_for_review');
  assert.equal(result.label, 'HUMAN REVIEW REQUIRED');
  assert.match(result.detail, /user-entered screening records and requires human review/);
  assert.match(CAMPAIGN_DECISION_NOTE, /not permission to submit/);
  assert.match(result.action.ownerStatus, /Acceptance recorded by user/);
  assert.equal(result.action.due, '2026-10-01');
  assert.match(result.reopenCriteria, /before any submission/);
});

test('human review suggestions apply to any campaign without inventing a P&C role', () => {
  const document = {opportunities: [{...readyRoute,
    applicant: 'Fictional research company'}], requirements: [goodCheck]};
  const original = JSON.stringify(document);
  const result = decide(document, '2026-09-29');
  assert.equal(result.state, 'ready_for_review');
  assert.match(result.action.task, /Ask a campaign reviewer/);
  assert.match(result.action.task, /eligibility evidence and authority/);
  assert.match(result.reopenCriteria, /authority appropriate to this campaign/);
  assert.doesNotMatch(result.action.task + result.reopenCriteria, /P&C/);
  assert.equal(result.action.ownerNeeded, true);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
  assert.equal(JSON.stringify(document), original);
});

test('the decision card describes owner type consistently with the saved action', () => {
  const result = decide({actions: [{opportunity: '', scope_confirmed: true,
    task: 'Confirm the applicant', owner: 'Treasurer', owner_kind: 'role',
    owner_confirmed: false, status: 'open'}]}, '2026-09-29');
  assert.equal(result.action.ownerNeeded, true);
  assert.match(result.action.ownerStatus, /role suggestion, not a named person/);
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

test('a named but unconfirmed applicant stays blocked with an explicit next step', () => {
  const result = decide({
    opportunities: [{...readyRoute, applicant_confirmed: false}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /Confirm the named applicant directly/);
  assert.match(result.action.task, /Confirm the named applicant directly/);
});

test('a past date on a route still marked open requires status confirmation', () => {
  const result = decide({
    opportunities: [{...readyRoute, deadline: '2026-09-28'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /recorded closing date.*has passed/);
  assert.match(result.detail, /closing date \(2026-09-28\) has passed/);
  assert.match(result.reopenCriteria, /remaining applicant checks and application window in Opportunities/);
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

test('missing source snapshots are not described as changed sources', () => {
  const route = {...readyRoute, window_source_url: ''};
  const routeResult = decide({opportunities: [route], requirements: [goodCheck]},
    '2026-09-29');
  assert.match(routeResult.detail, /No source URL snapshot was saved/);
  assert.doesNotMatch(routeResult.detail, /page changed after/);

  const sourceId = 'b'.repeat(32);
  const check = {...goodCheck, source_id: sourceId, source_url: '',
    checked_at: '2026-09-20'};
  const requirementResult = decide({opportunities: [readyRoute],
    requirements: [check], sources: [windowSource,
      {id: sourceId, url: 'https://example.org/rules', checked_at: '2026-09-20'}]},
  '2026-09-29');
  assert.match(requirementResult.detail, /No source URL snapshot was saved/);
  assert.doesNotMatch(requirementResult.detail, /URL changed after this excerpt/);
});

test('eligibility evidence checked in the future cannot qualify as current', () => {
  const result = decide({opportunities: [readyRoute],
    requirements: [{...goodCheck, checked_at: '2026-09-30'}]}, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /eligibility source check date \(2026-09-30\) is in the future/);
});

test('eligibility evidence becomes stale after 90 days but remains current on day 90', () => {
  const route = {...readyRoute, application_mode: 'required', applicant: 'Applicant',
    applicant_confirmed: true};
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
  assert.match(result.detail, /No applicant eligibility checks are recorded/);
  assert.match(result.reopenCriteria, /remaining applicant checks/);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('a route marked needs clarification does not imply that the programme round is closed', () => {
  const result = decide({
    opportunities: [{...readyRoute, status: 'clarification'}],
    requirements: [{...goodCheck, status: 'clarification', source_quote: ''}],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /Review the unresolved eligibility check: “Applicant type accepted”/);
  assert.doesNotMatch(result.action.task, /contact the funder/i);
  assert.doesNotMatch(result.reopenCriteria, /Confirm the route is open/);
  assert.doesNotMatch(result.reopenCriteria, /recorded clarification reason/);
});

test('a route with an unresolved clarification cannot be ready even when every check is complete', () => {
  const result = decide({
    opportunities: [{...readyRoute, status: 'clarification'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.equal(result.label, 'NOT READY');
  assert.match(result.detail, /Local fund.*not ready.*no unresolved applicant check identifies why/);
  assert.match(result.action.task, /no unresolved applicant check identifies why/);
  assert.doesNotMatch(result.reopenCriteria, /recorded clarification reason/);
});

test('a complete source record with a clarification status asks for a human resolution, not duplicate evidence', () => {
  const result = decide({
    opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'clarification'}],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /source and applicant-evidence record.*remains marked for clarification/);
  assert.match(result.action.task, /resolve the interpretation and update its status/);
  assert.doesNotMatch(result.detail, /record a source excerpt|a check date/i);
  assert.doesNotMatch(result.reopenCriteria, /record a source excerpt|a check date/i);
});

test('a complete source record with an unknown status asks for assessment, not duplicate evidence', () => {
  const result = decide({
    opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'unknown'}],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /complete evidence record but remains unassessed/);
  assert.match(result.action.task, /review it and record the applicant-specific status/);
  assert.doesNotMatch(result.detail, /record a source excerpt|a check date/i);
});

test('eligibility guidance names only source fields that are actually missing', () => {
  const result = decide({
    opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'unknown', source_quote: ''}],
  }, '2026-09-29');
  assert.match(result.detail, /Record a source excerpt\./);
  assert.doesNotMatch(result.detail, /applicant-specific evidence|source link|check date/);
});

test('a researching route requires confirmation of a current live round', () => {
  const result = decide({
    opportunities: [{...readyRoute, status: 'researching'}],
    requirements: [goodCheck],
  }, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /current round is open/);
  assert.match(result.reopenCriteria, /current official wording.*keep unresolved checks open/);
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
  assert.match(result.reopenCriteria, /Reassess “CSIRO RUIC”/);
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
  assert.match(result.reopenCriteria, /Reassess “Focused route”/);
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

const assertReadableGuidance = result => {
  for (const text of [result.detail, result.reopenCriteria, result.action.task]) {
    assert.doesNotMatch(text, /\.\.|\b(?:record|and) (?:Record|The|No)\b|\. and resolve/);
    assert.doesNotMatch(text, /human review: Review|wording: Review/);
  }
};

test('the actual garden fixture gives separate actionable eligibility instructions', () => {
  const garden = JSON.parse(readFileSync(new URL(
    '../src/sinter/web/offline-garden-campaign.json', import.meta.url), 'utf8'));
  const original = JSON.stringify(garden);
  const result = campaignDecision(garden, '2026-09-30');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /is not ready for human review\. Review the unresolved eligibility check:/);
  assert.match(result.detail, /“Confirm applicant conditions and exclusions” is not assessed\. Record a current official source link and a source excerpt\. Record the date this eligibility source was checked\./);
  assert.match(result.reopenCriteria, /remaining applicant checks and application window in Opportunities/);
  assert.doesNotMatch(result.reopenCriteria, /Confirm applicant conditions and exclusions|Record a current official source link/);
  assert.equal(result.action.source, 'recorded');
  assert.equal(result.action.actionIndex, 1);
  assert.equal(result.action.task, garden.actions[1].task);
  assert.equal(result.action.ownerNeeded, true);
  assert.equal(result.action.due, garden.actions[1].due);
  assert.equal(JSON.stringify(garden), original);
  assertReadableGuidance(result);
});

test('a missing eligibility check date is a sentence rather than a field label', () => {
  const result = decide({opportunities: [readyRoute],
    requirements: [{...goodCheck, checked_at: ''}]}, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /is marked met, but its source record is incomplete or out of date\. Record the date this eligibility source was checked\.$/);
  assert.doesNotMatch(result.detail, /applicant-specific evidence|source link|source excerpt/);
  assertReadableGuidance(result);
});

test('invalid, future and stale date instructions remain distinct complete sentences', () => {
  const cases = [
    ['2026-02-30', 'Record a valid date for this eligibility source check.'],
    ['2026-09-30', 'The eligibility source check date (2026-09-30) is in the future; correct it.'],
    ['2026-06-30', 'The eligibility source was last checked 91 days ago; recheck it (within 90 days).'],
  ];
  for (const [checked_at, expected] of cases) {
    const result = decide({opportunities: [readyRoute],
      requirements: [{...goodCheck, checked_at}]}, '2026-09-29');
    assert.equal(result.state, 'not_ready');
    assert.ok(result.action.task.endsWith(expected), result.action.task);
    assert.doesNotMatch(result.action.task, /applicant-specific evidence|source link|source excerpt/);
    assertReadableGuidance(result);
  }
});

test('source snapshot issues retain their exact independent instructions', () => {
  const sourceId = 'b'.repeat(32);
  const linked = {id: sourceId, url: goodCheck.source_url,
    checked_at: goodCheck.checked_at};
  const cases = [
    [{...goodCheck, source_id: sourceId}, null,
      'The linked campaign source is missing; reconnect it and recheck the wording.'],
    [{...goodCheck, source_id: sourceId, source_url: ''}, linked,
      'No source URL snapshot was saved with this wording; compare it with the linked page and recheck before use.'],
    [{...goodCheck, source_id: sourceId}, {...linked, url: ''},
      'The linked campaign source has no URL; add the official page and recheck the wording.'],
    [{...goodCheck, source_id: sourceId}, {...linked, url: 'https://example.org/changed'},
      'The saved source URL differs from the linked record; re-read the page and update the wording and check date before use.'],
    [{...goodCheck, source_id: sourceId}, {...linked, checked_at: ''},
      'The linked source has no check date; re-read the page and record when it was checked.'],
    [{...goodCheck, source_id: sourceId, checked_at: ''}, linked,
      'No source check date was saved with this wording; re-read it and record a date before use.'],
    [{...goodCheck, source_id: sourceId}, {...linked, checked_at: '2026-09-21'},
      'The saved check date differs from the linked record; re-read the wording and update the date before use.'],
  ];
  for (const [check, source, expected] of cases) {
    const result = decide({opportunities: [readyRoute], requirements: [check],
      sources: [windowSource, ...(source ? [source] : [])]}, '2026-09-29');
    assert.equal(result.state, 'not_ready');
    assert.ok(result.action.task.endsWith(expected), result.action.task);
    assertReadableGuidance(result);
  }
});

test('clarification combines missing fields, date and snapshot without joining sentences as labels', () => {
  const sourceId = 'b'.repeat(32);
  const result = decide({opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'clarification', source_id: sourceId,
      evidence: '', source_url: '', source_quote: '', checked_at: ''}],
    sources: [windowSource, {id: sourceId, url: goodCheck.source_url,
      checked_at: goodCheck.checked_at}]}, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.action.task, /remains marked for clarification\. Record applicant-specific evidence, a current official source link and a source excerpt\. Record the date this eligibility source was checked\. No source URL snapshot was saved/);
  assert.ok(result.action.task.endsWith('Resolve the interpretation and update its status.'));
  assertReadableGuidance(result);
});

test('unknown and clarification statuses remain blocked with complete source records', () => {
  for (const status of ['unknown', 'clarification']) {
    const result = decide({opportunities: [readyRoute],
      requirements: [{...goodCheck, status}]}, '2026-09-29');
    assert.equal(result.state, 'not_ready');
    assert.doesNotMatch(result.action.task, /Record a source excerpt|Record the date/);
    assertReadableGuidance(result);
  }
});

test('one shared qualification replaces repeated global paragraphs across decision states', () => {
  for (const document of [
    {}, {opportunities: [{...readyRoute, status: 'closed'}]},
    {opportunities: [{...readyRoute, status: 'submitted'}]},
    {opportunities: [readyRoute], requirements: [goodCheck]},
    {opportunities: [readyRoute], requirements: [{...goodCheck, status: 'unknown'}]},
  ]) {
    const result = decide(document, '2026-09-29');
    assert.doesNotMatch(result.detail + result.reopenCriteria, /Sinter.*verif|permission to submit|clearance to apply/);
  }
  assert.equal((CAMPAIGN_DECISION_NOTE.match(/Sinter/g) || []).length, 1);
  assert.match(CAMPAIGN_DECISION_NOTE, /sources, eligibility or authority/);
  assert.match(CAMPAIGN_DECISION_NOTE, /not permission to submit/);
});

test('distinct progress guidance keeps the selected route and does not promise clearance', () => {
  const result = decide({opportunities: [readyRoute],
    requirements: [{...goodCheck, status: 'clarification', source_quote: ''}]}, '2026-09-29');
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /Applicant type accepted.*Record a source excerpt/);
  assert.match(result.reopenCriteria, /After resolving the blocker above/);
  assert.match(result.reopenCriteria, /Reassess “Local fund”/);
  assert.match(result.reopenCriteria, /keep unresolved checks open/);
  assert.doesNotMatch(result.reopenCriteria, /Applicant type accepted|Record a source excerpt|ready to submit/);
  assert.equal(result.action.source, 'suggested');
  assert.equal(result.action.ownerNeeded, true);
  assert.match(result.action.task, /Applicant type accepted.*Record a source excerpt/);
});

test('a later user-marked unmet check outranks unknown and clarification checks on an active route', () => {
  for (const routeStatus of ['open', 'clarification']) {
    for (const firstStatus of ['unknown', 'clarification']) {
      const document = {
        opportunities: [{...readyRoute, status: routeStatus}],
        requirements: [
          {...goodCheck, rule: 'Broad applicant interpretation', status: firstStatus},
          {...goodCheck, rule: 'Cash matching is available', status: 'not_met'},
        ],
      };
      const original = JSON.stringify(document);
      const result = decide(document, '2026-09-29');
      assert.equal(result.state, 'not_ready');
      assert.equal(result.label, 'NOT READY');
      assert.ok(result.detail.endsWith('“Cash matching is available” is marked not met in the user-entered record.'));
      assert.equal(result.action.task, '“Cash matching is available” is marked not met in the user-entered record.');
      assert.equal(result.action.source, 'suggested');
      assert.equal(result.action.ownerNeeded, true);
      assert.equal(Object.hasOwn(result.action, 'due'), false);
      assert.match(result.reopenCriteria, /keep unresolved checks open/);
      assert.equal(JSON.stringify(document), original);
      assertReadableGuidance(result);
    }
  }
});

test('unmet-check priority is scoped to the selected active route', () => {
  const other = {...readyRoute, name: 'Other route'};
  const result = decide({opportunities: [other, readyRoute], requirements: [
    {...goodCheck, opportunity: other.name, rule: 'Other route cash condition', status: 'not_met'},
    {...goodCheck, rule: 'Selected applicant interpretation', status: 'unknown'},
  ]}, '2026-09-29', readyRoute.name);
  assert.match(result.detail, /Selected applicant interpretation/);
  assert.match(result.action.task, /Selected applicant interpretation/);
  assert.doesNotMatch(result.detail + result.action.task, /Other route cash condition/);
});

test('multiple unmet checks use their original stable order without rewriting evidence', () => {
  const document = {opportunities: [readyRoute], requirements: [
    {...goodCheck, rule: 'Earlier unknown check', status: 'unknown'},
    {...goodCheck, rule: 'First unmet condition', status: 'not_met'},
    {...goodCheck, rule: 'Second unmet condition', status: 'not_met'},
  ]};
  const original = JSON.stringify(document);
  const result = decide(document, '2026-09-29');
  assert.match(result.detail, /First unmet condition.*marked not met/);
  assert.match(result.action.task, /First unmet condition.*marked not met/);
  assert.doesNotMatch(result.detail + result.action.task, /Earlier unknown check|Second unmet condition/);
  assert.equal(JSON.stringify(document), original);
});

test('prioritising a user-marked unmet check does not bypass stale or changed source gates', () => {
  const sourceId = 'b'.repeat(32);
  for (const variant of ['stale', 'changed']) {
    const check = {...goodCheck, source_id: sourceId, rule: 'Cash condition',
      status: 'not_met', checked_at: variant === 'stale' ? '2026-06-30' : goodCheck.checked_at};
    const linked = {id: sourceId, url: check.source_url,
      checked_at: variant === 'changed' ? '2026-09-21' : check.checked_at};
    const document = {opportunities: [readyRoute], requirements: [check],
      sources: [windowSource, linked]};
    const original = JSON.stringify(document);
    const blocked = decide(document, '2026-09-29');
    assert.equal(blocked.state, 'not_ready');
    assert.match(blocked.detail, /Cash condition.*marked not met in the user-entered record/);
    assert.equal(JSON.stringify(document), original);
    const reassessed = decide({...document, requirements: [{...check, status: 'met'}]}, '2026-09-29');
    assert.equal(reassessed.state, 'not_ready');
    assert.match(reassessed.detail, variant === 'stale'
      ? /last checked 91 days ago/ : /saved check date differs from the linked record/);
  }
});

test('remaining route gaps still block review when an unmet check is explicitly changed', () => {
  const document = {opportunities: [{...readyRoute, application_mode: 'unknown'}],
    requirements: [{...goodCheck, rule: 'Cash condition', status: 'not_met'}]};
  const blocked = decide(document, '2026-09-29');
  assert.match(blocked.detail, /Cash condition.*marked not met/);
  const reassessed = decide({...document,
    requirements: [{...document.requirements[0], status: 'met'}]}, '2026-09-29');
  assert.equal(reassessed.state, 'not_ready');
  assert.match(reassessed.detail, /formal application and who is allowed to apply/);
});

test('an unmet primary gap leaves the explicit recorded action, owner and proposed date untouched', () => {
  const recorded = {opportunity: readyRoute.name, scope_confirmed: true,
    task: 'Confirm the cash range with the operator', status: 'open',
    owner: 'Fictional Treasurer', owner_kind: 'role', owner_confirmed: false,
    due: '2026-10-02'};
  const document = {opportunities: [{...readyRoute, status: 'clarification'}],
    requirements: [
      {...goodCheck, rule: 'Broad applicant interpretation', status: 'clarification'},
      {...goodCheck, rule: 'Cash matching is available', status: 'not_met'},
    ], actions: [recorded]};
  const original = JSON.stringify(document);
  const result = decide(document, '2026-09-29');
  assert.match(result.detail, /Cash matching is available.*marked not met/);
  assert.equal(result.action.source, 'recorded');
  assert.equal(result.action.actionIndex, 0);
  assert.equal(result.action.task, recorded.task);
  assert.equal(result.action.opportunity, recorded.opportunity);
  assert.equal(result.action.due, recorded.due);
  assert.equal(result.action.ownerNeeded, true);
  assert.match(result.action.ownerStatus, /role suggestion, not a named person/);
  assert.equal(JSON.stringify(document), original);
});

const selectedRecordDocument = (purpose, status = 'researching') => ({
  opportunities: [readyRoute, {name: 'Selected record', purpose, status,
    application_mode: 'unknown'}], requirements: [goodCheck], sources: [windowSource],
  actions: [{opportunity: readyRoute.name, scope_confirmed: true,
    status: 'open', submission_phase: 'pre_submission',
    task: '  Keep the other route’s actual task.  ', owner: 'Casey Example',
    owner_kind: 'person', owner_confirmed: false, due: '2026-09-01'}],
});

test('an explicitly selected record keeps its suggestion while other current work stays separate', () => {
  for (const purpose of ['discussion', 'research']) {
    const document = selectedRecordDocument(purpose);
    const before = structuredClone(document);
    const result = campaignDecision(document, '2026-09-29', 'Selected record');
    assert.equal(result.focusOpportunity, 'Selected record');
    assert.equal(result.state, 'in_progress');
    assert.equal(result.action.source, 'suggested');
    assert.match(result.action.task, purpose === 'discussion'
      ? /discussion scope.*next question/ : /specific research question.*source evidence/);
    assert.equal(result.action.ownerNeeded, true);
    assert.equal(Object.hasOwn(result.action, 'due'), false);
    const portfolio = result.portfolioAction;
    assert.equal(portfolio.source, 'recorded');
    assert.equal(portfolio.actionIndex, 0);
    assert.equal(portfolio.opportunity, readyRoute.name);
    for (const key of ['task', 'owner', 'owner_kind', 'owner_confirmed', 'due',
      'status', 'submission_phase']) {
      assert.equal(portfolio[key], document.actions[0][key]);
    }
    assert.equal(portfolio.ownerNeeded, true);
    assert.deepEqual(document, before);
  }
});

test('separate portfolio work does not acquire absent owner, date, status or phase metadata', () => {
  const document = selectedRecordDocument('research');
  document.actions = [{opportunity: readyRoute.name, task: 'Original unstated metadata'}];
  const before = structuredClone(document);
  const result = campaignDecision(document, '2026-09-29', 'Selected record');
  assert.equal(result.portfolioAction.actionIndex, 0);
  assert.equal(result.portfolioAction.task, document.actions[0].task);
  for (const key of ['owner', 'owner_kind', 'owner_confirmed', 'due', 'status',
    'submission_phase']) assert.equal(Object.hasOwn(result.portfolioAction, key), false);
  assert.deepEqual(document, before);
});

test('selected informational work keeps own then current campaign-wide action precedence', () => {
  for (const purpose of ['discussion', 'research']) {
    const document = selectedRecordDocument(purpose);
    const global = {opportunity: '', scope_confirmed: true, status: 'open',
      task: 'Review the campaign-wide records.', owner: '', owner_kind: 'unknown',
      owner_confirmed: false, due: ''};
    const own = {...global, opportunity: 'Selected record',
      task: 'Check the selected record’s evidence.', owner_kind: 'unassigned'};
    document.actions.push(global, own);
    const before = structuredClone(document);
    const result = campaignDecision(document, '2026-09-29', 'Selected record');
    assert.equal(result.action.actionIndex, 2);
    assert.equal(result.action.task, own.task);
    assert.equal(result.action.opportunity, own.opportunity);
    assert.equal(result.action.ownerNeeded, true);
    assert.equal(Object.hasOwn(result.action, 'due'), false);
    assert.equal(result.portfolioAction.actionIndex, 0);
    assert.deepEqual(document, before);
    const onlyGlobal = {...document, actions: document.actions.slice(0, 2)};
    const globalResult = campaignDecision(onlyGlobal, '2026-09-29', 'Selected record');
    assert.equal(globalResult.action.actionIndex, 1);
    assert.equal(globalResult.action.opportunity, '');
    assert.equal(globalResult.action.ownerNeeded, true);
    assert.match(globalResult.action.ownerStatus, /Owner needed.*no person/);
    assert.equal(onlyGlobal.actions[1].owner_kind, 'unknown');
  }
});

test('unrelated held or unclassified history cannot replace a selected record’s local guidance', () => {
  const document = selectedRecordDocument('research');
  document.actions.push(
    {opportunity: readyRoute.name, scope_confirmed: false, status: 'open',
      task: 'Unclassified other route work'},
    {status: 'open', task: 'Older action with no recorded scope'},
    {opportunity: 'Selected record', scope_confirmed: true, status: 'held',
      task: 'The selected record’s held historical task', due: '2026-09-01'},
  );
  document.requirements.push({...goodCheck, status: 'not_met',
    rule: 'Other route’s historic adverse condition'});
  const before = structuredClone(document);
  const result = campaignDecision(document, '2026-09-29', 'Selected record');
  assert.equal(result.action.source, 'suggested');
  assert.match(result.action.task, /specific research question.*source evidence/);
  assert.doesNotMatch(result.action.task + result.detail,
    /Other route’s historic|older action|unclassified|held historical task/i);
  assert.equal(result.portfolioAction.actionIndex, 0);
  assert.deepEqual(document, before);
});

test('selected active records still surface their own entered unmet checks and uncertain action scope', () => {
  const document = selectedRecordDocument('research');
  document.requirements.push({...goodCheck, opportunity: 'Selected record',
    status: 'not_met', rule: 'Selected evidence condition'});
  const result = campaignDecision(document, '2026-09-29', 'Selected record');
  assert.match(result.action.task, /Selected evidence condition.*marked not met/);
  assert.equal(result.portfolioAction.actionIndex, 0);
  document.actions.push({opportunity: 'Selected record', scope_confirmed: false,
    status: 'open', task: 'Scope must be confirmed first'});
  const unclassified = campaignDecision(document, '2026-09-29', 'Selected record');
  assert.match(unclassified.action.task, /Confirm the scope of 1 older action/);
  assert.equal(unclassified.action.source, 'suggested');
});

test('an explicitly selected inactive discussion or research record stays in focus beside active work', () => {
  for (const purpose of ['discussion', 'research']) {
    for (const status of ['paused', 'closed', 'not_pursuing']) {
      const document = selectedRecordDocument(purpose, status);
      document.actions.push({opportunity: 'Selected record', scope_confirmed: true,
        status: 'held', task: 'Retained work stays held.', due: '2026-10-01'});
      const before = structuredClone(document);
      const result = campaignDecision(document, '2026-09-29', 'Selected record');
      assert.equal(result.focusOpportunity, 'Selected record');
      assert.equal(result.state, 'no_go');
      assert.match(result.label, /NOT CURRENT/);
      assert.match(result.detail, /Selected record/);
      assert.match(result.detail, /historical records; no active commitment/);
      assert.equal(result.action.source, 'suggested');
      assert.match(result.action.task, /Review the retained scope and evidence/);
      assert.equal(Object.hasOwn(result.action, 'due'), false);
      assert.match(result.reopenCriteria, /explicit decision to change the route status/);
      assert.equal(result.portfolioAction.actionIndex, 0);
      assert.deepEqual(document, before);
    }
  }
});

test('a selected submitted informational record only promotes an explicit post-submission follow-up', () => {
  for (const purpose of ['discussion', 'research']) {
    const document = selectedRecordDocument(purpose, 'submitted');
    const retained = {opportunity: 'Selected record', scope_confirmed: true,
      status: 'open', submission_phase: 'pre_submission',
      task: 'Retained unfinished preparation', owner: '', owner_kind: 'unassigned',
      owner_confirmed: false, due: ''};
    document.actions.push(retained);
    const before = structuredClone(document);
    const result = campaignDecision(document, '2026-09-29', 'Selected record');
    assert.equal(result.focusOpportunity, 'Selected record');
    assert.equal(result.state, 'awaiting_decision');
    assert.equal(result.label, 'SUBMITTED STATUS RECORDED');
    assert.match(result.detail, /does not establish a formal application, agreement, award/);
    assert.equal(result.action.source, 'suggested');
    assert.match(result.action.task, /Review 1 unfinished pre-submission action/);
    assert.doesNotMatch(result.action.task, /Retained unfinished preparation/);
    assert.deepEqual(document, before);
    const followUp = {...document, actions: [document.actions[0],
      {...retained, submission_phase: 'post_submission',
        task: 'Record a response if documented.', due: '2026-10-04'}]};
    const current = campaignDecision(followUp, '2026-09-29', 'Selected record');
    assert.equal(current.action.source, 'recorded');
    assert.equal(current.action.actionIndex, 1);
    assert.equal(current.action.task, followUp.actions[1].task);
    assert.equal(current.action.due, followUp.actions[1].due);
    assert.equal(current.portfolioAction.actionIndex, 0);
  }
});

test('missing and unknown purpose, formal conflicts and no explicit selection keep legacy fallback', () => {
  for (const purpose of [undefined, 'unknown', 'application']) {
    const document = selectedRecordDocument(purpose);
    if (purpose === undefined) delete document.opportunities[1].purpose;
    const before = structuredClone(document);
    const selected = campaignDecision(document, '2026-09-29', 'Selected record');
    assert.equal(selected.focusOpportunity, 'Selected record');
    assert.equal(selected.action.source, 'recorded');
    assert.equal(selected.action.actionIndex, 0);
    assert.equal(Object.hasOwn(selected, 'portfolioAction'), false);
    document.opportunities[1].status = 'closed';
    const historical = campaignDecision(document, '2026-09-29', 'Selected record');
    assert.equal(historical.focusOpportunity, readyRoute.name);
    assert.equal(historical.state, 'ready_for_review');
    assert.equal(Object.hasOwn(historical, 'portfolioAction'), false);
    document.opportunities[1].status = before.opportunities[1].status;
    assert.deepEqual(document, before);
  }
  const nonformal = selectedRecordDocument('research');
  const overall = campaignDecision(nonformal, '2026-09-29');
  assert.equal(overall.focusOpportunity, readyRoute.name);
  assert.equal(overall.state, 'ready_for_review');
  assert.equal(overall.action.actionIndex, 0);
  assert.equal(Object.hasOwn(overall, 'portfolioAction'), false);
  const informationalFirst = {...nonformal,
    opportunities: [...nonformal.opportunities].reverse()};
  const unselectedRecord = campaignDecision(informationalFirst, '2026-09-29');
  assert.equal(unselectedRecord.focusOpportunity, 'Selected record');
  assert.equal(unselectedRecord.action.actionIndex, 0);
  assert.equal(Object.hasOwn(unselectedRecord, 'portfolioAction'), false);
  const required = structuredClone(nonformal);
  required.opportunities[1].application_mode = 'required';
  const conflict = campaignDecision(required, '2026-09-29', 'Selected record');
  assert.equal(conflict.state, 'not_ready');
  assert.match(conflict.detail, /formal application is recorded as required/);
  assert.equal(conflict.action.actionIndex, 0);
  assert.equal(Object.hasOwn(conflict, 'portfolioAction'), false);
});
