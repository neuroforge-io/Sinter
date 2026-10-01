/** Read-only projection of retained report evidence, never current project data. */
import {reportCitationIndex} from './report-citations.js';

const object = row => row && typeof row === 'object' && !Array.isArray(row);
const identity = value => typeof value === 'string' && value.trim() !== '';
function unique(rows) {
  const byId = new Map();
  for (const row of rows) {
    if (object(row) && identity(row.id)) byId.set(row.id, byId.has(row.id) ? null : row);
  }
  return byId;
}

/** Unsupported model reports do not gain a source-only interpretation. */
export function casebookQuestionEvidence(report) {
  if (report?.workflow !== 'casebook' || report.model_draft || report.incomplete
      || !Array.isArray(report.question_index)) return null;
  const register = unique(Array.isArray(report.source_register) ? report.source_register : []);
  const originals = unique(Array.isArray(report.sources) ? report.sources : []);
  const excerpts = unique(Array.isArray(report.excerpts) ? report.excerpts : []);
  const {passages} = reportCitationIndex(report);
  const labels = new Map([...passages].map(([label, row]) => [row.excerpt_id, label]));
  const originalCharacters = new Map();
  const scopes = new Map(), scopeMalformed = new Set();
  let malformedScopes = Object.hasOwn(report, 'question_scopes') && !Array.isArray(report.question_scopes);
  for (const scope of Array.isArray(report.question_scopes) ? report.question_scopes : []) {
    if (!object(scope) || !Number.isInteger(scope.question_index)
        || scope.question_index < 0 || scope.question_index >= report.question_index.length) { malformedScopes = true; continue; }
    if (scopes.has(scope.question_index)) scopeMalformed.add(scope.question_index);
    scopes.set(scope.question_index, scope);
  }
  return report.question_index.map((question, index) => {
    const exactQuestion = typeof question?.question === 'string' ? question.question : null;
    const gaps = [];
    const scope = scopes.get(index);
    let selectedIds = [...register.keys()], mode = 'all';
    if (malformedScopes || scopeMalformed.has(index) || (scope &&
        (Object.keys(scope).sort().join('|') !== 'question|question_index|source_ids'
          || scope.question !== exactQuestion || !Array.isArray(scope.source_ids)
          || scope.source_ids.some(id => !identity(id) || !register.get(id))
          || new Set(scope.source_ids).size !== scope.source_ids.length))) {
      mode = 'unavailable'; selectedIds = [];
      gaps.push('The recorded source choice is unavailable or inconsistent. Keep this historical report and check its original backup.');
    } else if (scope) { selectedIds = [...scope.source_ids]; mode = selectedIds.length ? 'selected' : 'none'; }
    if (!Array.isArray(report.source_register) || register.size !== report.source_register.length
        || [...register.values()].some(row => !row)) {
      mode = 'unavailable'; selectedIds = [];
      gaps.push('The retained source register is missing or contains ambiguous identities.');
    }
    if (object(question?.source_scope)) {
      const recorded = question.source_scope;
      const expectedMode = mode === 'all' ? 'all' : 'selected';
      if (Object.keys(recorded).sort().join('|') !== 'mode|source_ids|sources_searched'
          || recorded.mode !== expectedMode || recorded.sources_searched !== selectedIds.length
          || !Array.isArray(recorded.source_ids)
          || JSON.stringify(recorded.source_ids) !== JSON.stringify(selectedIds)) {
        mode = 'unavailable'; selectedIds = [];
        gaps.push('The recorded question search choice disagrees with the report’s retained source choices.');
      }
    } else if (Object.hasOwn(question || {}, 'source_scope')) {
      mode = 'unavailable'; selectedIds = [];
      gaps.push('The recorded question search choice is unavailable.');
    }
    const questionAvailable = exactQuestion !== null && !/^[\s\u001c-\u001f\u0085]*$/u.test(exactQuestion);
    if (!questionAvailable) gaps.push('The exact question wording is unavailable. No current project wording was substituted.');
    const ids = Array.isArray(question?.excerpt_ids) ? question.excerpt_ids : null;
    if (!ids) gaps.push('The recorded passage list is unavailable.');
    const seen = new Set();
    const selected = new Set(selectedIds);
    const matches = (ids || []).map(id => {
      const excerpt = identity(id) ? excerpts.get(id) : null;
      const source = excerpt ? originals.get(excerpt.source_id) : null;
      const recordedSource = excerpt ? register.get(excerpt.source_id) : null;
      let unavailable = !identity(id) || seen.has(id) || !excerpt || !source || !recordedSource
        || mode === 'unavailable' || !selected.has(excerpt.source_id)
        || !Number.isSafeInteger(excerpt.start) || !Number.isSafeInteger(excerpt.end)
        || excerpt.start < 0 || excerpt.end <= excerpt.start
        || typeof excerpt.quote !== 'string' || typeof source.content !== 'string';
      seen.add(id);
      if (!unavailable) {
        if (!originalCharacters.has(source)) originalCharacters.set(source, Array.from(source.content));
        const original = originalCharacters.get(source);
        unavailable = excerpt.end > original.length
          || original.slice(excerpt.start, excerpt.end).join('') !== excerpt.quote;
      }
      return {excerptId: identity(id) ? id : null, sourceId: excerpt?.source_id || null,
        label: labels.get(id) || 'Recorded excerpt',
        sourceTitle: typeof recordedSource?.title === 'string' ? recordedSource.title : null,
        available: !unavailable, quote: unavailable ? null : excerpt.quote,
        start: unavailable ? null : excerpt.start, end: unavailable ? null : excerpt.end};
    });
    const scopeLabel = mode === 'all' ? 'All supplied sources'
      : mode === 'none' ? 'No sources selected'
        : mode === 'selected' ? `${selectedIds.length} selected source${selectedIds.length === 1 ? '' : 's'}`
          : 'Recorded source choice unavailable';
    const status = gaps.length || matches.some(row => !row.available) ? 'Review required'
      : mode === 'none' ? 'No sources selected'
        : matches.length ? 'Review required' : 'No wording match';
    return {position: index + 1, question: exactQuestion, questionAvailable, scopeLabel, sourceIds: selectedIds,
      status, matches, gaps};
  });
}
