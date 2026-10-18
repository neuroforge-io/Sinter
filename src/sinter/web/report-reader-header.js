/** Saved-report reading controls. Storage authority stays in report-drafts. */
import {h} from './ui.js';
import {reportSaveState, reportSavedCopyId, reportHasUnappliedInputs,
  reportHasUnconfirmedSave, reportSavingHasNewerEdits,
  reportReplacementState, reportReplacementUnchanged} from './report-drafts.js';

export function readerSavePresentation(report, {deciding = false} = {}) {
  const state = reportSaveState(report), id = reportSavedCopyId(report);
  const unapplied = reportHasUnappliedInputs(report);
  const uncertain = reportHasUnconfirmedSave(report);
  const newer = state.kind === 'saving' && reportSavingHasNewerEdits(report);
  const summaries = {
    saved: 'Saved locally.',
    prepared: 'Prepared locally; not yet saved.',
    pending: unapplied ? 'Apply or cancel the pending inputs before saving.' : 'Unsaved changes.',
    saving: newer ? 'Saving an earlier version. Newer edits are unsaved.' : 'Saving a new copy...',
    'not-sent': 'The latest save was not sent.',
    rejected: 'The latest save was rejected.',
    unconfirmed: 'Save outcome unknown. Check saved copies before another save.',
    unknown: 'Save state unavailable.',
  };
  return Object.freeze({
    kind: state.kind, id, message: state.message, summary: summaries[state.kind] || state.message,
    identityLabel: state.kind === 'saved' ? 'Saved copy' : 'Last acknowledged copy',
    warning: uncertain && state.kind !== 'unconfirmed'
      ? 'An earlier save remains unconfirmed. An additional copy may exist.' : '',
    saveLabel: state.kind === 'saving' ? 'Saving new copy...'
      : state.kind === 'unconfirmed' ? 'Save an additional copy' : id ? 'Save new copy' : 'Save draft',
    saveHidden: state.kind === 'saved',
    saveDisabled: deciding || unapplied || ['saved', 'saving', 'unknown'].includes(state.kind),
    duplicateHidden: state.kind !== 'saved',
    duplicateDisabled: deciding || unapplied || state.kind !== 'saved',
  });
}

/** A confirmation grants only this exact, still-active local draft. No writes. */
export async function authorizeAdditionalReportCopy(report, {confirm, isActive = () => true} = {}) {
  if (!isActive()) return {allowed: false, reason: 'inactive'};
  if (reportHasUnappliedInputs(report)) return {allowed: false, reason: 'unapplied'};
  const before = reportReplacementState(report);
  if (before.saving) return {allowed: false, reason: 'saving'};
  if (!await confirm()) return {allowed: false, reason: 'cancelled'};
  if (!isActive()) return {allowed: false, reason: 'inactive'};
  if (reportHasUnappliedInputs(report) || !reportReplacementUnchanged(report, before)) {
    return {allowed: false, reason: 'changed'};
  }
  return {allowed: true};
}

/** Compose the original controls; never clone save handlers or evidence. */
export function reportReaderHeader({title, back, saveState, controls}) {
  const identity = h('p', {class: 'reader-copy-identity', id: title.id + '-identity'});
  const warning = h('p', {class: 'reader-save-warning', role: 'note', hidden: true, id: title.id + '-warning'});
  const fullReference = h('p', {class: 'reader-copy-reference fine'});
  const detailState = h('p', {class: 'fine'});
  const element = h('header', {class: 'report-heading report-reader-heading non-print',
    tabIndex: -1, role: 'group', 'aria-labelledby': title.id},
    h('div', {class: 'reader-topline'}, back, identity), title, saveState, warning, controls);
  return {
    element, detailState, fullReference,
    focus() {
      element.focus({preventScroll: true});
      element.scrollIntoView({block: 'start', behavior: 'instant'});
    },
    update(presentation, reference) {
      identity.textContent = presentation.id
        ? presentation.identityLabel + ' ' + reference : 'Local draft';
      fullReference.textContent = presentation.id
        ? presentation.identityLabel + ': ' + presentation.id : 'No acknowledged saved-copy reference.';
      detailState.textContent = presentation.message;
      saveState.textContent = presentation.summary;
      warning.textContent = presentation.warning;
      warning.hidden = !presentation.warning;
      const description = [identity.id, saveState.id,
        ...(presentation.warning ? [warning.id] : [])].filter(Boolean).join(' ');
      title.setAttribute('aria-describedby', description);
      element.setAttribute('aria-describedby', description);
    },
  };
}
