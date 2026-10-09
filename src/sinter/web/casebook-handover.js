/** Export scope for a source-only handover, separate from evidence selection. */
export const HANDOVER_EVIDENCE_OPTIONS = Object.freeze([
  Object.freeze(['compact', 'Compact notes']),
  Object.freeze(['selected_appendix', 'All selected passages']),
]);

export function handoverEvidenceMode(book = {}) {
  const mode = book.handover_evidence === undefined ? 'compact' : book.handover_evidence;
  if (!HANDOVER_EVIDENCE_OPTIONS.some(([value]) => value === mode)) {
    throw new Error('Choose compact handover notes or a selected evidence appendix.');
  }
  return mode;
}

export function handoverExportNotice(report) {
  if (report?.document_type !== 'handover' || report?.model_draft) return '';
  const count = Array.isArray(report.excerpts) ? report.excerpts.length : 0;
  const scope = handoverEvidenceMode(report) === 'selected_appendix'
    ? `This prepared handover includes all ${count} selected passages.`
      + (count > 4 ? ' Passages after the first four are in its appendix.' : '')
    : `This prepared handover includes ${Math.min(4, count)} of ${count} selected passages. Additional passages stay in Evidence; choose All selected passages to include them in the document.`;
  return scope + ' This is selected wording, not answered questions or a whole-source review. Word exports the current document text; your edits can change what it includes.';
}
