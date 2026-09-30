import {isCampaignActionCurrent, isCampaignActionScopeConfirmed} from './campaign-state.js';
import {campaignActionOwnerState} from './campaign-owner.js';

const ACTIVE_ROUTE_STATES = new Set(['researching', 'open', 'upcoming', 'clarification']);

export function campaignActionPhaseLabel(phase) {
  return ({pre_submission: 'Before submission',
    post_submission: 'After-submission follow-up'})[phase] || 'Not recorded';
}

/** Preserve whether an older saved action ever recorded its scope. */
export function normalizeCampaignActionScopes(actions) {
  return (Array.isArray(actions) ? actions : []).map(row => {
    const next = {...row};
    const hadScope = Object.hasOwn(next, 'opportunity');
    next.opportunity ??= '';
    if (typeof next.scope_confirmed !== 'boolean') next.scope_confirmed = hadScope;
    next.submission_phase ??= 'pre_submission';
    return next;
  });
}

function currentScopeNames(opportunities) {
  if (!Array.isArray(opportunities)) return null;
  const routes = opportunities;
  const current = routes.filter(row => ACTIVE_ROUTE_STATES.has(row.status)
    || row.status === 'submitted');
  return new Set(current.map(row => row.name));
}

function scopeLabel(row, currentNames, opportunities) {
  if (!isCampaignActionScopeConfirmed(row)) return 'Scope not confirmed';
  if (!row.opportunity) return 'Campaign-wide';
  if (currentNames === null) return row.opportunity;
  const route = opportunities.find(item => item.name === row.opportunity);
  if (route?.status === 'submitted') {
    return row.submission_phase === 'post_submission'
      ? `${currentNames.has(row.opportunity) ? 'Submitted follow-up' : 'Historical submitted follow-up'} · ${row.opportunity}`
      : `Historical pre-submission · ${row.opportunity}`;
  }
  if (currentNames.has(row.opportunity)
      && row.submission_phase === 'post_submission') {
    return `Held post-submission · route reactivated · ${row.opportunity}`;
  }
  if (!currentNames.has(row.opportunity)) return `Historical · ${row.opportunity}`;
  return row.opportunity;
}

function planRow(row, currentNames, opportunities) {
  const confirmedScope = isCampaignActionScopeConfirmed(row);
  const owner = campaignActionOwnerState(row.owner, row.owner_confirmed,
    row.owner_kind);
  return {
    action: row.task,
    scope: scopeLabel(row, currentNames, opportunities),
    phase: !confirmedScope ? 'Not assigned · scope unconfirmed'
      : !row.opportunity ? 'Not applicable · campaign-wide'
        : row.submission_phase === 'post_submission'
          ? 'After-submission follow-up' : 'Before submission',
    owner: owner.export,
    due: row.due,
    status: row.status === 'done' ? 'done'
      : row.status === 'held' ? 'held' : 'not_started',
  };
}

/** Convert saved campaign actions into the shared user-entered plan format. */
export function campaignActionRowsForPlan(actions, opportunities = []) {
  const currentNames = currentScopeNames(opportunities);
  return actions.map(row => planRow(row, currentNames, opportunities));
}

/** Only dated, unfinished actions in the current pre/post-submission phase export. */
export function campaignActionRowsForCalendar(actions, opportunities = []) {
  const currentNames = currentScopeNames(opportunities);
  return actions.filter(row => row.status !== 'done' && row.due
    && isCampaignActionCurrent(row, opportunities))
    .map(row => planRow(row, currentNames, opportunities));
}
