/** Resolve only identities present in this report's original source register. */
export function reportCitationReferences(report) {
  const sources = new Map((Array.isArray(report.sources) ? report.sources : [])
    .filter(row => typeof row?.id === 'string' && row.id.length > 0)
    .map(row => [row.id, row.id]));
  const references = new Map(sources);
  const add = (id, source) => {
    if (typeof id === 'string' && id && sources.has(source)) references.set(id, source);
  };
  for (const row of Array.isArray(report.excerpts) ? report.excerpts : []) add(row?.id, row?.source_id);
  for (const question of Array.isArray(report.question_index) ? report.question_index : []) {
    for (const row of Array.isArray(question?.matches) ? question.matches : []) add(row?.excerpt_id, row?.source_id);
  }
  return references;
}

/** Match complete registered IDs, without guessing a hash length or model format. */
export function reportCitationMatcher(references) {
  if (!references.size) return () => [];
  const alternatives = [...references.keys()].sort((a, b) => b.length - a.length)
    .map(id => id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const pattern = new RegExp(`(^|[^\\p{L}\\p{N}_-])(${alternatives})(?![\\p{L}\\p{N}_-])`, 'gu');
  return text => [...text.matchAll(pattern)].map(match => ({
    id: match[2], index: match.index + match[1].length, sourceId: references.get(match[2]),
  }));
}

export function reportCitationMatches(text, references) {
  return reportCitationMatcher(references)(text);
}
