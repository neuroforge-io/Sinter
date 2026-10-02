/** Bounded presentation over the full campaign; rows and indexes are retained. */
export const OPPORTUNITY_PAGE_SIZE = 20;
export const CAMPAIGN_OPPORTUNITY_LIMIT = 200;

export function canAddCampaignOpportunity(rows) {
  return !Array.isArray(rows) || rows.length < CAMPAIGN_OPPORTUNITY_LIMIT;
}

export function campaignOpportunityView(rows, {query = '', status = 'all', page = 0} = {}) {
  const entries = (Array.isArray(rows) ? rows : []).map((row, index) => ({row, index}));
  const needle = typeof query === 'string' ? query.trim().toLowerCase() : '';
  const matched = entries.filter(({row}) => {
    if (status !== 'all' && row?.status !== status) return false;
    if (!needle) return true;
    const text = [row?.name, row?.funder, row?.url, row?.fit, row?.route_type, row?.status,
      ...[row?.route_type, row?.status].filter(value => typeof value === 'string')
        .map(value => value.replaceAll('_', ' '))]
      .filter(value => typeof value === 'string').join(' ').toLowerCase();
    return text.includes(needle);
  });
  const pages = Math.ceil(matched.length / OPPORTUNITY_PAGE_SIZE);
  const current = Math.min(Math.max(0, Number.isSafeInteger(page) ? page : 0), Math.max(0, pages - 1));
  const offset = current * OPPORTUNITY_PAGE_SIZE;
  return {entries: matched.slice(offset, offset + OPPORTUNITY_PAGE_SIZE),
    matchedIndexes: matched.map(({index}) => index),
    total: entries.length, matched: matched.length, page: current, pages,
    start: matched.length ? offset + 1 : 0, end: Math.min(offset + OPPORTUNITY_PAGE_SIZE, matched.length)};
}
