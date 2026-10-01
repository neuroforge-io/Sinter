/** Keep a window quote bound to the source the operator actually selected. */
export function selectWindowSource(row, source) {
  const sourceId = source?.id || '';
  const sourceUrl = source?.url || '';
  const changedSource = (row.window_source_id || '') !== sourceId
    || (row.window_source_url || '') !== sourceUrl;
  const opportunity = {...row};
  if (changedSource) {
    opportunity.window_source_id = sourceId;
    opportunity.window_source_url = sourceUrl;
    opportunity.window_source_quote = '';
    opportunity.window_checked_at = '';
  }
  return {opportunity, changedSource};
}
