/** Shared, read-only checks for user-recorded requirement evidence. */
import {campaignSourceSnapshotGuidance,
  campaignSourceSnapshotIssue} from './campaign-source-state.js';

const hasText = value => typeof value === 'string' && value.trim().length > 0;
const SOURCE_CHECK_MAX_AGE_DAYS = 90;
const sourceFields = [
  ['evidence', 'applicant-specific evidence'],
  ['source_url', 'a current official source link'],
  ['source_quote', 'a source excerpt'],
];
const parseDay = value => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed)
    && new Date(parsed).toISOString().slice(0, 10) === value ? parsed : null;
};

function sourceDateGuidance(checkedAt, today) {
  if (!hasText(checkedAt)) return 'Record the date this eligibility source was checked.';
  const checked = parseDay(checkedAt), current = parseDay(today);
  if (checked === null || current === null) {
    return 'Record a valid date for this eligibility source check.';
  }
  if (checked > current) return `The eligibility source check date (${checkedAt}) is in the future; correct it.`;
  const ageDays = Math.floor((current - checked) / 86400000);
  return ageDays > SOURCE_CHECK_MAX_AGE_DAYS
    ? `The eligibility source was last checked ${ageDays} days ago; recheck it (within ${SOURCE_CHECK_MAX_AGE_DAYS} days).`
    : '';
}

function sourceSnapshotGuidance(row, sources) {
  // A complete legacy record may have a literal URL without a registered ID.
  // Once an ID is recorded, its exact saved URL/date must match that source.
  if (!hasText(row?.source_id)) return '';
  const linked = sources.find(source => source?.id === row.source_id);
  return campaignSourceSnapshotGuidance(campaignSourceSnapshotIssue(
    row.source_url, row.checked_at, linked));
}

export function campaignRequirementSourceComplete(row, today, sources = []) {
  return sourceFields.every(([key]) => hasText(row?.[key]))
    && !sourceDateGuidance(row?.checked_at, today)
    && !sourceSnapshotGuidance(row, sources);
}

export function campaignRequirementSourceGuidance(row, today, sources = []) {
  const missing = sourceFields.filter(([key]) => !hasText(row?.[key]))
    .map(([, label]) => label);
  const fields = missing.length < 2 ? missing[0]
    : `${missing.slice(0, -1).join(', ')} and ${missing.at(-1)}`;
  // Keep complete date/snapshot sentences separate from missing-field labels.
  return [fields ? `Record ${fields}.` : '',
    sourceDateGuidance(row?.checked_at, today), sourceSnapshotGuidance(row, sources)]
    .filter(Boolean).join(' ');
}

/** A recorded not-met verdict can be complete while still blocking its route. */
export function campaignRequirementNeedsReview(row, today, sources = []) {
  return !['met', 'not_met'].includes(row?.status)
    || !campaignRequirementSourceComplete(row, today, sources);
}
