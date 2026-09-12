import {h, button, field, check, notice, selectField, safeLink, dateTime, announce, download} from './ui.js';
import {request, waitForJob} from './api.js';
import {renderReport} from './reports.js';

export async function library({onEditProject} = {}) {
  const root = h('div');
  const list = h('div', {class: 'stack non-print'}), opened = h('div');
  const feedback = h('div', {class: 'non-print', 'aria-live': 'polite'});
  async function refresh() {
    const {reports} = await request('/api/reports');
    list.replaceChildren(...reports.map(report => h('article', {class: 'card'},
      h('h3', {}, report.title), h('p', {class: 'muted'}, 'Saved ' + dateTime(report.created_at)),
      h('div', {class: 'button-row'}, button('Open draft', async () => {
        try { const document = await request(`/api/reports/${report.id}`); opened.replaceChildren(...[document.input_snapshot && onEditProject ? h('div', {class: 'button-row non-print'}, button('Edit project inputs', () => onEditProject(document.input_snapshot))) : null, renderReport(document)].filter(Boolean)); opened.scrollIntoView({block: 'start'}); }
        catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
      }), button('Delete saved copy', async () => {
        if (!window.confirm(`Delete the saved copy of "${report.title}"? Downloaded copies are not deleted.`)) return;
        try { await request('/api/reports/delete', {data: {id: report.id}}); opened.replaceChildren(); await refresh(); announce('Saved copy deleted.'); }
        catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
      }, 'danger')))));
    if (!reports.length) list.append(h('div', {class: 'empty'}, h('h3', {}, 'Your next good piece of work belongs here.'),
      h('p', {}, 'Prepare a draft and choose Save to this computer. Nothing is saved automatically.')));
  }
  root.append(h('header', {class: 'page-intro non-print'}, h('h2', {}, 'My workspace'),
    h('p', {}, 'Explicitly saved drafts, with their original evidence packs.')),
    h('div', {class: 'non-print'}, notice('Saved reports stay in your local Sinter folder, not a cloud account. They are not encrypted. Export important work and protect access to this computer.')),
    feedback, list, opened);
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
      feedback.replaceChildren(notice('Watch created. It checks while the launcher is running.', 'success'));
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
      const response = await fetch('/api/calendar', {cache: 'no-store'});
      if (!response.ok) throw new Error('Calendar export failed. Reload the app and try again.');
      download('sinter-reminders.ics', await response.text(), 'text/calendar;charset=utf-8');
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
  });
  root.append(h('header', {class: 'page-intro'}, h('h2', {}, 'Stay ahead of the next opportunity.'),
    h('p', {}, 'Saved search watches with change tracking, safe retries and calendar reminders.')),
    notice('Keep the Sinter launcher running for automatic checks. Closing it pauses execution; overdue work resumes on restart. No email alerts or applications are sent.'),
    form, feedback, h('div', {class: 'button-row'}, run, calendar,
      button('Refresh results', () => refresh().catch(error => feedback.replaceChildren(notice(error.message, 'error'))))), list);
  await refresh();
  return root;
}
