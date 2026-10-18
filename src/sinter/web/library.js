import {h, button, field, check, notice, selectField, safeLink, dateTime, announce, download} from './ui.js';
import {request, waitForJob} from './api.js';
import {renderReport} from './reports.js';
import {savedReportRestore} from './saved-report-restore.js';
import {unsavedReportDrafts, reportSaveState, rememberReportSavedCopy, reportSavedCopyId} from './report-drafts.js';
import {authorizeReportReplacement, reportReplacementStillAllowed} from './report-replacement.js';
import {confirmAction} from './confirm-action.js';
import {savedReportList, savedReportReference} from './saved-report-list.js';

export async function library({onEditProject, setBusy} = {}) {
  const root = h('div');
  const opened = h('div');
  const openingStatus = h('div', {class: 'non-print', 'aria-live': 'polite'});
  const feedback = h('div', {class: 'non-print', 'aria-live': 'polite'});
  const pending = h('section', {class: 'card stack non-print', 'aria-label': 'Unsaved document or form work'});
  let knownReports = [];
  let disposed = false, currentReport = null, currentView = null;
  let opening = 0, refreshing = 0, readController = null, decisionController = null;
  const deleting = new Set(), uncertainDeletions = new Set();
  const active = () => !disposed && root.isConnected;

  function restoreControl(control, scroll) {
    if (!active()) return;
    const target = control?.isConnected && !control.disabled && !control.closest('[hidden]')
      ? control : savedCopies.element.querySelector('input');
    target?.focus({preventScroll: true});
    if (target === control) window.scrollTo(scroll.x, scroll.y);
  }

  async function authorization(title, confirmLabel) {
    decisionController?.abort();
    const decision = new AbortController();
    decisionController = decision;
    try {
      return await authorizeReportReplacement(currentReport, {isActive: active,
        confirm: () => confirmAction({title, confirmLabel, signal: decision.signal,
          description: 'The current document has unsaved changes or an unconfirmed save. '
            + 'It will remain in Pending work in this session. Apply and save it before closing Sinter.'})});
    } finally { if (decisionController === decision) decisionController = null; }
  }

  function showReport(report, {saved = false, recovered = false, id = null} = {}) {
    const close = button('Close open draft', async () => {
      const attempt = ++opening, scroll = {x: window.scrollX, y: window.scrollY};
      readController?.abort(); readController = null; openingStatus.replaceChildren();
      try {
        const allowed = await authorization('Close this draft view?', 'Close draft view');
        if (attempt !== opening || !active()) return;
        if (!allowed || !reportReplacementStillAllowed(currentReport, allowed)) {
          restoreControl(close, scroll); return;
        }
        currentView?.dispose?.(); currentView = null; currentReport = null;
        opened.replaceChildren(); refreshPending(); savedCopies.element.querySelector('input')?.focus({preventScroll: true});
      } catch (error) {
        if (attempt === opening && active()) { feedback.replaceChildren(notice(error.message, 'error')); restoreControl(close, scroll); }
      }
    }, 'quiet');
    let candidate;
    try {
      candidate = renderReport(report, {saved, recovered, onSaved: async () => {
        try { await refresh(); }
        catch (error) { if (active()) feedback.replaceChildren(notice('The draft was saved, but refreshing the list failed: ' + error.message, 'error')); }
      }});
      if (id) rememberReportSavedCopy(report, id);
      const toolbar = h('div', {class: 'button-row non-print'},
        report.input_snapshot && onEditProject ? button('Edit project inputs', () => onEditProject(report.input_snapshot)) : null, close);
      opened.replaceChildren(toolbar, candidate);
    } catch (cause) {
      candidate?.dispose?.();
      const error = new Error('This saved copy could not be displayed. Your current draft is unchanged. Keep a workspace backup before repairing the saved record.');
      error.cause = cause; throw error;
    }
    const previous = currentView;
    currentReport = report; currentView = candidate;
    let warning = '';
    try { previous?.dispose?.(); }
    catch { warning = 'The selected draft opened, but the previous view could not release all of its controls.'; }
    try {
      opened.scrollIntoView({block: 'start'});
      const heading = currentView.querySelector('h2, h3');
      if (heading) { heading.tabIndex = -1; heading.focus({preventScroll: true}); }
    } catch { warning ||= 'The selected draft opened. Scroll to its document to continue.'; }
    return warning;
  }

  async function openReport(metadata, control, recoveredReport = null) {
    if (!active()) return;
    const attempt = ++opening, scroll = {x: window.scrollX, y: window.scrollY};
    readController?.abort(); decisionController?.abort();
    try {
      const allowed = await authorization('Open another draft?', 'Open selected draft');
      if (!allowed || attempt !== opening || !active()) {
        if (attempt === opening) restoreControl(control, scroll);
        return;
      }
      if (metadata && deleting.has(metadata.id)) throw new Error('This saved copy is being deleted. Your open draft is unchanged.');
      const read = new AbortController(); readController = read;
      const cancel = button('Cancel opening', () => {
        if (attempt !== opening) return;
        opening++; read.abort(); readController = null; decisionController?.abort(); openingStatus.replaceChildren();
        restoreControl(control, scroll); announce('Opening cancelled. Your open draft is unchanged.');
      }, 'quiet');
      openingStatus.replaceChildren(h('p', {}, 'Opening the selected saved copy…'), cancel);
      const report = recoveredReport ?? await request('/api/reports/' + encodeURIComponent(metadata.id), {signal: read.signal});
      if (attempt !== opening || !active()) return;
      if (!reportReplacementStillAllowed(currentReport, allowed)) {
        feedback.replaceChildren(notice('Your open draft or its save state changed while the saved copy was loading. '
          + 'Your current work is kept. Open the selected copy again when ready.', 'warning')); return;
      }
      if (metadata && (deleting.has(metadata.id) || !knownReports.some(row => row.id === metadata.id))) {
        throw new Error('This saved copy changed or is being deleted. Check the saved list before opening it. Your open draft is unchanged.');
      }
      const warning = showReport(report, {saved: !recoveredReport, recovered: Boolean(recoveredReport), id: metadata?.id ?? null});
      feedback.replaceChildren(...(warning ? [notice(warning, 'warning')] : [])); refreshPending();
    } catch (error) {
      if (attempt === opening && active()) {
        feedback.replaceChildren(notice(error.message, 'error')); restoreControl(control, scroll);
      }
    } finally { if (attempt === opening) { readController = null; openingStatus.replaceChildren(); } }
  }

  async function deleteReport(metadata, control) {
    if (!active() || deleting.has(metadata.id)) return;
    const scroll = {x: window.scrollX, y: window.scrollY};
    const openCopy = () => reportSavedCopyId(currentReport) === metadata.id;
    let deleted = false, decision, restore = false;
    try {
      if (openCopy()) throw new Error('Close the open draft before deleting this saved copy. Nothing was deleted.');
      decision = new AbortController(); decisionController = decision;
      const approved = await confirmAction({signal: decision.signal, title: 'Delete this saved copy?', confirmLabel: 'Delete saved copy',
        description: 'Delete "' + metadata.title + '" (reference ' + savedReportReference(metadata.id, knownReports)
          + ') from My workspace? Downloaded copies are not deleted.'});
      if (!approved || !active()) { restore = active(); return; }
      if (openCopy()) throw new Error('This copy is now open. Close it before deleting its saved copy. Nothing was deleted.');
      deleting.add(metadata.id); savedCopies.setBusy(metadata.id, true); refreshing++;
      // A read started before deletion cannot later install that deleted copy.
      opening++; readController?.abort(); readController = null; openingStatus.replaceChildren();
      await request('/api/reports/delete', {data: {id: metadata.id}, acceptResponse: result => {
        if (result?.ok !== true) throw new Error('The app did not confirm deletion of the saved copy.');
        return result;
      }});
      deleted = true;
      if (!active()) return;
      knownReports = knownReports.filter(row => row.id !== metadata.id);
      savedCopies.update(knownReports);
      await refresh(); announce('Saved copy deleted.');
      feedback.replaceChildren(notice('Saved copy deleted. Your open draft is unchanged.', 'success')); restore = true;
    } catch (error) {
      if (active()) {
        const uncertain = deleting.has(metadata.id) && !deleted
          && !['not-sent', 'rejected'].includes(error.requestState?.outcome);
        if (uncertain) uncertainDeletions.add(metadata.id);
        feedback.replaceChildren(notice(deleted
          ? 'The saved copy was deleted, but refreshing the list failed: ' + error.message
          : uncertain ? 'Deletion was not confirmed. Your open draft is kept. Choose Refresh saved list to check before explicitly trying again. ' + error.message
            : error.message, deleted || uncertain ? 'warning' : 'error'));
        restore = true;
      }
    } finally {
      if (decisionController === decision) decisionController = null;
      if (!uncertainDeletions.has(metadata.id)) { deleting.delete(metadata.id); savedCopies.setBusy(metadata.id, false); }
      if (restore && (document.activeElement === control || document.activeElement === document.body
          || !document.activeElement?.isConnected)) restoreControl(control, scroll);
    }
  }

  const savedCopies = savedReportList({
    load: (id, signal) => request('/api/reports/' + encodeURIComponent(id), {signal}),
    onOpen: openReport, onDelete: deleteReport,
  });

  function refreshPending() {
    const drafts = unsavedReportDrafts();
    pending.hidden = !drafts.length;
    pending.replaceChildren(h('h3', {}, 'Pending work in this session'),
      notice('Open each draft to apply or discard pending text and summary rows. Save applied document edits before closing Sinter.'),
      ...drafts.map(({report}) => {
        const open = button('Open unsaved draft', () => openReport(null, open, report));
        return h('article', {}, h('strong', {}, report.document_title || report.title || 'Untitled draft'),
          h('p', {class: 'muted'}, reportSaveState(report).message), open);
      }));
  }

  async function refresh({checkUncertain = false} = {}) {
    const attempt = ++refreshing;
    const {reports} = await request('/api/reports');
    if (disposed || attempt !== refreshing) return false;
    knownReports = reports;
    if (checkUncertain) {
      for (const id of uncertainDeletions) { deleting.delete(id); savedCopies.setBusy(id, false); }
      uncertainDeletions.clear();
    }
    refreshPending(); savedCopies.update(reports); return true;
  }

  async function refreshRestoredCopies() {
    const updated = await refresh({checkUncertain: true});
    if (updated) savedCopies.showAll();
    return updated;
  }
  const restore = savedReportRestore({setBusy, onChanged: refreshPending,
    onSaved: refreshRestoredCopies, onCheckSaved: refreshRestoredCopies});
  root.append(h('header', {class: 'page-intro non-print'}, h('h2', {}, 'My workspace'),
    h('p', {}, 'Find saved wording and reopen its original evidence.')),
    h('div', {class: 'non-print'}, notice(globalThis.sinterBrowser
      ? 'Saved reports stay in this browser on this device, not a cloud account. They are not encrypted. Clearing browser storage, private browsing or device loss can erase saved work. Use Export saved workspace above to keep a separate backup.'
      : 'Saved reports stay in your local Sinter folder, not a cloud account. They are not encrypted. Export important work and protect access to this computer.')),
    feedback, openingStatus, pending,
    h('div', {class: 'button-row non-print'}, button('Refresh saved list', () => refresh({checkUncertain: true})
      .catch(error => feedback.replaceChildren(notice(error.message, 'error'))), 'quiet')),
    restore.element, savedCopies.element, opened);
  root.dispose = () => {
    disposed = true; opening++; refreshing++;
    readController?.abort(); decisionController?.abort();
    currentView?.dispose?.(); savedCopies.dispose(); restore.dispose();
  };
  await refresh();
  return root;
}

export async function watches({setBusy, seed = {}} = {}) {
  const root = h('div');
  const title = field('Watch name', 'text', seed.title || '', '', {required: true, maxLength: 200});
  const query = field('Exact search query', 'text', seed.query || '', 'Sent to NeuroForge on each check. Do not include private details.', {required: true, maxLength: 1024});
  const interval = selectField('Check frequency', [['86400', 'Daily'], ['604800', 'Weekly'], ['3600', 'Hourly']], '86400');
  const deadline = field('Confirmed closing date (optional)', 'date', '', 'Only enter a date checked with the funder. Confirm the closing time and time zone separately.');
  const consent = check('I authorise repeated searches for this exact query while Sinter is running.');
  const list = h('div', {class: 'stack'}), feedback = h('div', {'aria-live': 'polite'});
  async function refresh() {
    const {watches} = await request('/api/watches');
    list.replaceChildren(...watches.map(watch => {
      const results = watch.results || {};
      return h('article', {class: 'card'}, h('div', {class: 'watch-heading'}, h('h3', {}, watch.title),
        h('span', {class: 'badge'}, watch.enabled ? 'ACTIVE' : 'PAUSED')),
      h('p', {}, watch.query), h('p', {class: 'watch-meta'}, 'Last check: ' + dateTime(watch.last_run) + ' / Next due: ' + dateTime(watch.next_run)),
      watch.error ? notice(watch.error, 'error') : null,
      h('p', {class: 'muted'}, `${results.new?.length || 0} new / ${results.changed?.length || 0} changed / ${results.not_returned?.length || 0} not returned`),
      h('details', {}, h('summary', {}, 'Latest search results'),
        notice('Not returned does not mean closed or withdrawn. Verify opening and closing status on the current official page.'),
        ...(results.items || []).map(item => h('div', {class: 'source'}, safeLink(item.url, item.title), h('p', {}, item.content)))),
      h('div', {class: 'button-row'}, button(watch.enabled ? 'Pause watch' : 'Resume watch', async () => {
        try { await request('/api/watches/update', {data: {id: watch.id, enabled: !watch.enabled}}); await refresh(); }
        catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
      }), button('Delete watch', async () => {
        if (!window.confirm(`Delete "${watch.title}" and its saved results?`)) return;
        try { await request('/api/watches/delete', {data: {id: watch.id}}); await refresh(); }
        catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
      }, 'danger')));
    }));
    if (!watches.length) list.append(h('div', {class: 'empty'}, 'No watches yet. Give a recurring search a name above to start.'));
  }
  const form = h('form', {class: 'card'}, h('h3', {}, 'Keep an eye on something useful'),
    title.wrap, query.wrap, h('div', {class: 'form-grid'}, interval.wrap, deadline.wrap), consent.wrap,
    h('button', {type: 'submit', class: 'button primary'}, 'Create search watch'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!consent.input.checked) { feedback.replaceChildren(notice('Confirm permission for recurring searches first.', 'error')); return; }
    const submit = form.querySelector('[type=submit]');
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      await request('/api/watches', {data: {title: title.input.value, query: query.input.value,
        interval: Number(interval.input.value), deadline: deadline.input.value, consent: true}});
      feedback.replaceChildren(notice(globalThis.sinterBrowser ? 'Watch created. It checks while this webpage is open and active.' : 'Watch created. It checks while the launcher is running.', 'success'));
      title.input.value = ''; query.input.value = ''; deadline.input.value = ''; consent.input.checked = false;
      await refresh();
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    finally { submit.disabled = false; }
  });
  const run = button('Check due watches now', async () => {
    run.disabled = true; setBusy(true);
    try {
      const job = await request('/api/watches/check', {data: {}});
      const result = await waitForJob(job.id, state => { feedback.textContent = state.message || 'Checking...'; });
      feedback.replaceChildren(notice(`${result.checked} due checks attempted. Review any errors below.`, 'success'));
      await refresh();
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    finally { run.disabled = false; setBusy(false); }
  });
  const calendar = button('Download calendar reminders', async () => {
    try {
      if (globalThis.sinterBrowser) {
        const blob = await request('/api/calendar', {responseType:'blob'});
        download('sinter-reminders.ics', blob, 'text/calendar;charset=utf-8'); return;
      }
      const response = await fetch('/api/calendar', {cache: 'no-store'});
      if (!response.ok) throw new Error('Calendar export failed. Reload the app and try again.');
      download('sinter-reminders.ics', await response.text(), 'text/calendar;charset=utf-8');
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
  });
  root.append(h('header', {class: 'page-intro'}, h('h2', {}, 'Stay ahead of the next opportunity.'),
    h('p', {}, 'Saved search watches with change tracking, safe retries and calendar reminders.')),
    notice(globalThis.sinterBrowser ? 'Keep this page open and active for automatic checks. Browser sleep can delay checks. No email alerts or applications are sent.' : 'Keep the Sinter launcher running for automatic checks. Closing it pauses execution; overdue work resumes on restart. No email alerts or applications are sent.'),
    form, feedback, h('div', {class: 'button-row'}, run, calendar,
      button('Refresh results', () => refresh().catch(error => feedback.replaceChildren(notice(error.message, 'error'))))), list);
  await refresh();
  return root;
}
