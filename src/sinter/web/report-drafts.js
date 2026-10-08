/** Unsaved document edits survive page changes within this browser session.
 * Nothing here writes to disk or changes the report's original evidence.
 */
let identities = new WeakMap();
const drafts = new Map();
let sequence = 0;

export function registerReportDraft(report, content, {saved = false} = {}) {
  if (!identities.has(report)) identities.set(report, {
    id: `report-draft-${++sequence}`, report, baseline: content, content, editor: null, forms: new Map(),
    saved: saved === true, saving: false, saveFailure: null,
    baselinePayload: JSON.stringify(report), payload: JSON.stringify(report),
    views: new Set(),
  });
  const state = identities.get(report); update(state); return state;
}

/** Session views observe one shared save; a broken/detached view cannot undo it. */
export function observeReportSaveState(report, view, isActive = () => true) {
  const state = identities.get(report);
  if (!state) throw new Error('Register the report before observing its save state.');
  for (const old of state.views) if (!old.isActive()) state.views.delete(old);
  const observer = {refresh: view, isActive};
  state.views.add(observer);
  return () => state.views.delete(observer);
}

function notifyViews(state) {
  const failures = [];
  for (const view of state.views) {
    try { if (!view.isActive() || view.refresh() === false) state.views.delete(view); }
    catch (error) { failures.push(error); }
  }
  return failures;
}

function update(state) {
  state.payload = JSON.stringify(state.report);
  if (!state.saved || state.content !== state.baseline || state.editor || state.forms.size
      || state.payload !== state.baselinePayload || state.saveFailure === 'unconfirmed') drafts.set(state.id, state);
  else drafts.delete(state.id);
}

export function trackReportEdits(report, content) {
  const state = identities.get(report);
  if (!state) throw new Error('Register the original report before editing it.');
  state.content = content; state.editor = null; update(state);
}

export function trackReportEditor(report, text, open = true) {
  const state = identities.get(report);
  if (!state) throw new Error('Register the original report before editing it.');
  state.editor = open && text !== state.content ? {text, open: true} : null;
  update(state);
}

/** Named local forms participate in the same navigation/quit guard, not disk schema. */
export function trackReportForm(report, name, value) {
  const state = identities.get(report);
  if (!state) throw new Error('Register the original report before editing it.');
  if (typeof name !== 'string' || !name) throw new Error('Name this local report form.');
  state.forms.set(name, structuredClone(value)); update(state);
}

export function reportFormDraft(report, name) {
  const value = identities.get(report)?.forms.get(name);
  return value === undefined ? undefined : structuredClone(value);
}

export function clearReportForm(report, name) {
  const state = identities.get(report);
  if (state) { state.forms.delete(name); update(state); }
}

export function reportEditorDraft(report) {
  return identities.get(report)?.editor || null;
}

export function markReportSaved(report, content, submittedReport = report) {
  const state = identities.get(report);
  if (!state) return;
  // A user may keep editing while the save request is pending. Only the exact
  // content sent has reached disk; later edits and editor text remain unsaved.
  state.baseline = content; state.saved = true; state.saving = false;
  state.baselinePayload = JSON.stringify(submittedReport);
  state.saveFailure = null; update(state); return notifyViews(state);
}

/** These are local observations, never inferred from a title, ID or edit baseline. */
export function markReportSaving(report) {
  const state = identities.get(report);
  if (state) { state.saving = true; state.saveFailure = null; update(state); notifyViews(state); }
}

export function markReportSaveFailed(report, error) {
  const state = identities.get(report);
  if (!state) return;
  const outcome = error?.requestState?.outcome;
  state.saving = false;
  state.saveFailure = ['not-sent', 'rejected'].includes(outcome) ? outcome : 'unconfirmed';
  update(state); notifyViews(state);
}

export function reportSaveState(report) {
  const state = identities.get(report);
  if (!state) return {kind: 'unknown', message: 'Save state unavailable.'};
  update(state);
  if (state.saving) return {kind: 'saving', message: 'Saving to My workspace…'};
  const failures = {
    'not-sent': 'Save was not sent. Your local work is kept; restore the app connection before explicitly trying again.',
    rejected: 'The app rejected this save. Your local work is kept; resolve the reported issue before explicitly trying again.',
    unconfirmed: 'Save not confirmed. Your local draft is kept; check My workspace before explicitly trying again.',
  };
  if (state.saveFailure) return {kind: state.saveFailure,
    message: failures[state.saveFailure] + ' ' + reportDraftNotice(report)};
  const pending = reportDraftNotice(report);
  if (state.content !== state.baseline || state.payload !== state.baselinePayload
      || state.editor || state.forms.size) return {kind: 'pending', message: pending};
  return state.saved
    ? {kind: 'saved', message: 'Saved locally in My workspace.'}
    : {kind: 'prepared', message: 'Prepared locally; not saved to My workspace.'};
}

export function unsavedReportDrafts() { return [...drafts.values()]; }
export function hasUnsavedReportDrafts() { return drafts.size > 0; }
export function isReportDraftUnsaved(report) {
  const state = identities.get(report);
  return Boolean(state && drafts.has(state.id));
}
export function reportDraftNotice(report) {
  const state = identities.get(report);
  if (!state) return '';
  update(state);
  const messages = [];
  if (!state.saved) messages.push('Prepared document has not been saved; it is kept in this session only.');
  if (state.content !== state.baseline) messages.push('Applied document edits have not been saved.');
  else if (state.payload !== state.baselinePayload) messages.push('Changes to this document’s retained records have not been saved.');
  if (state.editor) messages.push('Draft text is waiting to be applied.');
  if (state.forms.has('handover-summary')) messages.push('Summary rows have not been applied; they are kept in this session only.');
  if ([...state.forms.keys()].some(name => name !== 'handover-summary')) messages.push('Other local form inputs have not been applied; they are kept in this session only.');
  return messages.join(' ');
}
export function clearReportDrafts() { drafts.clear(); identities = new WeakMap(); }
