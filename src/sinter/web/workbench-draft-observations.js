import {observeReportSaveState, reportSaveState, reportEditorDraft} from './report-drafts.js';

const unavailable = Object.freeze({
  save: Object.freeze({kind: 'unknown', message: 'Save state unavailable.'}), pendingText: false,
});

/** Cache observed presentation, never permission to replace, save or send a report. */
export function createWorkbenchDraftObservations({
  onChange, isActive, readSaveState = reportSaveState,
  readEditorDraft = reportEditorDraft, observe = observeReportSaveState,
}) {
  const entries = new Map();
  let disposed = false;
  const active = () => !disposed && isActive();
  function read(entry) {
    try {
      const save = readSaveState(entry.report);
      const pendingText = Boolean(readEditorDraft(entry.report));
      if (!save || typeof save.kind !== 'string' || typeof save.message !== 'string') return unavailable;
      return Object.freeze({save: Object.freeze({kind: save.kind, message: save.message}), pendingText});
    } catch { return unavailable; }
  }
  function refresh(number) {
    const entry = entries.get(number);
    if (!active() || !entry) return unavailable;
    entry.snapshot = entry.unsubscribe ? read(entry) : unavailable;
    return entry.snapshot;
  }
  return {
    add({number, report}) {
      if (!active()) return false;
      if (!Number.isSafeInteger(number) || number < 1 || !report || typeof report !== 'object') {
        throw new Error('Register this draft with its own number and report.');
      }
      const previous = entries.get(number);
      if (previous) {
        if (previous.report !== report) throw new Error('This draft number belongs to another report.');
        return true;
      }
      const entry = {report, snapshot: unavailable, unsubscribe: null};
      entries.set(number, entry);
      try {
        entry.unsubscribe = observe(report, () => {
          if (!active()) return false;
          refresh(number); onChange();
        }, active);
        entry.snapshot = read(entry);
      } catch { entry.snapshot = unavailable; }
      return true;
    },
    refresh,
    get(number) { return entries.get(number)?.snapshot ?? unavailable; },
    dispose() {
      disposed = true;
      const failures = [];
      for (const entry of entries.values()) {
        try { entry.unsubscribe?.(); } catch (error) { failures.push(error); }
      }
      entries.clear();
      return failures;
    },
  };
}
