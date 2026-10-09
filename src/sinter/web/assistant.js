/** A campaign model draft starts with a local, explicit context preview. */
import {h, button, selectField, field, check, notice, download} from './ui.js';
import {request, waitForJob} from './api.js';
import {renderReport} from './reports.js';
import {campaignActionOwnerState} from './campaign-owner.js';
import {campaignActionPhaseLabel} from './campaign-plan.js';

export async function campaignAssistant({setBusy = () => {}} = {}) {
  const {campaigns} = await request('/api/campaigns');
  if (!campaigns.length) return h('section', {class: 'card'}, h('h3', {}, 'Start with a saved campaign'),
    h('p', {}, 'Save a campaign with a route and recorded checks, then ask your model to help with the next step.'),
    h('a', {href: '#campaigns', class: 'button primary'}, 'Open funding campaigns'));
  const settings = (await request('/api/settings')).settings;
  const campaign = selectField('Saved campaign', campaigns.map(item => [item.id, item.title]));
  const route = selectField('Campaign route', []);
  const task = selectField('Help me with', [['next_actions', 'Prioritise next actions'],
    ['eligibility', 'Understand recorded checks'], ['enquiry', 'Draft an enquiry']]);
  const question = field('Anything else to focus on?', 'textarea', '', 'Optional. This is included in the model request.', {maxLength: 2000, rows: 2});
  const checks = h('div', {class: 'stack'}), actions = h('div', {class: 'stack'}), preview = h('div'), output = h('div');
  const feedback = h('div', {'aria-live': 'polite'});
  const consent = check('Send only the displayed context to my selected model.');
  let saved, selected = [], selectedActions = [], prepared = null, payload = null, busy = false, jobId, cancelRequested = false, loadSequence = 0, previewSequence = 0;
  function showReport(report) {
    output.replaceChildren(notice(report.notice, report.incomplete ? 'error' : ''), renderReport(report),
      button('Download the assistant record', () => download(`sinter-campaign-assistant-${report.incomplete ? 'INCOMPLETE' : 'DRAFT'}.json`, JSON.stringify(report, null, 2), 'application/json')));
    output.scrollIntoView({block: 'start'});
  }
  const send = button('Ask my assistant', async () => {
    if (busy || !prepared || !consent.input.checked) return;
    busy = true; cancelRequested = false; setBusy(true); send.disabled = true; cancel.hidden = false; cancel.disabled = false;
    controls.disabled = true; output.replaceChildren();
    feedback.replaceChildren(notice('Starting your campaign assistant…'));
    try {
      const job = await request('/api/assistant/job', {data: {...payload, context_hash: prepared.context_hash, consent: true}});
      jobId = job.job_id;
      if (cancelRequested) await request('/api/jobs/cancel', {data: {id: jobId}});
      const report = await waitForJob(jobId, job => feedback.replaceChildren(notice(job.message || 'Working…')));
      showReport(report);
      feedback.replaceChildren();
    } catch (error) {
      feedback.replaceChildren(notice(error.message, 'error'));
      if (error.partialResult?.result?.content) showReport(error.partialResult);
    } finally {
      busy = false; setBusy(false); controls.disabled = false; jobId = null; cancel.hidden = true; cancelRequested = false;
      send.disabled = !consent.input.checked || !prepared || !prepared.fit.allowed;
    }
  }, 'primary');
  send.disabled = true;
  const cancel = button('Stop assistant', async () => {
    cancelRequested = true; cancel.disabled = true;
    feedback.replaceChildren(notice('Stopping the existing task…'));
    try { if (jobId) await request('/api/jobs/cancel', {data: {id: jobId}}); }
    catch (error) { feedback.replaceChildren(notice(`${error.message} Open Recent activity to check the task before starting another.`, 'error')); cancel.disabled = false; }
  });
  cancel.hidden = true;
  function invalidate() { previewSequence++; prepared = null; payload = null; preview.replaceChildren(); consent.input.checked = false; send.disabled = true; }
  function updateHeldActions() {
    for (const item of selectedActions) {
      item.entry.input.disabled = saved.document.actions[item.index].status === 'held'
        && task.input.value === 'next_actions';
      if (item.entry.input.disabled) item.entry.input.checked = false;
    }
  }
  function chooseRoute() {
    invalidate(); selected = []; selectedActions = [];
    checks.replaceChildren(h('h4', {}, 'Choose the recorded checks to include'),
      h('p', {class: 'fine'}, 'Only selected checks and actions, the campaign objective and route details enter the preview. Other routes, communications, files and profile details are excluded.'));
    saved.document.requirements.forEach((row, index) => {
      if (row.opportunity !== route.input.value) return;
      const entry = check(`${row.rule} · ${row.status}`);
      entry.input.addEventListener('change', invalidate);
      selected.push({index, entry}); checks.append(entry.wrap);
    });
    if (!selected.length) checks.append(notice('No checks are recorded for this route. You can still ask for the next step using its saved details.'));
    actions.replaceChildren(h('h4', {}, 'Choose actions to include'), h('p', {class: 'fine'}, 'Include relevant existing actions so the assistant can avoid repeating completed work. On hold actions are retained, not completed, and cannot be selected for next-action suggestions.'));
    saved.document.actions.forEach((row, index) => {
      if (row.opportunity && row.opportunity !== route.input.value) return;
      const entry = check(`${row.task} · ${row.status === 'held' ? 'On hold · retained, not completed' : row.status}`);
      entry.input.addEventListener('change', invalidate);
      selectedActions.push({index, entry}); actions.append(entry.wrap);
    });
    updateHeldActions();
  }
  async function chooseCampaign() {
    const sequence = ++loadSequence;
    invalidate(); review.disabled = true;
    const loaded = await request('/api/campaigns/' + campaign.input.value);
    if (sequence !== loadSequence) return;
    saved = loaded;
    route.input.replaceChildren(...saved.document.opportunities.map(item => h('option', {value: item.name}, item.name)));
    chooseRoute(); review.disabled = !saved.document.opportunities.length;
  }
  campaign.input.addEventListener('change', () => chooseCampaign().catch(error => feedback.replaceChildren(notice(error.message, 'error'))));
  route.input.addEventListener('change', chooseRoute);
  task.input.addEventListener('change', () => { invalidate(); if (saved) updateHeldActions(); });
  question.input.addEventListener('input', invalidate);
  const review = button('Preview what will be sent', async () => {
    invalidate(); feedback.replaceChildren();
    const sequence = previewSequence;
    review.disabled = true;
    try {
      const nextPayload = {id: saved.id, revision: saved.revision, opportunity: route.input.value,
        checks: selected.filter(item => item.entry.input.checked).map(item => item.index),
        actions: selectedActions.filter(item => item.entry.input.checked).map(item => item.index),
        task: task.input.value, question: question.input.value};
      const nextPreview = await request('/api/assistant/preview', {data: nextPayload});
      if (sequence !== previewSequence) return;
      payload = nextPayload; prepared = nextPreview;
      const context = prepared.context;
      preview.replaceChildren(h('section', {class: 'card'}, h('h3', {}, 'What your assistant will see'),
        h('p', {class: 'fine'}, `${prepared.selected_checks} of ${prepared.available_checks} checks and ${prepared.selected_actions} actions selected · saved revision ${prepared.revision}`),
        h('p', {}, `Destination: ${prepared.connection.api_url} · model ${prepared.connection.model}`),
        notice(prepared.fit.message, prepared.fit.allowed ? '' : 'error'),
        h('h4', {}, context.organisation), h('p', {}, context.objective),
        h('h4', {}, context.route.name),
        h('p', {}, `Recorded route state: ${context.route.status}. Application: ${context.route.application_mode}. Applicant: ${context.route.applicant || 'Not recorded'}${context.route.applicant_confirmed ? ' (user-confirmed)' : ' (unconfirmed)'}.`),
        h('p', {}, `Recorded window: ${context.route.application_window}. Deadline: ${context.route.deadline || 'Not recorded'}. Checked: ${context.route.window_checked_at || 'Not recorded'}.`),
        context.route.window_source_quote ? h('blockquote', {}, context.route.window_source_quote) : null,
        ...context.selected_checks.map(row => h('section', {}, h('h4', {}, `Check ${row.record}: ${row.rule}`),
          h('p', {class: 'fine'}, `Recorded assessment: ${row.status} · checked ${row.checked_at || 'Not recorded'}`),
          h('p', {class: 'fine'}, row.source_snapshot),
          h('p', {}, row.evidence || 'Applicant evidence not recorded.'),
          row.source_quote ? h('blockquote', {}, row.source_quote) : null,
          row.source_url ? h('p', {}, row.source_url) : null)),
        ...context.selected_actions.map(row => h('section', {}, h('h4', {}, `Action ${row.record}: ${row.task}`),
          h('p', {}, `Recorded state: ${row.status}. Owner: ${campaignActionOwnerState(row.owner, row.owner_confirmed, row.owner_kind).summary}. Proposed date: ${row.due || 'Not recorded'}. Scope: ${row.opportunity || 'Campaign-wide'} (${row.scope_confirmed ? 'confirmed' : 'unconfirmed'}); phase ${campaignActionPhaseLabel(row.submission_phase)}.`))),
        question.input.value ? h('p', {}, 'Your focus: ' + question.input.value) : null,
        h('details', {}, h('summary', {}, 'View the full request'), h('pre', {class: 'help-code'}, prepared.content))),
        consent.wrap, h('div', {class: 'button-row'}, send, cancel));
    } catch (error) { if (sequence === previewSequence) feedback.replaceChildren(notice(error.message, 'error')); }
    finally { review.disabled = !saved?.document.opportunities.length; }
  });
  consent.input.addEventListener('change', () => { send.disabled = busy || !prepared || !prepared.fit.allowed || !consent.input.checked; });
  const controls = h('fieldset', {class: 'card'}, campaign.wrap, route.wrap, task.wrap, checks,
    h('details', {}, h('summary', {}, 'Include existing actions'), actions), question.wrap, review);
  await chooseCampaign();
  return h('div', {class: 'stack'}, h('p', {class: 'workspace-hint'}, `Selected model: ${settings.model} · ${settings.api_url}`),
    h('p', {}, 'Ask for a practical next step using your recorded campaign context. Suggestions stay separate from your campaign until you choose what to use.'),
    controls, preview, feedback, output, h('a', {href: '#settings', class: 'button quiet'}, 'Change assistant connection'));
}
