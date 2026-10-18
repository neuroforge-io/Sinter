import {h, field, button, notice} from './ui.js';
import {request} from './api.js';
import {documentMarkdown} from './documents.js';
import {decodeReportBackup, checkReportBackupSize} from './report-backup.js';
import {confirmAction} from './confirm-action.js';
import {registerReportDraft, observeReportSaveState, markReportSaving, markReportSaved,
  markReportSaveFailed, reportSaveState, reportSavedCopyId, reportHasUnappliedInputs, reportHasUnconfirmedSave,
  reportReplacementState, reportReplacementUnchanged} from './report-drafts.js';

/** Stage locally; only an explicit action saves a new copy. Never replace an editor. */
export function savedReportRestore({setBusy = () => {}, onChanged = () => {}, onSaved,
  onCheckSaved} = {}) {
  const feedback = h('div', {'aria-live': 'polite'}), preview = h('div');
  const source = field('Choose draft JSON', 'file', '',
    'Use the draft JSON downloaded from a report’s More options menu. Project backups have separate restore controls.',
    {accept: '.json,application/json'});
  const root = h('details', {class: 'card stack non-print'},
    h('summary', {}, 'Restore draft JSON'),
    h('p', {}, 'Inspect a complete exported draft, then save it as a new local copy. Existing work and connection settings stay intact.'),
    source.wrap, preview, feedback);
  let selected = null, generation = 0, disposed = false;
  let reading = false, writing = false, checking = false, deciding = false;
  let unsubscribe = null, decision = null;
  const active = () => !disposed && root.isConnected;
  const tell = (text, kind = '') => { if (active()) feedback.replaceChildren(notice(text, kind)); };
  const unchanged = (entry, token) => selected === entry && active()
    && reportReplacementUnchanged(entry.report, token);
  const stateOf = entry => entry?.registered ? reportSaveState(entry.report) : {kind: 'prepared'};
  const acknowledged = entry => entry?.registered && reportSavedCopyId(entry.report);
  const uncertain = entry => entry?.registered && reportHasUnconfirmedSave(entry.report) && !acknowledged(entry);
  const unapplied = entry => entry?.registered && reportHasUnappliedInputs(entry.report);

  function controls() {
    const state = stateOf(selected), blocked = reading || writing || checking || deciding;
    source.input.disabled = writing || checking || deciding;
    restore.disabled = !selected || blocked || Boolean(acknowledged(selected)) || unapplied(selected)
      || state.kind === 'saving' || (uncertain(selected)
        && !reportReplacementUnchanged(selected.report, selected.checkedToken));
    restore.textContent = acknowledged(selected) ? 'Restored to My workspace'
      : uncertain(selected) ? 'Restore an additional copy' : 'Restore as a new saved copy';
    check.hidden = !uncertain(selected);
    check.disabled = blocked || state.kind === 'saving';
    status.textContent = !selected ? '' : acknowledged(selected)
      ? 'Restored copy acknowledged. Reference ' + reportSavedCopyId(selected.report) + '. Later edits use the open draft’s Save control.'
        + (reportHasUnconfirmedSave(selected.report) ? ' An earlier attempt remains unconfirmed and may have created another copy.' : '')
      : selected.registered ? state.message + (uncertain(selected) && state.kind !== 'unconfirmed'
        ? ' An earlier save remains unconfirmed and may already have created a copy.' : '') + (unapplied(selected)
        ? ' Open it in Pending work to apply or cancel all editor and form inputs before restoring.' : '')
        : 'Preview only. No saved copy has been created.';
  }

  source.input.addEventListener('change', async () => {
    const attempt = ++generation;
    const previous = selected;
    unsubscribe?.(); unsubscribe = null;
    selected = null; reading = false; preview.replaceChildren(); feedback.replaceChildren(); controls();
    if (previous?.registered && !acknowledged(previous)) tell('The earlier draft remains in Pending work in this session. Open it there to recover its wording or check its save state.');
    const file = source.input.files?.[0];
    if (!file) return;
    try {
      checkReportBackupSize(file.size);
      reading = true; controls();
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (attempt !== generation || !active()) return;
      const report = decodeReportBackup(bytes);
      selected = {report, filename: file.name, registered: false, checkedToken: null};
      const wording = documentMarkdown(report), snippet = [...wording].slice(0, 2400).join('');
      const text = field('Restored wording preview', 'textarea', snippet,
        snippet.length < wording.length ? 'Preview excerpt only. Saving retains the complete report and evidence in the selected file.'
          : 'Saving retains the complete report and evidence in the selected file.',
        {readOnly: true, rows: 8, spellcheck: false});
      preview.replaceChildren(h('h3', {}, report.title),
        h('p', {class: 'muted'}, file.name + ' · ' + file.size.toLocaleString() + ' bytes'),
        notice('Historical evidence and recorded review or partial-completion status are retained. Restoring does not verify facts or make an old review current.'),
        ...(typeof report.export_privacy?.notice === 'string' ? [notice(report.export_privacy.notice, 'warning')] : []),
        text.wrap);
    } catch (error) {
      if (attempt === generation && active()) tell(error.message, 'error');
    } finally {
      if (attempt === generation && !disposed) { reading = false; controls(); }
    }
  });

  const restore = button('Restore as a new saved copy', async () => {
    const entry = selected;
    if (!entry || reading || writing || checking || deciding || !active()
        || acknowledged(entry) || unapplied(entry) || stateOf(entry).kind === 'saving') return;
    if (uncertain(entry)) {
      if (!reportReplacementUnchanged(entry.report, entry.checkedToken)) return;
      const token = reportReplacementState(entry.report);
      deciding = true; decision = new AbortController(); controls();
      let approved;
      try {
        approved = await confirmAction({signal: decision.signal, title: 'Restore another copy?',
          confirmLabel: 'Restore additional copy',
          description: 'The earlier request may already have saved this draft. Check the saved list first. Continuing creates another copy; it cannot resolve or replace the earlier one.'});
      } catch (error) { tell(error.message, 'error'); }
      finally { deciding = false; decision = null; if (active()) controls(); }
      if (!approved || !unchanged(entry, token) || reading || writing || checking
          || acknowledged(entry) || unapplied(entry)) return;
    }
    let snapshot, wording;
    try { snapshot = structuredClone(entry.report); wording = documentMarkdown(snapshot); }
    catch (error) { tell('Could not prepare this copy. Your local work is unchanged. ' + error.message, 'error'); return; }
    if (!entry.registered) {
      registerReportDraft(entry.report, wording);
      entry.registered = true;
      unsubscribe = observeReportSaveState(entry.report, () => {
        controls(); onChanged();
      }, () => active() && selected === entry);
    }
    writing = true; entry.checkedToken = null;
    try {
      setBusy(true); markReportSaving(entry.report); controls(); onChanged();
      let result;
      try {
        result = await request('/api/reports', {data: {report: snapshot}, acceptResponse: value => {
          if (!value || typeof value !== 'object' || Array.isArray(value)
              || typeof value.id !== 'string' || !/^[a-f0-9]{32}$/.test(value.id)) {
            throw new Error('The app did not return a complete saved-copy reference.');
          }
          return value;
        }});
      } catch (error) {
        markReportSaveFailed(entry.report, error);
        tell(reportSaveState(entry.report).message + ' ' + error.message, 'warning');
        return;
      }
      // An acknowledged write is recorded before refreshing any fallible view.
      markReportSaved(entry.report, wording, snapshot, result.id);
      tell('Restored as a new saved copy. Reference ' + result.id + '. Open it from the saved list when ready.', 'success');
      try { await onSaved?.(); }
      catch (error) { tell('Restored copy acknowledged. Reference ' + result.id
        + '. Refreshing the list failed; use Refresh saved list. Do not restore again to refresh it. ' + error.message, 'warning'); }
    } catch (error) {
      // A local callback failure before dispatch must not leave the draft "saving".
      if (!acknowledged(entry) && stateOf(entry).kind === 'saving') {
        markReportSaveFailed(entry.report, {requestState: {outcome: 'not-sent'}});
      }
      tell(acknowledged(entry)
        ? 'Restored copy acknowledged. Reference ' + reportSavedCopyId(entry.report)
          + '. The view could not refresh. Use Refresh saved list; do not restore again to refresh it. ' + error.message
        : 'Your draft is kept in Pending work in this session. ' + error.message, 'warning');
    } finally {
      writing = false;
      for (const release of [() => setBusy(false), () => { if (active()) controls(); },
        () => { if (active()) onChanged(); }]) {
        try { release(); }
        catch { /* Independent view failures cannot skip other cleanup or undo persistence. */ }
      }
    }
  }, 'primary');

  const check = button('Check saved list before retrying', async () => {
    const entry = selected;
    if (!entry?.registered || writing || checking || deciding || !uncertain(entry)
        || acknowledged(entry) || !active()) return;
    const token = reportReplacementState(entry.report);
    checking = true; controls();
    try {
      if (typeof onCheckSaved !== 'function') throw new Error('Reopen My workspace to check saved copies.');
      const refreshed = await onCheckSaved();
      if (refreshed === false || !unchanged(entry, token) || acknowledged(entry)) return;
      entry.checkedToken = token;
      tell('Saved list refreshed. Inspect its copies before deciding whether to restore an additional copy. Nothing was replayed.', 'warning');
    } catch (error) { tell('Could not check saved copies. Nothing was replayed. ' + error.message, 'error'); }
    finally { checking = false; if (active()) controls(); }
  }, 'quiet');
  const status = h('p', {role: 'status', 'aria-label': 'Draft restore state'});
  root.append(status, h('div', {class: 'button-row'}, restore, check)); controls();
  return {element: root, dispose() {
    disposed = true; generation++; decision?.abort(); unsubscribe?.();
    // A dispatched save owns its completion, even after this view is detached.
  }};
}
