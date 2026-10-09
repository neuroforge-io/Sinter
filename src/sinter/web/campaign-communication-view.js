/** Presentation only: retain canonical rows and their original array indexes. */
export const COMMUNICATION_ORDERS = Object.freeze([
  ['record', 'Record order'], ['newest', 'Newest dated first'],
  ['oldest', 'Oldest dated first'],
]);

export const COMMUNICATION_STATUSES = Object.freeze([
  ['all', 'All statuses'], ['draft', 'Draft · not sent'],
  ['sent', 'Recorded as sent'], ['received', 'Recorded as received'],
]);

const text = value => typeof value === 'string' ? value : '';

function excerpt(value, query, limit) {
  const characters = [...value];
  const at = query ? value.toLowerCase().indexOf(query) : -1;
  // Lowercasing can expand one saved character (for example İ -> i + dot).
  // Translate its search offset back to the original characters before slicing.
  let matchStart = 0, loweredOffset = 0;
  if (at >= 0) {
    while (matchStart < characters.length) {
      const width = characters[matchStart].toLowerCase().length;
      if (loweredOffset + width > at) break;
      loweredOffset += width; matchStart++;
    }
  }
  const context = Math.min(48, Math.max(0, limit - [...query].length));
  const start = at < 0 ? 0 : Math.max(0, matchStart - context);
  const end = Math.min(characters.length, start + limit);
  return (start ? '…' : '') + characters.slice(start, end).join('')
    + (end < characters.length ? '…' : '');
}

/** Literal saved wording only; current source text is never a preview input. */
export function campaignCommunicationPreview(row, {query = '', limit = 200} = {}) {
  const needle = text(query).trim().toLowerCase();
  const maximum = Number.isSafeInteger(limit) && limit > 0 ? limit : 200;
  const links = Array.isArray(row?.evidence_links) ? row.evidence_links : [];
  const material = [
    {kind: 'message', label: 'Saved message', value: text(row?.content)},
    ...links.flatMap(link => ['notes', 'title', 'url', 'checked_at'].map(key => ({
      kind: 'evidence', label: 'Saved evidence', value: text(link?.[key]),
    }))),
    ...['subject', 'counterparty', 'opportunity', 'date', 'direction', 'status', 'channel']
      .map(key => ({kind: 'metadata', label: 'Saved record', value: text(row?.[key])})),
  ];
  const match = needle
    ? material.find(item => item.value.toLowerCase().includes(needle)) : null;
  const selected = match || material.find(item => item.value.trim()) || null;
  return {kind: selected?.kind || 'empty', label: selected?.label || '',
    text: selected ? excerpt(selected.value, needle, maximum) : '',
    matchesQuery: Boolean(match), evidenceCount: links.length};
}

export function communicationHasDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)
      || Number(value.slice(0, 4)) < 1) return false;
  const stamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(stamp)
    && new Date(stamp).toISOString().slice(0, 10) === value;
}

/** Search saved wording, including evidence snapshots, never current source text. */
export function campaignCommunicationView(rows, {query = '', route = null,
  order = 'record', status = 'all'} = {}) {
  const needle = typeof query === 'string' ? query.trim().toLowerCase() : '';
  const scoped = typeof route === 'string';
  const filteredStatus = COMMUNICATION_STATUSES.some(([value]) => value === status
    && value !== 'all') ? status : null;
  const entries = (Array.isArray(rows) ? rows : []).map((row, index) => ({row, index}));
  const visible = entries.filter(({row}) => {
    if (filteredStatus && row?.status !== filteredStatus) return false;
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
