import assert from 'node:assert/strict';
import test from 'node:test';
import {applicationAnswerAvailability, defaultCampaignOpportunityIndex, hasConfirmedApplicationRoute,
  hasCurrentApplicationWindowEvidence} from '../src/sinter/web/campaign-state.js';

const today = '2026-09-29';
const source = {id: 'a'.repeat(32), url: 'https://example.org/window', checked_at: today};
const verified = (name, status, deadline) => ({name, status, deadline,
  application_window: 'fixed', url: 'https://example.org/fund',
  window_source_id: source.id, window_source_url: source.url,
  window_source_quote: 'Applications close on the recorded date.',
  window_checked_at: today});

test('application answer controls require both a confirmed workflow and applicant', () => {
  assert.equal(hasConfirmedApplicationRoute({application_mode: 'required', applicant: 'School'}), false);
  assert.equal(hasConfirmedApplicationRoute({application_mode: 'required', applicant: 'School', applicant_confirmed: true}), true);
  assert.equal(hasConfirmedApplicationRoute({application_mode: 'required', applicant: '  '}), false);
  assert.equal(hasConfirmedApplicationRoute({application_mode: 'unknown', applicant: 'School'}), false);
  assert.equal(hasConfirmedApplicationRoute({application_mode: 'not_required', applicant: 'School'}), false);
});

test('application answer availability gives a matching lock reason and copy label', () => {
  const inactive = applicationAnswerAvailability({
    status: 'closed', application_mode: 'required', applicant: 'School',
  });
  assert.equal(inactive.allowed, false);
  assert.equal(inactive.reason, 'inactive');
  assert.equal(inactive.copyLabel, 'Copy unavailable · inactive route');
  assert.match(inactive.message, /historical drafts/);

  const noFormalApplication = applicationAnswerAvailability({
    status: 'open', application_mode: 'not_required', applicant: '',
  });
  assert.equal(noFormalApplication.reason, 'not_required');
  assert.equal(noFormalApplication.copyLabel, 'Copy unavailable · no formal application');

  const workflowUnknown = applicationAnswerAvailability({
    status: 'clarification', application_mode: 'unknown', applicant: 'School',
  });
  assert.equal(workflowUnknown.reason, 'workflow_unconfirmed');
  assert.equal(workflowUnknown.copyLabel, 'Copy unavailable · workflow not confirmed');

  const applicantUnknown = applicationAnswerAvailability({
    status: 'open', application_mode: 'required', applicant: '  ',
  });
  assert.equal(applicantUnknown.reason, 'applicant_unconfirmed');
  assert.equal(applicantUnknown.copyLabel, 'Copy unavailable · applicant not recorded');

  const applicantPending = applicationAnswerAvailability({
    status: 'open', application_mode: 'required', applicant: 'Proposed School',
  });
  assert.equal(applicantPending.reason, 'applicant_unconfirmed');
  assert.equal(applicantPending.copyLabel, 'Copy unavailable · applicant not confirmed');
  assert.match(applicantPending.message, /does not establish programme eligibility/);

  const confirmed = applicationAnswerAvailability({
    status: 'upcoming', application_mode: 'required', applicant: 'School',
    applicant_confirmed: true,
  });
  assert.deepEqual(confirmed, {
    allowed: true, reason: '', message: '', copyLabel: 'Copy this answer',
  });
});

test('a near closing date outranks a rolling route and source order', () => {
  const routes = [
    {name: 'Rolling programme', status: 'open', application_window: 'rolling'},
    verified('October deadline', 'clarification', '2026-10-12'),
    verified('Later deadline', 'open', '2026-11-01'),
  ];
  assert.equal(defaultCampaignOpportunityIndex(routes, today, [source]), 1);
});

test('a still-active route with a passed date is brought forward to reconcile its status', () => {
  const routes = [
    {name: 'Rolling programme', status: 'open', application_window: 'rolling'},
    verified('Missed date', 'open', '2026-09-27'),
    verified('Future deadline', 'upcoming', '2026-10-12'),
  ];
  assert.equal(defaultCampaignOpportunityIndex(routes, today, [source]), 1);
});

test('inactive deadlines do not displace an actionable route', () => {
  const routes = [
    {name: 'Closed', status: 'closed', deadline: '2026-09-27'},
    {name: 'Rolling programme', status: 'open', application_window: 'rolling'},
    verified('Future deadline', 'upcoming', '2026-10-12'),
  ];
  assert.equal(defaultCampaignOpportunityIndex(routes, today, [source]), 2);
});

test('routes without dates keep the existing status-first order', () => {
  const routes = [
    {name: 'Needs research', status: 'researching'},
    {name: 'Upcoming', status: 'upcoming'},
    {name: 'Open', status: 'open'},
  ];
  assert.equal(defaultCampaignOpportunityIndex(routes, '2026-09-29'), 2);
});

test('an empty portfolio focuses index zero without inventing a route', () => {
  assert.equal(defaultCampaignOpportunityIndex([], '2026-09-29'), 0);
});

test('an unlinked typed date never outranks a verified deadline', () => {
  const routes = [
    {name: 'Unverified imminent date', status: 'open', deadline: '2026-09-30'},
    verified('Verified later date', 'upcoming', '2026-10-12'),
  ];
  assert.equal(defaultCampaignOpportunityIndex(routes, today, [source]), 1);
});

test('a source refresh invalidates the old application-window quote and its urgency', () => {
  const route = verified('Refreshed source', 'open', '2026-10-12');
  const refreshed = {...source, checked_at: '2026-09-30'};
  assert.equal(hasCurrentApplicationWindowEvidence(route, today, [source]), true);
  assert.equal(hasCurrentApplicationWindowEvidence(route, today, [refreshed]), false);
  assert.equal(defaultCampaignOpportunityIndex([
    {name: 'Earlier fallback', status: 'open'}, route,
  ], today, [refreshed]), 0);
});
