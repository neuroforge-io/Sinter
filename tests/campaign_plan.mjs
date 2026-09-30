import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignActionRowsForCalendar, campaignActionRowsForPlan,
  normalizeCampaignActionScopes} from '../src/sinter/web/campaign-plan.js';

test('campaign action exports preserve route scope and user-entered ownership state', () => {
  const rows = campaignActionRowsForPlan([
    {task: 'Check eligibility', opportunity: 'CSIRO Kick-Start',
      owner: 'Director', owner_kind: 'person', owner_confirmed: false,
      due: '2026-10-08', status: 'open'},
    {task: 'Build asset register', opportunity: '', owner: '',
      owner_confirmed: false, due: '', status: 'done'},
    {task: 'Verify match', opportunity: 'nbn Grants', owner: 'Lloyd',
      owner_kind: 'person', owner_confirmed: true, due: '', status: 'open'},
  ], [
    {name: 'CSIRO Kick-Start', status: 'open'},
    {name: 'nbn Grants', status: 'researching'},
  ]);

  assert.deepEqual(rows, [
    {action: 'Check eligibility', scope: 'CSIRO Kick-Start',
      phase: 'Before submission',
      owner: 'Director (named person; acceptance unconfirmed)', due: '2026-10-08',
      status: 'not_started'},
    {action: 'Build asset register', scope: 'Campaign-wide',
      phase: 'Not applicable · campaign-wide',
      owner: 'Unassigned', due: '', status: 'done'},
    {action: 'Verify match', scope: 'nbn Grants',
      phase: 'Before submission',
      owner: 'Lloyd (user-marked accepted; verify directly)', due: '',
      status: 'not_started'},
  ]);
});

test('action export labels suggested roles without implying a person accepted', () => {
  const [row] = campaignActionRowsForPlan([{
    task: 'Check who can apply', opportunity: '', scope_confirmed: true,
    owner: 'Treasurer', owner_kind: 'role', owner_confirmed: false,
    due: '', status: 'open',
  }], []);
  assert.equal(row.owner, 'Treasurer (suggested role; no person named)');
});

test('legacy actions keep unknown scope until a person confirms it', () => {
  const actions = normalizeCampaignActionScopes([
    {task: 'Old action without a scope'},
    {task: 'Previously scoped action', opportunity: 'Local fund'},
    {task: 'Previously campaign-wide', opportunity: ''},
    {task: 'Still unconfirmed', opportunity: '', scope_confirmed: false},
  ]);
  assert.deepEqual(actions.map(row => [row.opportunity, row.scope_confirmed]), [
    ['', false], ['Local fund', true], ['', true], ['', false],
  ]);
  assert.equal(campaignActionRowsForPlan(actions, []).find(row => row.action === 'Old action without a scope').phase,
    'Not assigned · scope unconfirmed');
});

test('campaign calendars include only dated, open actions on confirmed current scopes', () => {
  const opportunities = [
    {name: 'Open route', status: 'open'},
    {name: 'Closed route', status: 'closed'},
    {name: 'Submitted route', status: 'submitted'},
  ];
  const actions = [
    {task: 'Check the open route', opportunity: 'Open route', due: '2026-10-08', status: 'open'},
    {task: 'Submit the closed route', opportunity: 'Closed route', due: '2026-09-01', status: 'open'},
    {task: 'Already completed', opportunity: '', due: '2026-09-15', status: 'done'},
    {task: 'Legacy scope unknown', due: '2026-10-02', status: 'open'},
    {task: 'Global next step', opportunity: '', due: '2026-10-12', status: 'open'},
    {task: 'Stale submission task', opportunity: 'Submitted route', due: '2026-10-03', status: 'open'},
    {task: 'Record award decision', opportunity: 'Submitted route',
      submission_phase: 'post_submission', due: '2026-10-15', status: 'open'},
  ];

  const calendarRows = campaignActionRowsForCalendar(actions, opportunities);
  assert.deepEqual(calendarRows.map(row => row.action), [
    'Check the open route', 'Global next step', 'Record award decision',
  ]);
  assert.deepEqual(calendarRows.map(row => row.due), [
    '2026-10-08', '2026-10-12', '2026-10-15',
  ]);

  const auditRows = campaignActionRowsForPlan(actions, opportunities);
  assert.equal(auditRows.find(row => row.action === 'Submit the closed route').scope,
    'Historical · Closed route');
  assert.equal(auditRows.find(row => row.action === 'Legacy scope unknown').scope,
    'Scope not confirmed');
  assert.equal(auditRows.find(row => row.action === 'Stale submission task').scope,
    'Historical pre-submission · Submitted route');
  assert.equal(auditRows.find(row => row.action === 'Record award decision').scope,
    'Submitted follow-up · Submitted route');
  assert.equal(auditRows.find(row => row.action === 'Record award decision').phase,
    'After-submission follow-up');
});

test('reopened-route actions with a post-submission phase stay labelled as held', () => {
  const opportunities = [{name: 'Reopened route', status: 'open'}];
  const actions = [{task: 'Check the previous submission', opportunity: 'Reopened route',
    scope_confirmed: true, submission_phase: 'post_submission',
    owner: '', owner_confirmed: false, due: '2026-10-14', status: 'open'}];

  assert.equal(campaignActionRowsForPlan(actions, opportunities)[0].scope,
    'Held post-submission · route reactivated · Reopened route');
  assert.deepEqual(campaignActionRowsForCalendar(actions, opportunities), []);
});
