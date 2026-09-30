/** Change a requirement's source without discarding its explanatory note. */
export function selectRequirementSource(row, linked) {
  const sourceId = linked?.id || '';
  const changedSource = (row.source_id || '') !== sourceId;
  const resetAssessment = changedSource && ['met', 'not_met'].includes(row.status);
  const requirement = {...row, source_id: sourceId};
  if (changedSource) {
    requirement.source_quote = '';
    requirement.checked_at = '';
    if (resetAssessment) requirement.status = 'unknown';
  }
  if (linked) {
    requirement.source_url = linked.url;
    // Retain the existing picker behavior: this remains user-entered metadata,
    // not a claim that the operator has checked this excerpt.
    if (!requirement.checked_at && linked.checked_at) {
      requirement.checked_at = linked.checked_at;
    }
  } else if (changedSource) {
    requirement.source_url = '';
  }
  return {requirement, changedSource, resetAssessment};
}
