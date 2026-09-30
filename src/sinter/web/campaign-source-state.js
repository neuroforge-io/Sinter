/** Classify saved evidence snapshots without guessing why they differ. */
export function campaignSourceSnapshotIssue(savedUrl, savedDate, source) {
  if (!source) return 'source_missing';
  const url = String(savedUrl || '').trim();
  const currentUrl = String(source.url || '').trim();
  if (!url) return currentUrl ? 'url_snapshot_missing' : 'source_url_missing';
  if (!currentUrl) return 'source_url_missing';
  if (url !== currentUrl) return 'url_mismatch';
  const checkedAt = String(savedDate || '').trim();
  const sourceCheckedAt = String(source.checked_at || '').trim();
  if (!sourceCheckedAt) return 'source_date_missing';
  if (!checkedAt) return 'date_snapshot_missing';
  if (checkedAt !== sourceCheckedAt) return 'date_mismatch';
  return '';
}

export function campaignSourceSnapshotGuidance(issue) {
  return ({
    source_missing: 'The linked campaign source is missing; reconnect it and recheck the wording.',
    url_snapshot_missing: 'No source URL snapshot was saved with this wording; compare it with the linked page and recheck before use.',
    source_url_missing: 'The linked campaign source has no URL; add the official page and recheck the wording.',
    url_mismatch: 'The saved source URL differs from the linked record; re-read the page and update the wording and check date before use.',
    source_date_missing: 'The linked source has no check date; re-read the page and record when it was checked.',
    date_snapshot_missing: 'No source check date was saved with this wording; re-read it and record a date before use.',
    date_mismatch: 'The saved check date differs from the linked record; re-read the wording and update the date before use.',
  })[issue] || '';
}
