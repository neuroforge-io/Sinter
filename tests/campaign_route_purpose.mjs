import assert from 'node:assert/strict';
import test from 'node:test';
import {CAMPAIGN_ROUTE_PURPOSES, campaignRoutePurpose, campaignRoutePurposeLabel,
  isNonApplicationRoute, campaignRoutePurposeConflict, campaignRoutePurposeGuidance}
  from '../src/sinter/web/campaign-route-purpose.js';
import {campaignDecision, applicationWindowGaps} from '../src/sinter/web/campaign-decision.js';
import {applicationAnswerAvailability, canDraftApplicationAnswer}
  from '../src/sinter/web/campaign-state.js';

const today = '2026-10-09';
const source = {id: 'a'.repeat(32), url: 'https://example.invalid/rules',
  checked_at: today};
const route = {name: 'Fictional route', status: 'open', url: source.url,
  application_mode: 'required', applicant: 'Fictional applicant',
  applicant_confirmed: true, application_window: 'fixed', deadline: '2026-10-30',
  window_source_id: source.id, window_source_url: source.url,
  window_source_quote: 'Fictional applications close on 30 October.',
  window_checked_at: today};
const check = {opportunity: route.name, rule: 'Fictional recorded check',
  status: 'met', evidence: 'Fictional evidence only.', source_id: source.id,
  source_url: source.url, source_quote: 'Fictional source excerpt.', checked_at: today};
const formal = () => ({opportunities: [{...route}], sources: [{...source}],
  requirements: [{...check}], actions: []});
const nonformal = purpose => ({opportunities: [{name: route.name, purpose,
  status: 'researching', application_mode: 'unknown'}], requirements: [], actions: [],
  sources: []});

test('purpose options are explicit and absent or invalid values remain unknown', () => {
  assert.deepEqual(CAMPAIGN_ROUTE_PURPOSES.map(([value]) => value),
    ['unknown', 'application', 'discussion', 'research']);
  for (const value of [undefined, null, 'grant', 'Research', 1, {}]) {
    const row = value === undefined ? {} : {purpose: value};
    const before = structuredClone(row);
    assert.equal(campaignRoutePurpose(row), 'unknown');
    assert.equal(campaignRoutePurposeLabel(row), 'Not specified');
    assert.deepEqual(row, before);
  }
});

test('no inferred purpose comes from application mode, funding, wording or communications', () => {
  const row = {application_mode: 'not_required', route_type: 'cash_grant',
    ceiling: 5000, name: 'Research discussion grant', fit: 'Research only',
    funding_tracking: {requested: 1000}, communications: [{content: 'Agreed discussion'}]};
  assert.equal(campaignRoutePurpose(row), 'unknown');
  assert.equal(isNonApplicationRoute(row), false);
  assert.equal(Object.hasOwn(row, 'purpose'), false);
});

test('a required formal application always overrides discussion or research classification', () => {
  for (const purpose of ['discussion', 'research']) {
    for (const mode of [undefined, 'unknown', 'not_required']) {
      assert.equal(isNonApplicationRoute({purpose, application_mode: mode}), true);
    }
    const required = {...route, purpose};
    assert.equal(isNonApplicationRoute(required), false);
    assert.match(campaignRoutePurposeConflict(required), /formal application.*required/);
    assert.equal(campaignRoutePurposeGuidance(required), null);
  }
  for (const purpose of [undefined, 'unknown', 'application']) {
    assert.equal(isNonApplicationRoute({...route, purpose}), false);
    assert.equal(campaignRoutePurposeConflict({...route, purpose}), '');
  }
});

test('absent, unknown and application purposes retain exact legacy formal decisions', () => {
  const document = formal();
  const legacy = campaignDecision(document, today);
  assert.equal(legacy.state, 'ready_for_review');
  for (const purpose of ['unknown', 'application']) {
    const explicit = {...document, opportunities: [{...route, purpose}]};
    assert.deepEqual(campaignDecision(explicit, today), legacy);
  }
  assert.equal(Object.hasOwn(document.opportunities[0], 'purpose'), false);
});

test('nonformal classification is explicit and preserves all original fields', () => {
  const document = nonformal('research');
  document.opportunities[0].route_type = 'cash_grant';
  document.opportunities[0].ceiling = 5000;
  document.opportunities[0].fit = 'Fictional conditional scope.';
  const before = structuredClone(document);
  const result = campaignDecision(document, today);
  assert.equal(result.state, 'in_progress');
  assert.equal(result.label, 'RESEARCH IN PROGRESS');
  assert.match(result.detail, /does not establish novelty, rights, eligibility or authority/);
  assert.deepEqual(document, before);
});

test('discussion and research suggestions are useful local work without invented dates or permission', () => {
  for (const purpose of ['discussion', 'research']) {
    const result = campaignDecision(nonformal(purpose), today);
    assert.equal(result.state, 'in_progress');
    assert.equal(result.action.source, 'suggested');
    assert.equal(result.action.ownerNeeded, true);
    assert.equal(Object.hasOwn(result.action, 'due'), false);
    assert.match(result.action.task, purpose === 'discussion'
      ? /discussion scope.*next question/ : /specific research question.*source evidence/);
    assert.doesNotMatch(result.detail + result.action.task, /current round|official programme|ready for human review/);
  }
});

test('the recorded current action retains its identity, owner and date on an explicit research route', () => {
  const document = nonformal('research');
  const action = {opportunity: route.name, scope_confirmed: true, status: 'open',
    task: 'Check the fictional source assumptions.', owner: 'Casey Example',
    owner_kind: 'person', owner_confirmed: true, due: '2026-10-12'};
  document.actions = [{...action, task: 'Held original task', status: 'held'}, action];
  const before = structuredClone(document);
  const result = campaignDecision(document, today);
  assert.equal(result.action.source, 'recorded');
  assert.equal(result.action.actionIndex, 1);
  assert.equal(result.action.task, action.task);
  assert.equal(result.action.due, action.due);
  assert.equal(result.action.ownerNeeded, false);
  assert.match(result.action.ownerStatus, /Acceptance recorded by user/);
  assert.deepEqual(document, before);
});

test('explicit discussion does not turn a suggested role or unknown date into confirmation', () => {
  const document = nonformal('discussion');
  document.actions = [{opportunity: route.name, scope_confirmed: true, status: 'open',
    task: 'Clarify the proposed scope.', owner: 'Convenor', owner_kind: 'role',
    owner_confirmed: false, due: ''}];
  const result = campaignDecision(document, today);
  assert.equal(result.action.ownerNeeded, true);
  assert.match(result.action.ownerStatus, /role suggestion, not a named person/);
  assert.equal(Object.hasOwn(result.action, 'due'), false);
});

test('entered unmet, stale and changed-source checks remain explicit on nonformal work', () => {
  for (const variant of ['unmet', 'stale', 'changed']) {
    const document = nonformal('research');
    const recorded = {...check, status: variant === 'unmet' ? 'not_met' : 'met',
      checked_at: variant === 'stale' ? '2026-06-30' : today};
    document.requirements = [recorded];
    document.sources = [{...source,
      checked_at: variant === 'changed' ? '2026-10-08' : recorded.checked_at}];
    const before = structuredClone(document);
    const result = campaignDecision(document, today);
    assert.equal(result.state, 'in_progress');
    assert.match(result.detail, /Recorded check still needs review/);
    assert.match(result.detail + result.action.task, variant === 'unmet'
      ? /marked not met/ : variant === 'stale' ? /last checked 101 days ago/
        : /saved check date differs/);
    assert.match(result.reopenCriteria, /Keep the recorded check unresolved/);
    assert.deepEqual(document, before);
  }
});

test('required-purpose conflicts block even complete formal screening without altering answer gates', () => {
  for (const purpose of ['discussion', 'research']) {
    const document = formal();
    document.opportunities[0].purpose = purpose;
    const before = structuredClone(document);
    const result = campaignDecision(document, today);
    assert.equal(result.state, 'not_ready');
    assert.match(result.detail, /formal application is recorded as required/);
    assert.match(result.action.task, /Reconcile the purpose and application workflow/);
    assert.match(result.reopenCriteria, /remaining applicant checks/);
    assert.equal(applicationAnswerAvailability(document.opportunities[0]).allowed,
      applicationAnswerAvailability(route).allowed);
    assert.equal(canDraftApplicationAnswer(document.opportunities[0]),
      canDraftApplicationAnswer(route));
    assert.deepEqual(document, before);
  }
});

test('reconciling a purpose conflict does not bypass remaining formal source or applicant gates', () => {
  const document = formal();
  document.opportunities[0] = {...route, purpose: 'research',
    applicant_confirmed: false, application_window: 'unknown'};
  assert.equal(campaignDecision(document, today).state, 'not_ready');
  const reconciled = {...document, opportunities: [{...document.opportunities[0],
    purpose: 'application'}]};
  const result = campaignDecision(reconciled, today);
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /Confirm the named applicant directly/);
  assert.equal(applicationAnswerAvailability(reconciled.opportunities[0]).allowed, false);
  assert.deepEqual(applicationWindowGaps(reconciled.opportunities[0], today, [source]),
    applicationWindowGaps({...reconciled.opportunities[0], purpose: undefined}, today, [source]));
});

test('explicit application and not-required mode conflict without enabling answer gates', () => {
  const document = formal();
  document.opportunities[0] = {...route, purpose: 'application',
    application_mode: 'not_required'};
  const before = structuredClone(document);
  const result = campaignDecision(document, today);
  assert.equal(result.state, 'not_ready');
  assert.match(result.detail, /labelled application.*No formal application recorded/);
  assert.match(result.action.task, /Reconcile the purpose and application workflow/);
  assert.equal(canDraftApplicationAnswer(document.opportunities[0]), false);
  assert.equal(applicationAnswerAvailability(document.opportunities[0]).allowed, false);
  assert.deepEqual(document, before);
  for (const purpose of [undefined, 'unknown']) {
    const legacy = {...document, opportunities: [{...document.opportunities[0], purpose}]};
    assert.equal(campaignRoutePurposeConflict(legacy.opportunities[0]), '');
    assert.equal(campaignDecision(legacy, today).state, 'ready_for_review');
  }
});

test('selected historical purpose conflicts add a notice without changing historical decision state', () => {
  for (const status of ['submitted', 'paused', 'closed', 'not_pursuing']) {
    for (const conflict of [
      {purpose: 'research', application_mode: 'required'},
      {purpose: 'discussion', application_mode: 'required'},
      {purpose: 'application', application_mode: 'not_required'},
    ]) {
      const document = formal();
      document.opportunities[0] = {...route, ...conflict, status};
      const before = structuredClone(document);
      const legacy = {...document, opportunities: [{...route, status,
        application_mode: conflict.application_mode}]};
      const oldState = campaignDecision(legacy, today, route.name);
      const result = campaignDecision(document, today, route.name);
      assert.equal(result.state, oldState.state);
      assert.equal(result.label, oldState.label);
      assert.match(result.detail, /Selected historical route.*Reconcile the purpose/);
      assert.match(result.detail, /recorded status remains unchanged/);
      assert.deepEqual(document, before);
    }
  }
});

test('historical conflict notices are scoped when another route remains active', () => {
  const document = formal();
  const historical = {...route, name: 'Fictional historical route',
    purpose: 'research', status: 'submitted'};
  document.opportunities.push(historical);
  const selected = campaignDecision(document, today, historical.name);
  assert.equal(selected.state, 'ready_for_review');
  assert.match(selected.detail, /Selected historical route “Fictional historical route”/);
  assert.match(selected.detail, /recorded status remains unchanged/);
  const active = campaignDecision(document, today, route.name);
  assert.equal(active.state, 'ready_for_review');
  assert.doesNotMatch(active.detail, /Selected historical route/);
  assert.equal(historical.status, 'submitted');
});

test('inactive informational routes retain history without invented future funder rounds', () => {
  for (const purpose of ['discussion', 'research']) {
    for (const status of ['closed', 'paused', 'not_pursuing']) {
      const document = nonformal(purpose);
      document.opportunities[0].status = status;
      document.actions = [{opportunity: route.name, scope_confirmed: true,
        status: 'held', task: 'Keep this fictional task held.', due: '2026-10-01'}];
      const before = structuredClone(document);
      const result = campaignDecision(document, today, route.name);
      assert.equal(result.state, 'no_go');
      assert.match(result.label, /NOT CURRENT/);
      assert.doesNotMatch(result.detail + result.action.task + result.reopenCriteria,
        /funder|future round|official programme/);
      assert.match(result.reopenCriteria, /Held work stays held/);
      assert.equal(Object.hasOwn(result.action, 'due'), false);
      assert.deepEqual(document, before);
    }
  }
});

test('a missing route status is not rewritten or described as a recorded closure', () => {
  const row = {purpose: 'research', name: 'Fictional incomplete record'};
  const before = structuredClone(row);
  const result = campaignRoutePurposeGuidance(row);
  assert.doesNotMatch(result.detail, /recorded as closed/);
  assert.deepEqual(row, before);
  assert.equal(Object.hasOwn(row, 'status'), false);
});

test('a submitted informational record does not become a delivered conversation, application or award', () => {
  const document = nonformal('discussion');
  document.opportunities[0].status = 'submitted';
  document.actions = [{opportunity: route.name, scope_confirmed: true, status: 'open',
    submission_phase: 'post_submission', task: 'Record any documented response.',
    owner_kind: 'unassigned', owner: '', owner_confirmed: false, due: ''}];
  const before = structuredClone(document);
  const result = campaignDecision(document, today);
  assert.equal(result.state, 'awaiting_decision');
  assert.equal(result.label, 'SUBMITTED STATUS RECORDED');
  assert.match(result.detail, /does not establish a formal application, agreement, award/);
  assert.equal(result.action.source, 'recorded');
  assert.equal(result.action.task, document.actions[0].task);
  assert.deepEqual(document, before);
});

test('mixed inactive portfolios preserve legacy state rather than infer purpose for other routes', () => {
  const document = {opportunities: [{name: 'Legacy route', status: 'submitted'},
    {name: 'Fictional discussion', status: 'closed', purpose: 'discussion'}]};
  const result = campaignDecision(document, today);
  assert.equal(result.state, 'awaiting_decision');
  assert.equal(result.label, 'AWAITING FUNDER DECISION');
  assert.equal(Object.hasOwn(document.opportunities[0], 'purpose'), false);
});

test('purpose guidance stays scoped to the selected active route', () => {
  const document = formal();
  document.opportunities.push(nonformal('research').opportunities[0]);
  document.opportunities[1].name = 'Fictional research route';
  const research = campaignDecision(document, today, document.opportunities[1].name);
  assert.equal(research.state, 'in_progress');
  assert.equal(research.focusOpportunity, document.opportunities[1].name);
  const application = campaignDecision(document, today, route.name);
  assert.equal(application.state, 'ready_for_review');
  assert.equal(application.focusOpportunity, route.name);
});
