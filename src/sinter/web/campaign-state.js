/** Shared browser-side campaign routing policy. Keep in sync with campaigns.py. */
export const ACTIONABLE_OPPORTUNITY_STATES = Object.freeze([
  'researching', 'open', 'upcoming', 'clarification',
]);

const actionableOpportunityStates = new Set(ACTIONABLE_OPPORTUNITY_STATES);

export function isOpportunityActionable(status) {
  return actionableOpportunityStates.has(status);
}
