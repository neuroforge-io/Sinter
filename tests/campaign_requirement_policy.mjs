import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignRequirementNeedsReview, campaignRequirementSourceComplete,
  campaignRequirementSourceGuidance}
  from '../src/sinter/web/campaign-requirement-policy.js';
import {campaignDecision} from '../src/sinter/web/campaign-decision.js';

const today = '2026-09-29';
const sourceId = 'b'.repeat(32);
const requirement = {
  opportunity: 'Fictional fund', rule: 'Applicant category', status: 'met',
  evidence: 'The fictional applicant category is recorded.',
  source_id: sourceId, source_url: 'https://example.invalid/rules',
  source_quote: 'The fictional category can apply.', checked_at: today,
};
const linkedSource = {
  id: sourceId, url: requirement.source_url, checked_at: today,
};
const route = {
  name: requirement.opportunity, status: 'open', url: 'https://example.invalid/fund',
  application_mode: 'required', applicant: 'Fictional association',
  applicant_confirmed: true, application_window: 'fixed', deadline: '2026-10-30',
  window_source_id: 'a'.repeat(32), window_source_url: 'https://example.invalid/window',
  window_source_quote: 'Applications close on 30 October 2026.', window_checked_at: today,
};
const windowSource = {
  id: route.window_source_id, url: route.window_source_url, checked_at: today,
};
const decide = (row, sources) => campaignDecision({
  opportunities: [route], requirements: [row], sources: [windowSource, ...sources],
}, today);

for (const [label, checkedAt, needsReview, guidance] of [
  ['fresh', today, false, /^$/],
  ['exactly 90 days old', '2026-07-01', false, /^$/],
  ['91 days old', '2026-06-30', true, /last checked 91 days ago/],
  ['future', '2026-09-30', true, /is in the future/],
  ['impossible calendar day', '2026-02-30', true, /Record a valid date/],
  ['invalid format', '29/09/2026', true, /Record a valid date/],
  ['missing date', '', true, /Record the date/],
]) {
  test(`summary and decision agree when a met source is ${label}`, () => {
    const row = {...requirement, checked_at: checkedAt};
    const sources = [{...linkedSource, checked_at: checkedAt}];
    const before = JSON.stringify({row, sources});
    assert.equal(campaignRequirementNeedsReview(row, today, sources), needsReview);
    assert.equal(campaignRequirementSourceComplete(row, today, sources), !needsReview);
    assert.match(campaignRequirementSourceGuidance(row, today, sources), guidance);
    const decision = decide(row, sources);
    assert.equal(decision.state, needsReview ? 'not_ready' : 'ready_for_review');
    if (needsReview) assert.match(decision.detail, guidance);
    assert.equal(JSON.stringify({row, sources}), before);
  });
}

for (const [label, sources, rowChanges, guidance] of [
  ['missing linked source', [], {}, /linked campaign source is missing/],
  ['changed URL', [{...linkedSource, url: 'https://example.invalid/new-rules'}], {},
    /saved source URL differs/],
  ['changed check date', [{...linkedSource, checked_at: '2026-09-28'}], {},
    /saved check date differs/],
  ['missing current URL', [{...linkedSource, url: ''}], {}, /source has no URL/],
  ['missing saved URL', [linkedSource], {source_url: ''}, /No source URL snapshot was saved/],
  ['missing current date', [{...linkedSource, checked_at: ''}], {}, /source has no check date/],
  ['missing saved date', [linkedSource], {checked_at: ''}, /No source check date was saved/],
]) {
  test(`summary and decision retain the ${label} identity gate`, () => {
    const row = {...requirement, ...rowChanges};
    assert.equal(campaignRequirementNeedsReview(row, today, sources), true);
    assert.equal(campaignRequirementSourceComplete(row, today, sources), false);
    assert.match(campaignRequirementSourceGuidance(row, today, sources), guidance);
    const decision = decide(row, sources);
    assert.equal(decision.state, 'not_ready');
    assert.match(decision.detail, guidance);
  });
}

test('a fully recorded not-met verdict needs no evidence refresh but still blocks its route', () => {
  const row = {...requirement, status: 'not_met'};
  assert.equal(campaignRequirementNeedsReview(row, today, [linkedSource]), false);
  assert.equal(campaignRequirementSourceComplete(row, today, [linkedSource]), true);
  const decision = decide(row, [linkedSource]);
  assert.equal(decision.state, 'not_ready');
  assert.match(decision.detail, /marked not met in the user-entered record/);
  assert.match(decision.action.task, /marked not met in the user-entered record/);
});

test('an incomplete or stale not-met verdict is counted for review without changing its verdict', () => {
  for (const changes of [{evidence: ''}, {checked_at: '2026-06-30'}]) {
    const row = {...requirement, status: 'not_met', ...changes};
    const sources = [{...linkedSource, checked_at: row.checked_at}];
    assert.equal(campaignRequirementNeedsReview(row, today, sources), true);
    const decision = decide(row, sources);
    assert.equal(decision.state, 'not_ready');
    assert.match(decision.detail, /marked not met in the user-entered record/);
    assert.equal(row.status, 'not_met');
  }
});

test('complete unknown and clarification records still need an explicit assessment', () => {
  for (const status of ['unknown', 'clarification']) {
    const row = {...requirement, status};
    assert.equal(campaignRequirementNeedsReview(row, today, [linkedSource]), true);
    assert.equal(campaignRequirementSourceComplete(row, today, [linkedSource]), true);
    assert.equal(decide(row, [linkedSource]).state, 'not_ready');
  }
});

test('complete legacy unlinked evidence remains usable without inventing a source ID', () => {
  for (const source_id of [undefined, '']) {
    const row = {...requirement};
    if (source_id === undefined) delete row.source_id;
    else row.source_id = source_id;
    const before = JSON.stringify(row);
    assert.equal(campaignRequirementNeedsReview(row, today), false);
    assert.equal(campaignRequirementSourceComplete(row, today), true);
    assert.equal(decide(row, []).state, 'ready_for_review');
    assert.equal(JSON.stringify(row), before);
  }
});

test('missing source text or applicant evidence cannot disappear from the summary count', () => {
  for (const key of ['evidence', 'source_url', 'source_quote']) {
    const row = {...requirement, [key]: '  '};
    assert.equal(campaignRequirementNeedsReview(row, today, [linkedSource]), true);
    assert.equal(decide(row, [linkedSource]).state, 'not_ready');
  }
  assert.equal(campaignRequirementNeedsReview(undefined, today), true);
});

test('an invalid evaluation date never admits a met requirement as current', () => {
  assert.equal(campaignRequirementNeedsReview(requirement, '2026-02-30', [linkedSource]), true);
  assert.match(campaignRequirementSourceGuidance(requirement, '', [linkedSource]), /Record a valid date/);
});

test('evidence assessment is read-only for frozen rows and source snapshots', () => {
  const row = Object.freeze({...requirement, checked_at: '2026-06-30'});
  const sources = Object.freeze([Object.freeze({...linkedSource,
    checked_at: '2026-06-30'})]);
  const before = JSON.stringify({row, sources});
  assert.equal(campaignRequirementNeedsReview(row, today, sources), true);
  assert.equal(campaignRequirementSourceComplete(row, today, sources), false);
  assert.match(campaignRequirementSourceGuidance(row, today, sources), /last checked 91 days ago/);
  decide(row, sources);
  assert.equal(JSON.stringify({row, sources}), before);
});
