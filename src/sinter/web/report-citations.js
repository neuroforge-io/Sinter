function uniqueRows(rows) {
  const result = new Map();
  for (const row of rows) {
    if (typeof row?.id === 'string' && row.id) result.set(row.id, result.has(row.id) ? null : row);
  }
  return result;
}

/** Register presentation aliases only against the exact retained passage. */
function passageReferences(report, sources, excerpts) {
  const rows = report.document_references;
  const passages = new Map(), characters = new Map();
  if (!Array.isArray(rows) || rows.length > excerpts.length) return passages;
  const uniqueExcerpts = uniqueRows(excerpts);
  for (const [index, row] of rows.entries()) {
    if (typeof row?.excerpt_id !== 'string' || !row.excerpt_id.trim()
      || typeof row?.source_id !== 'string' || !row.source_id.trim()) continue;
    const excerpt = uniqueExcerpts.get(row?.excerpt_id);
    const source = sources.get(row?.source_id);
    if (row?.label !== `Passage ${index + 1}` || !excerpt || !source
      || excerpt !== excerpts[index] || row.source_id !== excerpt.source_id
      || !Number.isSafeInteger(row.start) || !Number.isSafeInteger(row.end)
      || row.start < 0 || row.start >= row.end
      || row.start !== excerpt.start || row.end !== excerpt.end
      || typeof source.content !== 'string' || typeof excerpt.quote !== 'string') continue;
    // Python excerpt offsets count Unicode code points, not JS UTF-16 units.
    if (!characters.has(source.id)) characters.set(source.id, Array.from(source.content));
    const original = characters.get(source.id);
    if (row.end > original.length || original.slice(row.start, row.end).join('') !== excerpt.quote) continue;
    passages.set(row.label, row);
  }
  return passages;
}

/** Resolve only identities present in this report's original source register. */
export function reportCitationIndex(report, {includePassages = true} = {}) {
  const sourceRows = Array.isArray(report.sources) ? report.sources : [];
  const sources = uniqueRows(sourceRows);
  const references = new Map([...sources.keys()].map(id => [id, id]));
  const add = (id, source) => {
    if (typeof id === 'string' && id && sources.has(source)) references.set(id, source);
  };
  const excerpts = Array.isArray(report.excerpts) ? report.excerpts : [];
  for (const row of excerpts) add(row?.id, row?.source_id);
  for (const question of Array.isArray(report.question_index) ? report.question_index : []) {
    for (const row of Array.isArray(question?.matches) ? question.matches : []) add(row?.excerpt_id, row?.source_id);
  }
  const passages = includePassages ? passageReferences(report, sources, excerpts) : new Map();
  for (const [label, row] of passages) {
    if (references.has(label)) passages.delete(label);
    else references.set(label, row.source_id);
  }
  return {references, passages};
}

export function reportCitationReferences(report) {
  return reportCitationIndex(report).references;
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
