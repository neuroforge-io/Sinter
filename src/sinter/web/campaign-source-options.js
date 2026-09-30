/** Local source choices preserve canonical objects; searching never links one. */
export const MAX_CAMPAIGN_SOURCE_MATCHES = 8;

const searchable = value => String(value || '').normalize('NFKC').toLocaleLowerCase();

export function campaignSourceOptions(sources) {
  const rows = Array.isArray(sources) ? sources : [];
  const ids = new Map();
  for (const row of rows) {
    if (typeof row?.id === 'string' && row.id.trim()) {
      ids.set(row.id, (ids.get(row.id) || 0) + 1);
    }
  }
  const options = rows.filter(source => typeof source?.id === 'string'
    && source.id.trim() && ids.get(source.id) === 1
    && typeof source.title === 'string' && source.title.trim()).map(source => {
    let host = '';
    try { host = new URL(source.url).hostname.replace(/^www\./, ''); } catch {}
    return {source, base: `${source.title}${host ? ` · ${host}` : ''}`};
  });
  const groups = new Map();
  for (const option of options) {
    const key = searchable(option.base);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(option);
  }
  return options.map(option => {
    const peers = groups.get(searchable(option.base));
    let prefix = 6;
    while (peers.some(peer => peer !== option
        && peer.source.id.slice(0, prefix) === option.source.id.slice(0, prefix))
        && prefix < option.source.id.length) prefix++;
    const label = option.base + (peers.length > 1
      ? ` · Source ${option.source.id.slice(0, prefix)}` : '');
    return {...option, label,
      search: searchable(`${label} ${option.source.url || ''} ${option.source.id}`)};
  });
}

export function matchingCampaignSources(options, query = '') {
  const needle = searchable(query).trim();
  const matches = options.filter(option => option.search.includes(needle));
  return {total: matches.length, matches: matches.slice(0, MAX_CAMPAIGN_SOURCE_MATCHES)};
}
