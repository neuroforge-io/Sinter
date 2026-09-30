/** Everyday local tools; no API calls to external providers. */
import {h, field, selectField, button, notice, markdown, download, announce} from './ui.js';
import {request} from './api.js';

export function communityPage({remember, seed = {}}) {
  const title = field('Plan name', 'text', seed.title || '', 'For a volunteer roster, event checklist or committee action list.', {maxLength: 200});
  const rows = h('div', {class: 'stack'}), entries = [], output = h('div', {'aria-live': 'polite'});
  const planStatus = h('div', {'aria-live': 'polite'});
  let inputRevision = 0, preparedRevision = null, preparing = false;
  function updatePlanControls() {
    const stale = preparedRevision !== null && preparedRevision !== inputRevision;
    output.dataset.stale = String(stale);
    for (const control of output.querySelectorAll('button')) control.disabled = stale || preparing;
  }
  function invalidatePlan() {
    updatePlanControls();
    if (preparedRevision !== null && preparedRevision !== inputRevision) {
      planStatus.replaceChildren(notice('This plan reflects earlier inputs. Prepare my action plan again before saving or downloading it. Your current edits and the earlier plan are kept here.', 'warning'));
    }
  }
  const changed = () => {
    inputRevision++;
    remember('tools', {title: title.input.value, actions: entries.map(row => ({action: row.action.input.value, owner: row.owner.input.value, due: row.due.input.value, status: row.status.input.value}))});
    invalidatePlan();
  };
  title.input.addEventListener('input', changed);
  function add(value = {}) {
    if (entries.length >= 200) return;
    const action = field('Action', 'text', value.action || '', '', {maxLength: 2000});
    const owner = field('Person responsible', 'text', value.owner || '', 'Leave blank when unassigned.', {maxLength: 200});
    const due = field('Proposed target date (unconfirmed)', 'date', value.due || '', 'Planning date only. Confirm it with the responsible person.');
    const status = selectField('Progress', [['not_started', 'Not started'], ['in_progress', 'In progress'], ['done', 'Done']], value.status || 'not_started');
    const row = {action, owner, due, status};
    const card = h('div', {class: 'card plan-row'}, action.wrap, h('div', {class: 'form-grid'}, owner.wrap, due.wrap, status.wrap),
      button('Remove this action', () => { entries.splice(entries.indexOf(row), 1); card.remove(); changed(); }, 'quiet'));
    Object.values(row).forEach(f => f.input.addEventListener('input', changed)); entries.push(row); rows.append(card);
  }
  (seed.actions?.length ? seed.actions : [{}]).forEach(add);
  const prepare = button('Prepare my action plan', async () => {
    const submittedRevision = inputRevision;
    preparing = true; prepare.disabled = true; updatePlanControls();
    planStatus.replaceChildren(notice('Preparing from the current inputs. Editing them will require a new plan before you save or download.'));
    try {
      const result = await request('/api/community/plan', {data: {title: title.input.value, actions: entries.map(row => ({action: row.action.input.value, owner: row.owner.input.value, due: row.due.input.value, status: row.status.input.value}))}});
      output.replaceChildren(h('div', {class: 'button-row'}, button('Download spreadsheet CSV', () => download('sinter-action-plan.csv', result.csv, 'text/csv')),
        button('Download calendar dates', () => download('sinter-action-plan.ics', result.calendar, 'text/calendar')),
        button('Download plan JSON', () => download('sinter-action-plan.json', JSON.stringify(result, null, 2), 'application/json')),
        button('Save plan in My workspace', async () => { try { await request('/api/reports', {data: {report: result}}); announce('Plan saved.'); } catch (error) { output.prepend(notice(error.message, 'error')); } })), markdown(result.markdown));
      preparedRevision = submittedRevision;
      planStatus.replaceChildren(); invalidatePlan();
      announce(submittedRevision === inputRevision ? 'Action plan ready.' : 'Inputs changed during preparation. Prepare the plan again before saving or downloading.');
    } catch (error) { planStatus.replaceChildren(notice(error.message + ' Your inputs and any earlier prepared plan are still here.', 'error')); }
    finally { preparing = false; prepare.disabled = false; updatePlanControls(); }
  }, 'primary');
  const before = field('Earlier wording', 'textarea'), after = field('Updated wording', 'textarea'), comparison = h('div', {'aria-live': 'polite'});
  const compare = button('Show exactly what changed', async () => {
    compare.disabled = true;
    try {
      const result = await request('/api/community/compare', {data: {before: before.input.value, after: after.input.value}});
      comparison.replaceChildren(notice(`${result.changed_blocks} changed blocks. ${result.notice}`), ...result.changes.map(row => h('article', {class: 'card'},
        h('h4', {}, `${row.kind}: earlier line ${row.before_start}, updated line ${row.after_start}`), h('div', {class: 'form-grid'}, h('div', {}, h('strong', {}, 'Before'), h('pre', {class: 'plain-wrap'}, row.before || '(none)')), h('div', {}, h('strong', {}, 'After'), h('pre', {class: 'plain-wrap'}, row.after || '(none)'))))));
    } catch (error) { comparison.replaceChildren(notice(error.message, 'error')); }
    finally { compare.disabled = false; }
  });
  return h('div', {class: 'stack'}, h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'LESS ADMIN. MORE DOING.'),
    h('h2', {}, 'Small tools. Real time saved.'), h('p', {}, 'Organise volunteers and tasks, export proposed dates and compare document revisions. Everything here stays local.')),
    title.wrap, rows, h('div', {class: 'button-row'}, button('Add another action', () => { add(); changed(); }), prepare), planStatus, output,
    h('details', {class: 'card'}, h('summary', {}, 'Compare two versions of a document'),
      h('div', {class: 'form-grid'}, before.wrap, after.wrap), compare, comparison));
}
