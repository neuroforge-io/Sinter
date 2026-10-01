/** Local display filters only; never infer relevance or alter stored choices. */
export function sourceFilterMatches(source, query) {
  const terms = query.normalize('NFC').trim().toLowerCase().split(/\s+/u).filter(Boolean);
  const metadata = ['title', 'date', 'url', 'id']
    .map(key => typeof source[key] === 'string' ? source[key] : '').join('\n').normalize('NFC').toLowerCase();
  return terms.every(term => metadata.includes(term));
}

/** Ephemeral display state is anchored to literal current question positions. */
export function sourceFilterStates(questions, states) {
  const valid = [], seen = new Set();
  if (!Array.isArray(states)) return valid;
  for (const state of states) {
    if (!state || Object.keys(state).sort().join('|') !== 'query|question|question_index|selected_only'
        || !Number.isInteger(state.question_index) || state.question_index < 0
        || state.question_index >= questions.length || seen.has(state.question_index)
        || state.question !== questions[state.question_index] || typeof state.query !== 'string'
        || typeof state.selected_only !== 'boolean') continue;
    seen.add(state.question_index); valid.push({...state});
  }
  return valid.sort((a, b) => a.question_index - b.question_index);
}

export function sourceFilterView(documents, sourceIds, {query = '', selectedOnly = false} = {}) {
  const selected = new Set(sourceIds);
  const visibleIndices = documents.flatMap((source, index) =>
    sourceFilterMatches(source, query) && (!selectedOnly || selected.has(source.id)) ? [index] : []);
  const selectedVisible = new Set(visibleIndices.map(index => documents[index].id)
    .filter(id => selected.has(id))).size;
  return {visibleIndices, totalSources: documents.length, selectedTotal: sourceIds.length,
    selectedOutsideView: sourceIds.length - selectedVisible};
}
