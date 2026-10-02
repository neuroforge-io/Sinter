/** Unsaved document edits survive page changes within this browser session.
 * Nothing here writes to disk or changes the report's original evidence.
 */
let identities = new WeakMap();
const drafts = new Map();
let sequence = 0;

export function registerReportDraft(report, content) {
  if (!identities.has(report)) identities.set(report, {
    id: `report-draft-${++sequence}`, report, baseline: content, content, editor: null, forms: new Map(),
  });
  return identities.get(report);
}

function update(state) {
  if (state.content !== state.baseline || state.editor || state.forms.size) drafts.set(state.id, state);
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

export function markReportSaved(report, content) {
  const state = identities.get(report);
  if (!state) return;
  // A user may keep editing while the save request is pending. Only the exact
  // content sent has reached disk; later edits and editor text remain unsaved.
  state.baseline = content; update(state);
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
  const messages = [];
  if (state.content !== state.baseline) messages.push('Applied document edits have not been saved.');
  if (state.editor) messages.push('Draft text is waiting to be applied.');
  if (state.forms.has('handover-summary')) messages.push('Summary rows have not been applied; they are kept in this session only.');
  if ([...state.forms.keys()].some(name => name !== 'handover-summary')) messages.push('Other local form inputs have not been applied; they are kept in this session only.');
  return messages.join(' ');
}
export function clearReportDrafts() { drafts.clear(); identities = new WeakMap(); }
