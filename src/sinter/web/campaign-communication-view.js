/** Presentation only: retain canonical rows and their original array indexes. */
export const COMMUNICATION_ORDERS = Object.freeze([
  ['record', 'Record order'], ['newest', 'Newest dated first'],
  ['oldest', 'Oldest dated first'],
]);

export function communicationHasDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)
      || Number(value.slice(0, 4)) < 1) return false;
  const stamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(stamp)
    && new Date(stamp).toISOString().slice(0, 10) === value;
}

/** Search saved wording, including evidence snapshots, never current source text. */
export function campaignCommunicationView(rows, {query = '', route = null,
  order = 'record'} = {}) {
  const needle = typeof query === 'string' ? query.trim().toLowerCase() : '';
  const scoped = typeof route === 'string';
  const entries = (Array.isArray(rows) ? rows : []).map((row, index) => ({row, index}));
  const visible = entries.filter(({row}) => {
    if (scoped && (row?.opportunity || '') !== route) return false;
    if (!needle) return true;
    const savedLinks = Array.isArray(row?.evidence_links) ? row.evidence_links : [];
    const text = [row?.subject, row?.counterparty, row?.content, row?.opportunity,
      row?.date, row?.direction, row?.status, row?.channel,
      ...savedLinks.flatMap(link => [link?.title, link?.url, link?.notes, link?.checked_at])]
      .filter(value => typeof value === 'string').join(' ').toLowerCase();
    return text.includes(needle);
  });
  if (order === 'newest' || order === 'oldest') {
    visible.sort((left, right) => {
      const leftDated = communicationHasDate(left.row?.date);
      const rightDated = communicationHasDate(right.row?.date);
      if (leftDated !== rightDated) return leftDated ? -1 : 1;
      if (!leftDated) return left.index - right.index;
      const dateOrder = left.row.date.localeCompare(right.row.date);
      return (order === 'newest' ? -dateOrder : dateOrder) || left.index - right.index;
    });
  }
  return visible;
}
