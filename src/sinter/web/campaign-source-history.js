/** Literal previous source records. These are never current evidence. */
const requirementFields = ['opportunity', 'rule', 'status', 'evidence', 'source_id',
  'source_url', 'source_quote', 'checked_at'];
const referenceFields = ['kind', 'source_id', 'title', 'url', 'excerpt', 'checked_at', 'notes'];
const workstreams = {
  contributors: ['contributors_status', 'unknown'],
  rights: ['rights_status', 'unknown'],
  disclosure: ['disclosure_status', 'unknown', 'first_public_date'],
  prior_art: ['prior_art_status', 'not_started', 'prior_art_checked_at'],
};

function previousRecord(row, fields) {
  return structuredClone(Object.fromEntries(fields.filter(key => Object.hasOwn(row, key))
    .map(key => [key, row[key]])));
}

function retainPrevious(row, next, fields, linked, assessment) {
  const entry = {state: 'historical', reason: linked ? 'replaced' : 'cleared',
    record: previousRecord(row, fields)};
  if (assessment) entry.assessment = assessment;
  next.source_history = [...structuredClone(row.source_history || []), entry];
}

export function requirementSourceReplacement(row, linked) {
  const sourceId = linked?.id || '';
  const changedSource = (row.source_id || '') !== sourceId
    || Boolean(linked && (row.source_url || '') !== (linked.url || ''));
  const resetAssessment = changedSource && ['met', 'not_met'].includes(row.status);
  const requirement = {...row};
  if (!changedSource) return {requirement, changedSource, resetAssessment};
  Object.assign(requirement, {source_id: sourceId, source_url: linked?.url || '',
    source_quote: '', checked_at: ''});
  if (resetAssessment) requirement.status = 'unknown';
  if (row.source_id || row.source_url || row.source_quote || row.checked_at || resetAssessment) {
    retainPrevious(row, requirement, requirementFields, linked);
  }
  return {requirement, changedSource, resetAssessment};
}

export function assetSourceReplacement(row, linked, asset) {
  const sourceId = linked?.id || '';
  const changedSource = (row.source_id || '') !== sourceId || Boolean(linked
    && ((row.url || '') !== (linked.url || '') || (row.title || '') !== linked.title));
  const reference = {...row}, assetChanges = {};
  if (!changedSource) return {reference, assetChanges, changedSource};
  Object.assign(reference, {source_id: sourceId, title: linked?.title || row.title || '',
    url: linked?.url || '', excerpt: '', checked_at: ''});
  const hasPrevious = Boolean(row.source_id || row.title || row.url || row.excerpt
    || row.checked_at || row.notes);
  const stream = workstreams[row.kind];
  let assessment;
  if (stream && hasPrevious) {
    const [statusField, initial, dateField] = stream;
    assessment = {status_field: statusField, status: asset[statusField] ?? initial};
    assetChanges[statusField] = initial;
    if (dateField) {
      assessment.date_field = dateField; assessment.date = asset[dateField] || '';
      assetChanges[dateField] = '';
    }
  }
  if (hasPrevious) {
    retainPrevious(row, reference, referenceFields, linked, assessment);
  }
  return {reference, assetChanges, changedSource};
}

export function sourceHistoryReferences(row, sourceId) {
  return (row.source_history || []).some(entry => entry.record?.source_id === sourceId);
}

export function sourceHistoryCount(rows) {
  return rows.reduce((count, row) => count + 1 + (row.source_history || []).length, 0);
}

/** Revoke a prepared selection when its original live editor or row is gone. */
export function captureSourceReplacementGuard(document, row, currentDocument, isActive, asset = null) {
  const originalValues = JSON.stringify(document);
  return () => isActive() && currentDocument() === document
    && (asset ? document.assets.includes(asset) && asset.references.includes(row)
      : document.requirements.includes(row))
    && JSON.stringify(document) === originalValues;
}
