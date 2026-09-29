/** Shared browser-side campaign routing policy. Keep in sync with campaigns.py. */
export const ACTIONABLE_OPPORTUNITY_STATES = Object.freeze([
  'researching', 'open', 'upcoming', 'clarification',
]);

const actionableOpportunityStates = new Set(ACTIONABLE_OPPORTUNITY_STATES);
const WINDOW_CHECK_MAX_AGE_DAYS = 90;

function validDay(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
  const stamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(stamp)
    && new Date(stamp).toISOString().slice(0, 10) === value ? stamp : null;
}

/** A date is urgent only when its user-entered source trail is current and consistent. */
export function hasCurrentApplicationWindowEvidence(opportunity, today, sources = []) {
  if (!['fixed', 'rolling'].includes(opportunity?.application_window)
      || !opportunity?.url || !opportunity?.window_source_id
      || !String(opportunity?.window_source_url || '').trim()
      || !String(opportunity?.window_source_quote || '').trim()
      || !opportunity?.window_checked_at) return false;
  const source = sources.find(row => row?.id === opportunity.window_source_id);
  if (!source || source.url !== opportunity.window_source_url
      || source.checked_at !== opportunity.window_checked_at) return false;
  const checked = validDay(opportunity.window_checked_at);
  const current = validDay(today);
  if (checked === null || current === null || checked > current
      || (current - checked) / 86400000 > WINDOW_CHECK_MAX_AGE_DAYS) return false;
  return opportunity.application_window !== 'fixed'
    || Boolean(opportunity.deadline && validDay(opportunity.deadline) !== null);
}

export function isOpportunityActionable(status) {
  return actionableOpportunityStates.has(status);
}

/** Application answers stay locked until both the workflow and applicant are explicit. */
export function hasConfirmedApplicationRoute(opportunity) {
  return opportunity?.application_mode === 'required'
    && typeof opportunity.applicant === 'string'
    && opportunity.applicant.trim().length > 0;
}

/**
 * Pick a useful starting route when opening a campaign without a saved focus.
 * A missed source-checked date needs review before a later route. Unlinked,
 * stale or rolling dates do not steer focus; status order is the fallback.
 */
export function defaultCampaignOpportunityIndex(opportunities, today, sources = []) {
  const rows = Array.isArray(opportunities) ? opportunities : [];
  if (!rows.length) return 0;
  const current = today || (() => {
    const date = new Date();
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0')].join('-');
  })();
  const statusRank = new Map([
    ['open', 0], ['upcoming', 1], ['researching', 2], ['clarification', 3],
  ]);
  const candidates = rows.map((row, index) => ({row, index}))
    .filter(({row}) => isOpportunityActionable(row?.status));
  const rank = ({row}) => statusRank.get(row.status) ?? statusRank.size;
  const dated = candidates.filter(({row}) => row.application_window === 'fixed'
    && row.deadline && hasCurrentApplicationWindowEvidence(row, current, sources));
  const overdue = dated.filter(({row}) => row.deadline < current)
    .sort((left, right) => right.row.deadline.localeCompare(left.row.deadline)
      || rank(left) - rank(right) || left.index - right.index);
  if (overdue.length) return overdue[0].index;
  const upcoming = dated.filter(({row}) => row.deadline >= current)
    .sort((left, right) => left.row.deadline.localeCompare(right.row.deadline)
      || rank(left) - rank(right) || left.index - right.index);
  if (upcoming.length) return upcoming[0].index;
  candidates.sort((left, right) => rank(left) - rank(right)
    || left.index - right.index);
  return candidates[0]?.index ?? 0;
}

export function isCampaignActionScopeConfirmed(action) {
  return action.scope_confirmed === true
    || (action.scope_confirmed !== false && Object.hasOwn(action, 'opportunity'));
}

/** Keep pre- and post-submission tasks on the correct side of a route change. */
export function isCampaignActionCurrent(action, opportunities) {
  if (!isCampaignActionScopeConfirmed(action)) return false;
  if (!action.opportunity) return true;
  const routes = Array.isArray(opportunities) ? opportunities : [];
  const route = routes.find(row => row.name === action.opportunity);
  if (!route) return false;
  if (isOpportunityActionable(route.status)) {
    return action.submission_phase !== 'post_submission';
  }
  return route.status === 'submitted'
    && action.submission_phase === 'post_submission';
}
