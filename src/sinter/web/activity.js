/** Recover a running or completed job without submitting it a second time. */
import {h, button, notice, dateTime, download, markdown} from './ui.js';
import {request} from './api.js';
import {renderReport} from './reports.js';
export async function activityPage() {
  const list = h('div', {class: 'stack'}), output = h('div', {class: 'stack'}), status = h('div', {'aria-live': 'polite'});
  async function refresh() {
    try {
      const result = await request('/api/jobs'); list.replaceChildren();
      if (!result.jobs.length) list.append(notice('No retained tasks. Start a project, or open a saved report in My workspace.'));
      for (const job of result.jobs) {
        const card = h('article', {class: 'card'}, h('h3', {}, job.label), h('span', {class: 'badge'}, job.status),
          h('p', {}, job.error || job.message), h('small', {class: 'muted'}, 'Started: ' + dateTime(job.started_at || job.created_at)));
        if (job.status === 'done') card.append(button('Open result', async () => {
          try {
            const current = await request('/api/jobs/' + job.id);
            output.replaceChildren(current.result?.markdown ? renderReport(current.result) :
              h('div', {class: 'card'}, h('pre', {class: 'plain-wrap'}, JSON.stringify(current.result, null, 2)),
                button('Download task result', () => download('sinter-task.json', JSON.stringify(current.result, null, 2), 'application/json'))));
          } catch(error) { status.replaceChildren(notice(error.message, 'error')); }
        }, 'primary'));
        if (['queued', 'running'].includes(job.status)) card.append(button(job.cancel_requested ? 'Stop requested' : 'Stop this task', async () => {
          try { await request('/api/jobs/cancel', {data: {id: job.id}}); await refresh(); }
          catch(error) { status.replaceChildren(notice(error.message, 'error')); }
        }, 'quiet'));
        list.append(card);
      }
    } catch(error) { status.replaceChildren(notice(error.message + ' Refresh status rather than starting the original task again.', 'error')); }
  }
  await refresh();
  return h('div', {class: 'stack'}, h('header', {class: 'page-intro'}, h('h2', {}, 'Pick up where the connection left off.'),
    h('p', {}, 'A dropped browser connection does not necessarily stop the task. Check here before running it again.')),
    notice('Recent results remain in this running app for up to 30 minutes after completion, subject to its 20-task retention cap. They are not saved across app restarts. Save or download what you need.'),
    button('Refresh task status', refresh), status, list, output);
}
