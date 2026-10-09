/** Explicit local intent; never infer workflow, eligibility or authority. */
import {isOpportunityActionable} from './campaign-state.js';

export const CAMPAIGN_ROUTE_PURPOSES = Object.freeze([
  ['unknown', 'Not specified'], ['application', 'Application'],
  ['discussion', 'Discussion'], ['research', 'Research'],
]);

export function campaignRoutePurpose(row) {
  return CAMPAIGN_ROUTE_PURPOSES.some(([value]) => value === row?.purpose)
    ? row.purpose : 'unknown';
}

export function campaignRoutePurposeLabel(row) {
  return CAMPAIGN_ROUTE_PURPOSES.find(([value]) => value === campaignRoutePurpose(row))[1];
}

/** A recorded required application always retains the formal application gates. */
export function isNonApplicationRoute(row) {
  return ['discussion', 'research'].includes(campaignRoutePurpose(row))
    && row?.application_mode !== 'required';
}

export function campaignRoutePurposeConflict(row) {
  if (campaignRoutePurpose(row) === 'application'
      && row?.application_mode === 'not_required') {
    return 'This route is labelled application, but its workflow is recorded as “No formal application recorded”. Reconcile the purpose and application workflow explicitly; the label does not establish workflow, eligibility or authority.';
  }
  if (!['discussion', 'research'].includes(campaignRoutePurpose(row))
      || row?.application_mode !== 'required') return '';
  return `This route is labelled ${campaignRoutePurposeLabel(row).toLowerCase()}, but a formal application is recorded as required. Reconcile the purpose and application workflow explicitly; applicant, source and eligibility checks remain in force.`;
}

/** Neutral display guidance from explicit purpose and status, without changing records. */
export function campaignRoutePurposeGuidance(row) {
  if (!isNonApplicationRoute(row)) return null;
  const purpose = campaignRoutePurpose(row);
  const name = typeof row?.name === 'string' && row.name.trim()
    ? `“${row.name.trim()}”` : 'This route';
  if (row.status === 'submitted') {
    return {state: 'awaiting_decision', label: 'SUBMITTED STATUS RECORDED',
      detail: `A submitted status is recorded for ${name}. Confirm what was submitted and what response is outstanding; this record does not establish a formal application, agreement, award or research conclusion.`,
      suggestedTask: 'Check the original communication or submission record and record the response when received.',
      progressCriteria: 'Keep the submitted record as history. Record any response with its source; reassess the scope before starting further work.'};
  }
  if (!isOpportunityActionable(row.status)) {
    const status = row.status === 'paused' ? 'paused'
      : row.status === 'not_pursuing' ? 'not being pursued'
        : row.status === 'closed' ? 'closed' : 'not currently active';
    return {state: 'no_go', label: `${purpose.toUpperCase()} NOT CURRENT`,
      detail: `${name} is recorded as ${status}. Its correspondence, evidence and unfinished work remain historical records; no active commitment is established.`,
      suggestedTask: 'Review the retained scope and evidence before deciding whether to resume this route.',
      progressCriteria: 'Resume only after an explicit decision to change the route status and review its scope, evidence and permissions. Held work stays held until explicitly resumed.'};
  }
  return purpose === 'discussion'
    ? {state: 'in_progress', label: 'DISCUSSION IN PROGRESS',
      detail: `${name} is a recorded discussion route. Track the other party’s position, unresolved questions and proposed next steps; this label does not establish an agreement, income or authority.`,
      suggestedTask: 'Record the discussion scope and the next question to clarify with the counterpart.',
      progressCriteria: 'Progress when the discussion scope and next step are recorded and any commitments are confirmed with the responsible person. A formal application, if required, needs its own recorded workflow and checks.'}
    : {state: 'in_progress', label: 'RESEARCH IN PROGRESS',
      detail: `${name} is a recorded research route. Preserve source evidence and distinguish findings from questions still to check; this label does not establish novelty, rights, eligibility or authority.`,
      suggestedTask: 'Record the specific research question and the source evidence to check next.',
      progressCriteria: 'Progress when the research question, selected evidence and remaining uncertainty are recorded. Confirm permissions before using restricted material; any formal application still needs its own workflow and checks.'};
}
