/** Conservative, read-only overview for the campaign workspace. */
import {isCampaignActionCurrent, isCampaignActionScopeConfirmed,
  isOpportunityActionable} from './campaign-state.js';
import {campaignActionOwnerState} from './campaign-owner.js';
import {campaignCurrencyComparisonNote} from './campaign-currency.js';
import {campaignSourceSnapshotGuidance,
  campaignSourceSnapshotIssue} from './campaign-source-state.js';

export const CAMPAIGN_DECISION_NOTE = 'Based on your records. Sinter has not verified sources, eligibility or authority; this is not permission to submit.';

const hasText = value => typeof value === 'string' && value.trim().length > 0;
const WINDOW_CHECK_MAX_AGE_DAYS = 90;
const parseDay = value => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed)
    && new Date(parsed).toISOString().slice(0, 10) === value ? parsed : null;
};

function requirementDateGap(checkedAt, today) {
  if (!hasText(checkedAt)) return 'Record the date this eligibility source was checked.';
  const checked = parseDay(checkedAt), current = parseDay(today);
  if (checked === null || current === null) {
    return 'Record a valid date for this eligibility source check.';
  }
  if (checked > current) return `The eligibility source check date (${checkedAt}) is in the future; correct it.`;
  const ageDays = Math.floor((current - checked) / 86400000);
  return ageDays > WINDOW_CHECK_MAX_AGE_DAYS
    ? `The eligibility source was last checked ${ageDays} days ago; recheck it (within ${WINDOW_CHECK_MAX_AGE_DAYS} days).`
    : '';
}

function sourceVersionGap(row, sources = []) {
  if (!hasText(row?.source_id)) return '';
  const linked = sources.find(source => source?.id === row.source_id);
  return campaignSourceSnapshotGuidance(campaignSourceSnapshotIssue(
    row.source_url, row.checked_at, linked));
}

const sourceComplete = (row, today, sources = []) => ['evidence', 'source_url', 'source_quote']
  .every(key => hasText(row?.[key])) && !requirementDateGap(row?.checked_at, today)
  && !sourceVersionGap(row, sources);
const sourceFields = [
  ['evidence', 'applicant-specific evidence'],
  ['source_url', 'a current official source link'],
  ['source_quote', 'a source excerpt'],
];

function sourceRecordGuidance(row, today, sources = []) {
  const missing = sourceFields.filter(([key]) => !hasText(row?.[key]))
    .map(([, label]) => label);
  const fields = missing.length < 2 ? missing[0]
    : `${missing.slice(0, -1).join(', ')} and ${missing.at(-1)}`;
  // Field labels are noun phrases; date and snapshot guidance are complete
  // sentences. Keep each instruction intact instead of joining unlike parts.
  return [fields ? `Record ${fields}.` : '',
    requirementDateGap(row?.checked_at, today), sourceVersionGap(row, sources)]
    .filter(Boolean).join(' ');
}

function requirementGap(check, today, sources = []) {
  const name = hasText(check.rule) ? `“${check.rule.trim()}”` : 'This eligibility check';
  const complete = sourceComplete(check, today, sources);
  if (check.status === 'not_met') {
    return `${name} is marked not met in the user-entered record.`;
  }
  if (check.status === 'clarification') {
    return complete
      ? `${name} has a source and applicant-evidence record but remains marked for clarification; resolve the interpretation and update its status.`
      : `${name} remains marked for clarification. ${sourceRecordGuidance(check, today, sources)} Resolve the interpretation and update its status.`;
  }
  if (check.status === 'unknown') {
    return complete
      ? `${name} has a complete evidence record but remains unassessed; review it and record the applicant-specific status.`
      : `${name} is not assessed. ${sourceRecordGuidance(check, today, sources)}`;
  }
  return `${name} is marked met, but its source record is incomplete or out of date. ${sourceRecordGuidance(check, today, sources)}`;
}

function firstUnmetRequirement(checks) {
  // This is a user-entered blocker, not verified programme ineligibility.
  // Keep source order when several checks are marked not met.
  return checks.find(row => row.status === 'not_met');
}

function windowCheckGap(checkedAt, today, label) {
  if (!hasText(checkedAt)) {
    return `Record when the ${label} was checked.`;
  }
  const checked = parseDay(checkedAt);
  const current = parseDay(today);
  if (checked === null || current === null) {
    return 'Record a valid date for the application-window source check.';
  }
  if (checked > current) {
    return `The application-window check date (${checkedAt}) is in the future; correct it.`;
  }
  const ageDays = Math.floor((current - checked) / 86400000);
  return ageDays > WINDOW_CHECK_MAX_AGE_DAYS
    ? `The application window was last checked ${ageDays} days ago; recheck the official wording (within ${WINDOW_CHECK_MAX_AGE_DAYS} days).`
    : '';
}

function applicationWindowSourceGap(opportunity, sources) {
  if (!hasText(opportunity.window_source_id)) {
    return 'Link a registered official source to the application window, then recheck the exact wording.';
  }
  const source = sources.find(row => row?.id === opportunity.window_source_id);
  return campaignSourceSnapshotGuidance(campaignSourceSnapshotIssue(
    opportunity.window_source_url, opportunity.window_checked_at, source));
}

export function applicationWindowGaps(opportunity, today, sources = []) {
  const kind = opportunity.application_window
    || (opportunity.deadline ? 'fixed' : 'unknown');
  if (kind === 'rolling') {
    const gaps = [];
    if (!hasText(opportunity.window_source_quote)) {
      gaps.push('Add exact official wording that confirms the rolling application window.');
    }
    const checkedGap = windowCheckGap(opportunity.window_checked_at, today,
      'rolling application wording');
    if (checkedGap) gaps.push(checkedGap);
    const sourceGap = applicationWindowSourceGap(opportunity, sources);
    if (sourceGap) gaps.push(sourceGap);
    return gaps;
  }
  if (kind === 'fixed') {
    const gaps = [];
    if (!opportunity.deadline) gaps.push('Record the fixed application closing date.');
    else if (opportunity.deadline < today) {
      gaps.push(`The recorded closing date (${opportunity.deadline}) has passed; confirm the route status.`);
    }
    if (!hasText(opportunity.window_source_quote)) {
      gaps.push('Add exact official wording that confirms the closing date.');
    }
    const checkedGap = windowCheckGap(opportunity.window_checked_at, today,
      'closing-date wording');
    if (checkedGap) gaps.push(checkedGap);
    const sourceGap = applicationWindowSourceGap(opportunity, sources);
    if (sourceGap) gaps.push(sourceGap);
    return gaps;
  }
  return ['Confirm whether applications use a fixed closing date or a rolling window.'];
}

function routeGaps(opportunity, requirements, today, sources = []) {
  const gaps = [];
  const checks = requirements.filter(row => row.opportunity === opportunity.name);
  const unmet = firstUnmetRequirement(checks);
  if (unmet) gaps.push(requirementGap(unmet, today, sources));
  if (opportunity.status === 'researching') {
    gaps.push('Confirm that a current round is open from the official programme page.');
  } else if (opportunity.status === 'clarification') {
    const unresolved = checks.find(row => row.status === 'clarification')
      || checks.find(row => row.status !== 'met'
        || !sourceComplete(row, today, sources));
    if (unresolved) {
      gaps.push('Review the unresolved eligibility check: '
        + requirementGap(unresolved, today, sources));
    } else {
      gaps.push('This route is marked for clarification, but no unresolved applicant check identifies why. Record the outstanding point in the eligibility checks before deciding whether current rules or applicant evidence resolves it.');
    }
  }
  const applicationMode = opportunity.application_mode || 'unknown';
  if (applicationMode === 'unknown') {
    gaps.push('Confirm whether this route needs a formal application and who is allowed to apply.');
  } else if (applicationMode === 'required' && !hasText(opportunity.applicant)) {
    gaps.push('Record which organisation or person must submit the application.');
  } else if (applicationMode === 'required'
      && opportunity.applicant_confirmed !== true) {
    gaps.push('Confirm the named applicant directly with the person responsible for applying; this does not establish programme eligibility or authority to submit.');
  }
  if (!hasText(opportunity.url)) gaps.push('Add the current official programme page.');
  gaps.push(...applicationWindowGaps(opportunity, today, sources));

  if (!checks.length) {
    gaps.push('No applicant eligibility checks are recorded.');
  } else {
    for (const check of checks) {
      if (check.status !== 'met' || !sourceComplete(check, today, sources)) {
        gaps.push(requirementGap(check, today, sources));
      }
    }
  }
  const currencyGap = campaignCurrencyComparisonNote(opportunity);
  if (currencyGap) gaps.push(currencyGap);
  return gaps;
}

function routeFocus(active, requestedName) {
  const requested = active.find(row => row.name === requestedName);
  return requested || active[0] || null;
}

function reopenedWhen(document, state, today, focus) {
  const sources = Array.isArray(document?.sources) ? document.sources : [];
  const routes = Array.isArray(document?.opportunities) ? document.opportunities : [];
  const notMet = (Array.isArray(document?.requirements) ? document.requirements : [])
    .filter(row => row.status === 'not_met');
  if (state === 'no_go') {
    const criteria = [];
    if (routes.some(row => row.status === 'closed')) {
      criteria.push('a funder publishes a future round; record its official page, dates and current applicant rules');
    }
    if (routes.some(row => row.status === 'paused')) {
      criteria.push('the recorded pause is resolved and current official dates and applicant rules are checked');
    }
    if (routes.some(row => row.status === 'not_pursuing')) {
      criteria.push('group priorities or capacity change and a live round is confirmed against current official rules');
    }
    if (!criteria.length) {
      criteria.push('a new active route is recorded with current official dates and applicant rules');
    }
    if (notMet.length) {
      const check = notMet[0];
      const rule = hasText(check.rule) ? `“${check.rule.trim()}”` : 'unmet check';
      criteria.push(sourceComplete(check, today, sources)
        ? `new applicant evidence and a dated, exact excerpt from current official guidance resolve ${rule}`
        : `the user-marked ${rule} is reassessed with a current dated official excerpt and applicant-specific evidence`);
      if (notMet.length > 1) criteria.push('all other recorded unmet checks are reassessed on the same evidence basis');
    }
    return `Reopen only when ${criteria.join('; or ')}.`;
  }
  if (state === 'awaiting_decision') {
    return 'Record the funder’s decision when received. Before restarting after a decision or for another round, check the current official dates and applicant rules.';
  }
  if (state === 'not_assessed') {
    return 'Assess a route only after recording its current official programme page, application window and applicant eligibility wording.';
  }
  if (state === 'ready_for_review') {
    return 'Keep this at human review. Recheck the current official guidance, the applicant evidence and P&C authority before any submission.';
  }
  return `After resolving the blocker above, review the remaining applicant checks and application window in Opportunities. Reassess ${focus ? `“${focus.name}”` : 'this route'} against current official wording and applicant evidence; keep unresolved checks open.`;
}

function suggestedAction(state, active, document, today, focus) {
  const sources = Array.isArray(document?.sources) ? document.sources : [];
  if (state === 'no_go') return 'Check whether a future round has been published by the funder.';
  if (state === 'awaiting_decision') return 'Record the funder’s decision when it arrives.';
  if (state === 'not_assessed') return 'Record a current official funding route before assessing eligibility.';
  if (state === 'ready_for_review') return 'Ask a P&C reviewer to check the recorded eligibility evidence and authority.';
  const ordered = focus ? [focus] : active;
  for (const opportunity of ordered) {
    const checks = (document.requirements || []).filter(row =>
      row.opportunity === opportunity.name);
    const unmet = firstUnmetRequirement(checks);
    if (unmet) return requirementGap(unmet, today, sources);
    if (opportunity.status === 'clarification') {
      const unresolved = checks.find(row => row.status === 'clarification')
        || checks.find(row => row.status !== 'met'
          || !sourceComplete(row, today, sources));
      if (unresolved) {
        return 'Review the unresolved eligibility check: '
          + requirementGap(unresolved, today, sources);
      }
      return `“${opportunity.name}” is marked for clarification, but no unresolved applicant check identifies why. Record the outstanding point in the eligibility checks before deciding whether current rules or applicant evidence resolves it.`;
    }
    if (opportunity.status === 'researching') {
      return `Confirm that “${opportunity.name}” has a current round open on the official programme page.`;
    }
    if (!opportunity.application_mode || opportunity.application_mode === 'unknown') {
      return `Confirm whether “${opportunity.name}” needs a formal application and who is allowed to apply.`;
    }
    if (opportunity.application_mode === 'required'
        && !hasText(opportunity.applicant)) {
      return `Record which organisation or person must submit the application for “${opportunity.name}”.`;
    }
    if (opportunity.application_mode === 'required'
        && opportunity.applicant_confirmed !== true) {
      return `Confirm the named applicant directly with the person responsible for applying for “${opportunity.name}”; this does not establish programme eligibility or authority to submit.`;
    }
    if (!hasText(opportunity.url)) {
      return `Add the current official programme page for “${opportunity.name}”.`;
    }
    const timingGap = applicationWindowGaps(opportunity, today, sources)[0];
    if (timingGap) {
      return `Resolve the application window for “${opportunity.name}”: ${timingGap}`;
    }
    if (!checks.length) {
      return `Record the applicant eligibility checks for “${opportunity.name}” from current official guidance.`;
    }
    const openCheck = checks.find(row => row.status !== 'met'
      || !sourceComplete(row, today, sources));
    if (openCheck) {
      return requirementGap(openCheck, today, sources);
    }
    const currencyGap = campaignCurrencyComparisonNote(opportunity);
    if (currencyGap) return currencyGap;
  }
  return 'Review the next unresolved campaign item against current funder guidance.';
}

/**
 * Build a display-only decision and one next move from saved campaign fields.
 * It never mutates the document and never claims eligibility is verified.
 */
export function campaignDecision(document, today, focusedOpportunityName = '') {
  const opportunities = Array.isArray(document?.opportunities) ? document.opportunities : [];
  const requirements = Array.isArray(document?.requirements) ? document.requirements : [];
  const actions = Array.isArray(document?.actions) ? document.actions : [];
  const sources = Array.isArray(document?.sources) ? document.sources : [];
  const localToday = today || (() => {
    const date = new Date();
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0')].join('-');
  })();
  const active = opportunities.filter(row => isOpportunityActionable(row.status));
  const focus = routeFocus(active, focusedOpportunityName);

  let state, label, detail;
  if (!opportunities.length) {
    state = 'not_assessed';
    label = 'NOT ASSESSED';
    detail = 'No funding route is recorded, so there is no go/no-go decision yet.';
  } else if (!active.length && opportunities.some(row => row.status === 'submitted')) {
    state = 'awaiting_decision';
    label = 'AWAITING FUNDER DECISION';
    detail = 'Every current route is inactive or submitted. A submitted status is not an award or a rejection.';
  } else if (!active.length) {
    state = 'no_go';
    label = 'NO-GO FOR NOW';
    detail = 'No opportunity is recorded as active for this campaign.';
  } else {
    const focusedGaps = focus ? routeGaps(focus, requirements, localToday, sources) : [];
    if (focus && focusedGaps.length === 0) {
      state = 'ready_for_review';
      label = 'HUMAN REVIEW REQUIRED';
      detail = `“${focus.name}” has complete user-entered screening records and requires human review.`;
    } else {
      state = 'not_ready';
      label = 'NOT READY';
      const gap = focusedGaps[0] || 'current programme details or applicant-specific eligibility evidence';
      detail = `“${focus?.name || 'The selected route'}” is not ready for human review. ${gap}`;
    }
  }

  const openActions = actions.map((action, index) => ({action, index}))
    .filter(({action}) => action.status !== 'done' && hasText(action.task)
      && isCampaignActionCurrent(action, opportunities));
  const byUrgency = rows => {
    const overdue = rows.filter(({action}) => action.due && action.due < localToday)
      .sort((left, right) => left.action.due.localeCompare(right.action.due)
        || left.index - right.index);
    const upcoming = rows.filter(({action}) => action.due && action.due >= localToday)
      .sort((left, right) => left.action.due.localeCompare(right.action.due)
        || left.index - right.index);
    return overdue[0] || upcoming[0] || rows.find(({action}) => !action.due) || rows[0];
  };
  const routeActions = focus
    ? openActions.filter(({action}) => action.opportunity === focus.name) : [];
  const campaignActions = openActions.filter(({action}) => !hasText(action.opportunity));
  const otherRouteActions = openActions.filter(({action}) => hasText(action.opportunity)
    && action.opportunity !== focus?.name);
  // Keep the decision card aligned with its selected route. Route-specific
  // actions win, then genuinely campaign-wide work, then another route.
  const next = byUrgency(routeActions) || byUrgency(campaignActions)
    || byUrgency(otherRouteActions);
  let action;
  if (next) {
    const row = next.action;
    const owner = campaignActionOwnerState(row.owner, row.owner_confirmed,
      row.owner_kind);
    const ownerNeeded = owner.kind !== 'person' || row.owner_confirmed !== true;
    action = {
      source: 'recorded', task: row.task.trim(), actionIndex: next.index, ownerNeeded,
      opportunity: row.opportunity || '',
      ownerStatus: owner.detail,
      ...(row.due ? {due: row.due} : {}),
    };
  } else {
    const unconfirmedScopeCount = actions.filter(action => action.status !== 'done'
      && hasText(action.task) && !isCampaignActionScopeConfirmed(action)).length;
    const submissionPhaseReviewCount = actions.filter(action => {
      if (action.status === 'done' || !hasText(action.task)
          || !isCampaignActionScopeConfirmed(action)) return false;
      const route = opportunities.find(row => row.name === action.opportunity);
      return route?.status === 'submitted'
        && action.submission_phase !== 'post_submission';
    }).length;
    const reactivatedRouteReviewCount = actions.filter(action => {
      if (action.status === 'done' || !hasText(action.task)
          || !isCampaignActionScopeConfirmed(action)
          || action.submission_phase !== 'post_submission') return false;
      const route = opportunities.find(row => row.name === action.opportunity);
      return Boolean(route && isOpportunityActionable(route.status));
    }).length;
    const inactiveRouteReviewCount = actions.filter(action => {
      if (action.status === 'done' || !hasText(action.task)
          || !isCampaignActionScopeConfirmed(action) || !hasText(action.opportunity)) return false;
      const route = opportunities.find(row => row.name === action.opportunity);
      return ['closed', 'paused', 'not_pursuing'].includes(route?.status);
    }).length;
    action = {
      source: 'suggested', task: unconfirmedScopeCount
        ? `Confirm the scope of ${unconfirmedScopeCount} older action(s) before treating them as current campaign work.`
        : submissionPhaseReviewCount
          ? `Review ${submissionPhaseReviewCount} unfinished pre-submission action(s) on submitted route(s). Mark only genuine follow-up work as after-submission.`
          : reactivatedRouteReviewCount
            ? `Review ${reactivatedRouteReviewCount} open action(s) on reactivated route(s). Reclassify them as before-submission work or keep them held.`
            : inactiveRouteReviewCount
              ? `Review ${inactiveRouteReviewCount} open action(s) on inactive route(s). Move continuing work to a current scope or mark obsolete actions done.`
              : suggestedAction(state, active, {requirements, sources}, localToday, focus),
      ownerNeeded: true, ownerStatus: 'Owner needed — no person is recorded.',
    };
  }

  return {state, label, detail, action, focusOpportunity: focus?.name || '',
    reopenCriteria: reopenedWhen(document, state, localToday, focus)};
}
