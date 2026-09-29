/** Conservative, read-only overview for the campaign workspace. */
import {isOpportunityActionable} from './campaign-state.js';

const hasText = value => typeof value === 'string' && value.trim().length > 0;
const sourceComplete = row => ['evidence', 'source_url', 'source_quote', 'checked_at']
  .every(key => hasText(row?.[key]));

function routeGaps(opportunity, requirements, today) {
  const gaps = [];
  if (opportunity.status === 'researching') {
    gaps.push('Confirm that a current round is open from the official programme page.');
  } else if (opportunity.status === 'clarification') {
    gaps.push('Resolve the outstanding programme clarification and update the route status before human review.');
  }
  if (!hasText(opportunity.url)) gaps.push('Add the current official programme page.');
  if (!opportunity.deadline) gaps.push('Confirm the application closing date.');
  else if (opportunity.deadline < today) {
    gaps.push(`The recorded closing date (${opportunity.deadline}) has passed; confirm the route status.`);
  }

  const checks = requirements.filter(row => row.opportunity === opportunity.name);
  if (!checks.length) {
    gaps.push('No applicant eligibility checks are recorded.');
  } else {
    for (const check of checks) {
      if (check.status !== 'met' || !sourceComplete(check)) {
        const name = hasText(check.rule) ? `“${check.rule.trim()}”` : 'an eligibility check';
        gaps.push(check.status === 'not_met'
          ? `${name} is marked not met in the user-entered record.`
          : `${name} needs a current source excerpt, check date and applicant evidence.`);
      }
    }
  }
  return gaps;
}

function routeFocus(active, requestedName) {
  const requested = active.find(row => row.name === requestedName);
  return requested || active[0] || null;
}

function reopenedWhen(document, state, active, today, focus) {
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
      criteria.push(sourceComplete(check)
        ? `new applicant evidence and a dated, exact excerpt from current official guidance resolve ${rule}`
        : `the user-marked ${rule} is reassessed with a current dated official excerpt and applicant-specific evidence`);
      if (notMet.length > 1) criteria.push('all other recorded unmet checks are reassessed on the same evidence basis');
    }
    return `Reopen only when ${criteria.join('; or ')}. These records are user-entered and unverified by Sinter.`;
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
  const gap = focus && routeGaps(focus,
    Array.isArray(document?.requirements) ? document.requirements : [], today)[0];
  return gap
    ? `Resolve this recorded gap with current official wording, an exact excerpt, a check date and applicant-specific evidence: ${gap} Sinter does not verify these entries.`
    : 'Reassess after recording current official guidance and applicant-specific evidence for every route.';
}

function suggestedAction(state, active, document, today, focus) {
  if (state === 'no_go') return 'Check whether a future round has been published by the funder.';
  if (state === 'awaiting_decision') return 'Record the funder’s decision when it arrives.';
  if (state === 'not_assessed') return 'Record a current official funding route before assessing eligibility.';
  if (state === 'ready_for_review') return 'Ask a P&C reviewer to check the recorded eligibility evidence and authority.';
  const ordered = focus ? [focus] : active;
  for (const opportunity of ordered) {
    if (opportunity.status === 'clarification') {
      return `Resolve the outstanding clarification for “${opportunity.name}” with the funder and update the route status before human review.`;
    }
    if (opportunity.status === 'researching') {
      return `Confirm that “${opportunity.name}” has a current round open on the official programme page.`;
    }
    const checks = (document.requirements || []).filter(row => row.opportunity === opportunity.name);
    if (!checks.length) {
      return `Record the applicant eligibility checks for “${opportunity.name}” from current official guidance.`;
    }
    const openCheck = checks.find(row => row.status !== 'met' || !sourceComplete(row));
    if (openCheck) {
      const label = hasText(openCheck.rule) ? `“${openCheck.rule.trim()}”` : 'the next eligibility check';
      return `Resolve ${label} against current official guidance and record the excerpt, date and applicant evidence.`;
    }
    if (!hasText(opportunity.url) || !opportunity.deadline || opportunity.deadline < today) {
      return `Confirm the current official programme page, application date and route status for “${opportunity.name}”.`;
    }
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
    const focusedGaps = focus ? routeGaps(focus, requirements, localToday) : [];
    if (focus && focusedGaps.length === 0) {
      state = 'ready_for_review';
      label = 'READY FOR HUMAN REVIEW';
      detail = `“${focus.name}” has complete user-entered screening records. Sinter has not verified the sources, eligibility or P&C authority; this is not clearance to apply.`;
    } else {
      state = 'not_ready';
      label = 'NOT READY';
      const gap = focusedGaps[0] || 'current programme details or applicant-specific eligibility evidence';
      detail = `“${focus?.name || 'The selected route'}” is not ready for human review: ${gap} Sinter has not verified these entries.`;
    }
  }

  const openActions = actions.map((action, index) => ({action, index}))
    .filter(({action}) => action.status !== 'done' && hasText(action.task));
  const overdue = openActions.filter(({action}) => action.due && action.due < localToday)
    .sort((left, right) => left.action.due.localeCompare(right.action.due) || left.index - right.index);
  const next = overdue[0] || openActions[0];
  let action;
  if (next) {
    const row = next.action;
    const owner = String(row.owner || '').trim();
    const ownerNeeded = !owner || /\bunassigned\b/i.test(owner) || row.owner_confirmed !== true;
    action = {
      source: 'recorded', task: row.task.trim(), ownerNeeded,
      ownerStatus: !owner || /\bunassigned\b/i.test(owner) ? 'Owner needed — no person is recorded.'
        : row.owner_confirmed === true ? 'Acceptance recorded by user; verify directly.'
          : 'Confirm whether the recorded person has accepted.',
      ...(row.due ? {due: row.due} : {}),
    };
  } else {
    action = {
      source: 'suggested', task: suggestedAction(state, active, {requirements}, localToday, focus),
      ownerNeeded: true, ownerStatus: 'Owner needed — no person is recorded.',
    };
  }

  return {state, label, detail, action, focusOpportunity: focus?.name || '',
    reopenCriteria: reopenedWhen(document, state, active, localToday, focus)};
}
