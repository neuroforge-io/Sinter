/** A local, revisioned funding workspace. Every status is entered by a person. */
import {h, field, selectField, button, notice, download, announce, safeLink} from './ui.js';
import {request} from './api.js';
import {renderReport} from './reports.js';

const blank = () => ({schema: 'sinter-campaign/v1', title: '', organisation: '', objective: '',
  opportunities: [], requirements: [], answers: [], budget: [], actions: [], sources: []});
const opportunityStates = [['researching', 'Researching'], ['open', 'Open'], ['upcoming', 'Upcoming'],
  ['clarification', 'Needs clarification'], ['paused', 'Paused'], ['submitted', 'Submitted'], ['closed', 'Closed']];
const checkStates = [['unknown', 'Not checked'], ['clarification', 'Needs clarification'],
  ['met', 'Evidence supports this requirement'], ['not_met', 'Evidence does not support it']];
const countCharacters = value => [...value].length;
const money = value => value == null || value === '' ? 'Not confirmed' : new Intl.NumberFormat('en-AU', {style: 'currency', currency: 'AUD'}).format(Number(value));

export async function campaignsPage({setBusy = () => {}, remember = () => {}, seed = {}} = {}) {
  let document = structuredClone(seed.document || blank()), savedId = seed.id || null, revision = seed.revision || null;
  let dirty = Boolean(seed.dirty), selected = 0, tab = 'overview', busy = false;
  const root = h('div', {class: 'campaign-page'}), shelf = h('div', {class: 'campaign-shelf'});
  const feedback = h('div', {'aria-live': 'polite'}), status = h('span', {class: 'campaign-save-state', role: 'status'});
  const summary = h('div', {class: 'campaign-summary'}), editor = h('div'), output = h('div');
  const savedList = h('div', {class: 'campaign-saved-list'});
  const saveButton = button('Save campaign', () => save(), 'primary');
  const prepareButton = button('Prepare campaign brief', () => prepare(), 'quiet');

  function changed() {
    dirty = true; status.textContent = 'Unsaved changes';
    remember('campaigns', {document: structuredClone(document), id: savedId, revision, dirty});
    renderSummary();
  }
  function error(message) { feedback.replaceChildren(notice(message, 'error')); }
  function input(label, type, row, key, help = '', props = {}, callback = () => {}) {
    const entry = field(label, type, row[key] ?? '', help, props);
    entry.input.addEventListener('input', () => { row[key] = entry.input.value; callback(entry.input); changed(); });
    return entry;
  }
  function choice(label, choices, row, key, callback = () => {}) {
    const entry = selectField(label, choices, row[key]);
    entry.input.addEventListener('change', () => { row[key] = entry.input.value; changed(); callback(); });
    return entry;
  }
  function remove(rows, item, label) {
    return button(label, () => { rows.splice(rows.indexOf(item), 1); changed(); renderEditor(); }, 'quiet');
  }
  function lock(value) { busy = value; setBusy(value); saveButton.disabled = value; prepareButton.disabled = value; editor.inert = value; transfers.inert = value; }
  function apply(next, id = null, rev = null) {
    document = structuredClone(next); savedId = id; revision = rev; dirty = false; selected = 0;
    status.textContent = id ? 'Saved on this computer' : 'Not saved yet'; output.replaceChildren();
    editor.replaceChildren();
    remember('campaigns', {document: structuredClone(document), id: savedId, revision, dirty});
    renderEditor(); renderSummary();
  }
  function canReplace() { return !dirty || window.confirm('Replace these unsaved campaign edits? Export a backup or save them first if you need to keep them.'); }
  async function refreshShelf() {
    const result = await request('/api/campaigns');
    savedList.replaceChildren(...result.campaigns.map(item => h('div', {class: 'campaign-saved-item'},
      h('div', {}, h('strong', {}, item.title), h('small', {}, `Revision ${item.revision}`)),
      button('Open ' + item.title, async () => {
        if (busy || !canReplace()) return;
        lock(true);
        try { const saved = await request('/api/campaigns/' + item.id); apply(saved.document, saved.id || item.id, saved.revision); feedback.replaceChildren(notice('Campaign opened. Continue where you left off.', 'success')); }
        catch (problem) { error(problem.message); }
        finally { lock(false); }
      }, 'quiet'))));
    if (!result.campaigns.length) savedList.append(h('p', {class: 'fine'}, 'Saved campaigns will appear here.'));
  }
  async function save() {
    if (busy) return;
    lock(true); feedback.replaceChildren();
    try {
      const saved = await request('/api/campaigns/save', {data: {document, id: savedId, revision}});
      document = saved.document; savedId = saved.id; revision = saved.revision; dirty = false;
      renderEditor(); renderSummary();
      remember('campaigns', {document: structuredClone(document), id: savedId, revision, dirty});
      status.textContent = 'Saved on this computer';
      feedback.replaceChildren(notice('Campaign saved. Answers, costs, checks and actions will be here when you return.', 'success'));
      await refreshShelf(); announce('Campaign saved.');
    } catch (problem) { error(problem.message + ' Your edits are still here. Export a campaign backup before reopening another version.'); }
    finally { lock(false); }
  }
  async function prepare() {
    if (busy) return;
    lock(true); feedback.replaceChildren();
    try {
      const report = await request('/api/campaigns/prepare', {data: {document}});
      output.replaceChildren(renderReport(report)); output.scrollIntoView({block: 'start'});
      announce('Campaign brief prepared. Unknowns and review items remain visible.');
    } catch (problem) { error(problem.message); }
    finally { lock(false); }
  }
  function exportBackup() {
    download('sinter-campaign-backup.json', JSON.stringify(document, null, 2), 'application/json');
  }
  const imported = field('Import campaign backup', 'file', '', 'Sinter campaign JSON, up to 1 MB. Importing stays on this computer.', {accept: '.json'});
  imported.input.addEventListener('change', async () => {
    if (busy) return;
    const file = imported.input.files[0]; if (!file) return;
    lock(true);
    try {
      if (file.size > 1_000_000) throw new Error('Choose a campaign backup smaller than 1 MB.');
      const candidate = JSON.parse(await file.text());
      const report = await request('/api/campaigns/prepare', {data: {document: candidate}});
      if (!canReplace()) return;
      apply(report.campaign); dirty = true; changed();
      feedback.replaceChildren(notice('Campaign imported locally. Save campaign to keep this copy.', 'success'));
    } catch (problem) { error(problem instanceof SyntaxError ? 'This file is not valid campaign JSON. Your current campaign is unchanged.' : problem.message); }
    finally { imported.input.value = ''; lock(false); }
  });

  function renderSummary() {
    const pending = document.requirements.filter(row => !['met', 'not_met'].includes(row.status)
      || ![row.evidence, row.source_url, row.source_quote, row.checked_at].every(value => value?.trim()));
    const over = document.answers.filter(row => row.limit && countCharacters(row.text || '') > Number(row.limit));
    const quotes = document.budget.filter(row => row.unit_cost == null || row.unit_cost === '' || !row.quote_reference?.trim());
    const open = document.actions.filter(row => row.status !== 'done');
    shelf.replaceChildren(...(document.title ? [h('h3', {}, document.title), h('p', {class: 'fine'}, document.organisation)] : []));
    summary.replaceChildren(...[[pending.length, 'requirements to check'], [over.length, 'answers over their limit'],
      [quotes.length, 'costs needing a quote'], [open.length, 'next actions']].map(([count, label]) =>
      h('div', {}, h('strong', {}, count), h('span', {}, label))));
  }
  function scopeChoices() { return [['', 'Whole campaign'], ...document.opportunities.map(row => [row.name, row.name])]; }
  function addOpportunity() {
    let number = document.opportunities.length + 1;
    while (document.opportunities.some(row => row.name === 'Opportunity ' + number)) number++;
    document.opportunities.push({name: 'Opportunity ' + number, funder: '', url: '', deadline: '', decision_window: '', ceiling: null, fit: '', status: 'researching'});
    selected = document.opportunities.length - 1; changed(); renderEditor();
  }
  function renderEditor() {
    const detailsOpen = editor.querySelector('.campaign-details')?.open ?? !document.title;
    const title = input('Campaign name', 'text', document, 'title', '', {required: true, maxLength: 200});
    const organisation = input('Applicant organisation', 'text', document, 'organisation', 'Use the applicant’s legal name, which may differ from the school or venue.', {maxLength: 1024});
    const objective = input('What will this campaign make possible?', 'textarea', document, 'objective', 'Describe the project, who benefits and the intended timing. Keep separate years or options clear.', {rows: 3, maxLength: 12000});
    const details = h('details', {class: 'campaign-details', open: detailsOpen}, h('summary', {}, 'Campaign details'), title.wrap, organisation.wrap, objective.wrap);
    const tabs = h('div', {class: 'campaign-tabs', role: 'tablist', 'aria-label': 'Campaign sections'});
    const panel = h('section', {class: 'campaign-section', role: 'tabpanel'});
    const available = [['overview', 'Opportunities'], ['answers', 'Application answers'], ['budget', 'Budget'], ['actions', 'Next actions'], ['sources', 'Sources']];
    for (const [id, label] of available) {
      const control = button(label, () => { tab = id; renderEditor(); }, 'campaign-tab');
      control.setAttribute('role', 'tab'); control.setAttribute('aria-selected', String(tab === id)); control.tabIndex = tab === id ? 0 : -1;
      control.addEventListener('keydown', event => {
        const at = available.findIndex(([key]) => key === tab);
        const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (offset) { event.preventDefault(); tab = available[(at + offset + available.length) % available.length][0]; renderEditor(); editor.querySelector('[aria-selected="true"]').focus(); }
      });
      tabs.append(control);
    }
    panel.setAttribute('aria-label', available.find(([id]) => id === tab)[1]);
    if (tab === 'overview') renderOpportunities(panel);
    else if (tab === 'answers') renderAnswers(panel);
    else if (tab === 'budget') renderBudget(panel);
    else if (tab === 'actions') renderActions(panel);
    else renderSources(panel);
    editor.replaceChildren(details, tabs, panel);
  }
  function opportunityPicker(change) {
    const pick = selectField('Working on opportunity', document.opportunities.map((row, index) => [String(index), row.name]), String(selected));
    pick.input.addEventListener('change', () => { selected = Number(pick.input.value); change(); });
    return pick.wrap;
  }
  function renderOpportunities(panel) {
    panel.append(h('div', {class: 'campaign-section-heading'}, h('div', {}, h('h3', {}, 'A shortlist you can act on'),
      h('p', {class: 'muted'}, 'Keep timing, project fit and unanswered requirements beside each opportunity.')), button('Add opportunity', addOpportunity, 'quiet')));
    if (!document.opportunities.length) {
      panel.append(h('div', {class: 'campaign-empty'}, h('h4', {}, 'Start with one opportunity'), h('p', {}, 'Add a funder or programme, then record what you know and what needs checking. No eligibility is assumed.'))); return;
    }
    const rail = h('div', {class: 'campaign-opportunities', 'aria-label': 'Funding opportunities'});
    document.opportunities.forEach((row, index) => {
      const choose = button('', () => { selected = index; renderEditor(); }, 'campaign-opportunity');
      choose.setAttribute('aria-pressed', String(index === selected));
      choose.append(h('strong', {}, row.name), h('span', {}, row.funder || 'Funder to confirm'),
        h('small', {}, row.ceiling == null || row.ceiling === '' ? 'Amount to confirm' : 'Up to ' + money(row.ceiling)),
        h('small', {}, row.deadline ? 'Closes ' + row.deadline : 'Deadline not confirmed'));
      rail.append(choose);
    });
    selected = Math.min(selected, document.opportunities.length - 1);
    const item = document.opportunities[selected], focus = h('section', {class: 'campaign-focus', 'aria-label': 'Selected opportunity'});
    const name = input('Opportunity name', 'text', item, 'name', '', {required: true, maxLength: 200}, () => {
      for (const collection of ['requirements', 'answers', 'budget']) for (const row of document[collection]) if (row.opportunity === previousName) row.opportunity = item.name;
      previousName = item.name; rail.children[selected].querySelector('strong').textContent = item.name;
    });
    let previousName = item.name;
    const funder = input('Funder', 'text', item, 'funder', '', {maxLength: 300});
    const url = input('Programme page', 'url', item, 'url', '', {maxLength: 2000});
    const deadline = input('Confirmed closing date', 'date', item, 'deadline', 'Leave blank if the date has not been checked.');
    const decision = input('Decision timing', 'text', item, 'decision_window', 'For example, a decision several months after applications close.', {maxLength: 1000});
    const ceiling = input('Maximum available (AUD)', 'number', item, 'ceiling', 'An amount offered is not an award or project budget.', {min: 0, step: '.01'}, element => { item.ceiling = element.value || null; });
    const state = choice('Opportunity status', opportunityStates, item, 'status');
    const fit = input('Project fit and timing', 'textarea', item, 'fit', 'Which project option could this support? Record any exclusions or conditions before committing costs.', {rows: 3, maxLength: 6000});
    const opportunityEditor = h('details', {class: 'campaign-opportunity-editor', open: !item.funder && !item.fit},
      h('summary', {}, 'Edit opportunity details'), h('div', {class: 'form-grid'}, name.wrap, funder.wrap), url.wrap,
      h('div', {class: 'form-grid'}, deadline.wrap, decision.wrap, ceiling.wrap, state.wrap), fit.wrap);
    focus.append(h('header', {class: 'campaign-focus-heading'}, h('span', {class: 'eyebrow'}, item.funder || 'FUNDER TO CONFIRM'),
      h('h3', {}, item.name), item.url ? safeLink(item.url, 'Open programme guidance') : h('p', {class: 'fine'}, 'Programme link not added yet.')),
      h('dl', {class: 'campaign-opportunity-facts'},
        h('div', {}, h('dt', {}, 'Maximum available'), h('dd', {}, money(item.ceiling))),
        h('div', {}, h('dt', {}, 'Application closes'), h('dd', {}, item.deadline || 'Not confirmed')),
        h('div', {}, h('dt', {}, 'Decision timing'), h('dd', {}, item.decision_window || 'Not confirmed')),
        h('div', {}, h('dt', {}, 'Status'), h('dd', {}, opportunityStates.find(([key]) => key === item.status)?.[1] || 'Researching'))),
      h('div', {class: 'campaign-fit'}, h('strong', {}, 'Project fit and timing'), h('p', {}, item.fit || 'Record which project option this opportunity could support and what needs checking.')),
      opportunityEditor);
    const requirements = h('div', {class: 'campaign-checks'});
    function addRequirement() { document.requirements.push({opportunity: item.name, rule: '', status: 'unknown', evidence: '', source_url: '', source_quote: '', checked_at: ''}); changed(); renderEditor(); }
    requirements.append(h('div', {class: 'campaign-section-heading'}, h('h4', {}, 'What must be true?'), button('Add requirement', addRequirement, 'quiet')),
      h('p', {class: 'fine'}, 'Check each condition against current official guidance. These records do not determine overall eligibility.'));
    for (const row of document.requirements.filter(row => row.opportunity === item.name)) {
      const proof = h('p', {class: 'campaign-proof-status', role: 'status'});
      const stateLabel = h('span', {class: 'campaign-check-state'}), preview = h('span', {class: 'campaign-check-preview'});
      function updateProof() {
        const asserted = ['met', 'not_met'].includes(row.status);
        const complete = [row.evidence, row.source_url, row.source_quote, row.checked_at].every(value => value?.trim());
        stateLabel.textContent = asserted && !complete ? 'Evidence missing'
          : row.status === 'met' ? 'Supported · human checked' : row.status === 'not_met' ? 'Not supported · human checked'
            : row.status === 'clarification' ? 'Needs clarification' : 'Not checked';
        stateLabel.dataset.state = asserted && !complete ? 'unknown' : row.status;
        const note = row.evidence?.trim() || '';
        preview.textContent = note ? note.length > 180 ? note.slice(0, 180) + '… Open for the full note.' : note : 'No evidence note added yet.';
        proof.textContent = asserted && !complete ? 'This marked check is still unresolved. Add the source, exact wording, date and what the evidence establishes.'
          : asserted ? 'Human-entered assessment with a source record. Confirm interpretation with the funder.' : 'Keep this open until the condition is resolved.';
      }
      const rule = input('Requirement', 'text', row, 'rule', '', {maxLength: 4000});
      const status = choice('Requirement status', checkStates, row, 'status', updateProof);
      const reason = input('What the evidence establishes or leaves unclear', 'textarea', row, 'evidence', '', {rows: 2, maxLength: 6000}, updateProof);
      const source = input('Official source link', 'url', row, 'source_url', '', {maxLength: 2000}, updateProof);
      const quote = input('Exact source wording', 'textarea', row, 'source_quote', 'Keep conditions and exclusions with the quote.', {rows: 3, maxLength: 4000}, updateProof);
      const date = input('Date checked', 'date', row, 'checked_at', '', {}, updateProof);
      updateProof();
      const heading = h('summary', {}, h('span', {class: 'campaign-check-title'}, row.rule || 'New requirement'), stateLabel, preview);
      rule.input.addEventListener('input', () => { heading.querySelector('.campaign-check-title').textContent = row.rule || 'New requirement'; });
      requirements.append(h('details', {class: 'campaign-requirement', open: !row.rule}, heading,
        h('article', {class: 'campaign-check-editor', 'aria-label': 'Requirement check'}, rule.wrap, status.wrap, proof, reason.wrap,
        h('details', {open: Boolean(row.source_url || row.source_quote)}, h('summary', {}, 'Supporting source'), source.wrap, quote.wrap, date.wrap),
        remove(document.requirements, row, 'Remove requirement'))));
    }
    if (!document.requirements.some(row => row.opportunity === item.name)) requirements.append(h('p', {class: 'fine'}, 'No requirements checked yet. Start with applicant type, timing and permitted costs.'));
    requirements.append(button('Draft clarification letter', () => {
      const open = document.requirements.filter(row => row.opportunity === item.name && (row.status !== 'met'
        || ![row.evidence, row.source_url, row.source_quote, row.checked_at].every(value => value?.trim())));
      remember('brief', {workflow: 'brief', title: 'Clarification: ' + item.name, recipient: item.funder,
        notes: document.objective + (item.fit ? '\n\nOur understanding to confirm: ' + item.fit : ''),
        questions: open.length ? open.map(row => 'Please clarify: ' + row.rule).join('\n')
          : 'Please confirm the current applicant conditions, permitted project costs and approval timing.',
        organisation: document.organisation, use_search: false, use_model: false});
      location.hash = 'brief';
    }, 'quiet'));
    focus.append(requirements);
    panel.append(h('div', {class: 'campaign-opportunity-layout'}, rail, focus));
  }
  function renderAnswers(panel) {
    panel.append(h('h3', {}, 'Prepare answers for the funder’s form'), h('p', {class: 'muted'}, 'Keep the exact question and its limit together. Drafts can be saved over the limit; they still need shortening before use.'));
    if (!document.opportunities.length) { panel.append(notice('Add an opportunity first so each answer belongs to the right application.')); return; }
    selected = Math.min(selected, document.opportunities.length - 1);
    panel.append(opportunityPicker(renderEditor));
    const opportunity = document.opportunities[selected].name;
    panel.append(button('Add application question', () => {
      document.answers.push({opportunity, label: '', text: '', limit: null, status: 'draft'}); changed(); renderEditor();
    }, 'quiet'));
    for (const row of document.answers.filter(row => row.opportunity === opportunity)) {
      const label = input('Application question', 'textarea', row, 'label', 'Copy the actual wording from the application form.', {rows: 2, maxLength: 300});
      const counter = h('p', {class: 'campaign-character-count', role: 'status'});
      function update() {
        const used = countCharacters(row.text || ''), limit = Number(row.limit);
        counter.textContent = limit > 0 ? `${used} / ${limit} characters${used > limit ? ' · ' + (used - limit) + ' over — shorten before using' : ' · within limit'}` : `${used} characters · confirm the form’s limit`;
        counter.classList.toggle('over-limit', limit > 0 && used > limit);
      }
      const limit = input('Character limit', 'number', row, 'limit', 'Keep this blank if the form does not specify a limit.', {min: 1, max: 20000, step: 1}, element => { row.limit = element.value ? Number(element.value) : null; update(); });
      const answer = input('Draft answer', 'textarea', row, 'text', '', {rows: 5, maxLength: 20000}, () => { row.status = 'draft'; reviewed.input.value = 'draft'; update(); });
      const reviewed = choice('Answer review', [['draft', 'Needs review'], ['reviewed', 'Reviewed by me']], row, 'status');
      const copied = h('p', {class: 'fine', 'aria-live': 'polite'});
      update();
      panel.append(h('article', {class: 'campaign-row', 'aria-label': 'Application answer'}, label.wrap, h('div', {class: 'form-grid'}, limit.wrap, reviewed.wrap), answer.wrap, counter,
        h('div', {class: 'button-row'}, button('Copy this answer', async () => {
          try { await navigator.clipboard.writeText(row.text); copied.textContent = row.limit && countCharacters(row.text) > row.limit ? 'Copied as written. Shorten this draft before pasting it into the application.' : 'Answer copied.'; }
          catch { error('Clipboard access is unavailable. Export the campaign brief instead.'); }
        }, 'quiet'), remove(document.answers, row, 'Remove question')), copied));
    }
  }
  function renderBudget(panel) {
    const total = h('p', {class: 'campaign-budget-total', role: 'status'});
    function updateTotal() {
      let cents = 0n, unknown = 0, priced = 0;
      for (const row of document.budget) {
        const matched = /^(\d+)(?:\.(\d{1,2}))?$/.exec(String(row.unit_cost ?? ''));
        if (!matched || !/^\d+$/.test(String(row.quantity)) || Number(row.quantity) < 1) { unknown++; continue; }
        priced++;
        cents += (BigInt(matched[1]) * 100n + BigInt((matched[2] || '').padEnd(2, '0'))) * BigInt(row.quantity);
      }
      total.textContent = !document.budget.length ? 'Add the first project cost.' : !priced
        ? `No costs priced yet · ${unknown} item${unknown === 1 ? '' : 's'} awaiting prices`
        : `Known cost estimate: $${(cents / 100n).toLocaleString('en-AU')}.${String(cents % 100n).padStart(2, '0')}${unknown ? ' · ' + unknown + ' uncosted item' + (unknown === 1 ? '' : 's') + ' — total incomplete' : ''}`;
    }
    panel.append(h('h3', {}, 'Build a costed project'), h('p', {class: 'muted'}, 'Use AUD and keep the GST basis in the quote reference. Blank costs remain unknown. Estimates without a supplier quote still need checking.'), total,
      button('Add budget item', () => { document.budget.push({item: '', opportunity: '', quantity: 1, unit_cost: null, quote_reference: ''}); changed(); renderEditor(); }, 'quiet'));
    for (const row of document.budget) {
      const item = input('Budget item', 'text', row, 'item', '', {maxLength: 1000});
      const scope = choice('Funding opportunity', scopeChoices(), row, 'opportunity');
      function revised() { for (const answer of document.answers) answer.status = 'draft'; updateTotal(); }
      const quantity = input('Quantity', 'number', row, 'quantity', '', {min: 1, max: 100000, step: 1}, element => { row.quantity = element.value ? Number(element.value) : null; revised(); });
      const price = input('Unit cost (AUD)', 'number', row, 'unit_cost', 'Leave blank while waiting for a price.', {min: 0, step: '.01'}, element => { row.unit_cost = element.value || null; revised(); });
      const quote = input('Quote or estimate reference', 'textarea', row, 'quote_reference', 'Supplier, quote date, GST basis and where to find the quote. Leave blank if no quote is available.', {rows: 2, maxLength: 2000});
      panel.append(h('article', {class: 'campaign-row', 'aria-label': 'Budget item'}, h('div', {class: 'form-grid'}, item.wrap, scope.wrap), h('div', {class: 'form-grid'}, quantity.wrap, price.wrap), quote.wrap,
        remove(document.budget, row, 'Remove budget item')));
    }
    updateTotal();
  }
  function renderActions(panel) {
    panel.append(h('h3', {}, 'The next useful step'), h('p', {class: 'muted'}, 'Turn missing quotes, approvals and unanswered conditions into assigned actions. Dates are entered by you.'),
      button('Add next action', () => { document.actions.push({task: '', owner: '', due: '', status: 'open'}); changed(); renderEditor(); }, 'quiet'));
    for (const row of document.actions) {
      const task = input('Next action', 'text', row, 'task', '', {maxLength: 2000});
      const owner = input('Person responsible', 'text', row, 'owner', 'Leave blank if unassigned.', {maxLength: 200});
      const due = input('Confirmed due date', 'date', row, 'due');
      const state = choice('Action status', [['open', 'To do'], ['done', 'Done']], row, 'status');
      panel.append(h('article', {class: 'campaign-row', 'aria-label': 'Campaign action'}, task.wrap, h('div', {class: 'form-grid'}, owner.wrap, due.wrap, state.wrap), remove(document.actions, row, 'Remove action')));
    }
    async function exportPlan(format) {
      try {
        const plan = await request('/api/community/plan', {data: {title: document.title, actions: document.actions.map(row => ({action: row.task, owner: row.owner, due: row.due, status: row.status === 'done' ? 'done' : 'not_started'}))}});
        download('sinter-campaign-actions.' + (format === 'calendar' ? 'ics' : 'csv'), plan[format], format === 'calendar' ? 'text/calendar' : 'text/csv');
      } catch (problem) { error(problem.message); }
    }
    if (document.actions.length) panel.append(h('div', {class: 'button-row'}, button('Download actions CSV', () => exportPlan('csv'), 'quiet'), button('Download action dates', () => exportPlan('calendar'), 'quiet')));
  }
  function renderSources(panel) {
    panel.append(h('h3', {}, 'Keep the original guidance close'), h('p', {class: 'muted'}, 'Keep source links and the supplied wording used for your checks. Links are not fetched automatically.'),
      button('Add source', () => { document.sources.push({title: '', url: '', notes: ''}); changed(); renderEditor(); }, 'quiet'));
    for (const row of document.sources) {
      const title = input('Source title', 'text', row, 'title', '', {maxLength: 500});
      const url = input('Source link', 'url', row, 'url', '', {maxLength: 2000});
      const notes = input('Source wording and notes', 'textarea', row, 'notes', 'Preserve wording that supports a requirement, deadline or exclusion.', {rows: 5, maxLength: 6000});
      panel.append(h('article', {class: 'campaign-row', 'aria-label': 'Campaign source'}, title.wrap, url.wrap, notes.wrap,
        row.url ? safeLink(row.url, 'Open source') : h('span'), remove(document.sources, row, 'Remove source')));
    }
  }

  const transfers = h('details', {class: 'campaign-transfers'}, h('summary', {}, 'Open, import or back up a campaign'), savedList, imported.wrap,
    h('div', {class: 'button-row'}, button('Export campaign backup', exportBackup, 'quiet'), button('Start a new campaign', () => { if (canReplace()) apply(blank()); }, 'quiet'),
      button('Delete saved campaign', async () => {
        if (!savedId) { error('This campaign has not been saved.'); return; }
        if (!window.confirm('Delete this saved campaign? Export a backup first if you need a copy.')) return;
        try { await request('/api/campaigns/delete', {data: {id: savedId, revision}}); apply(blank()); await refreshShelf(); }
        catch (problem) { error(problem.message); }
      }, 'danger')));
  root.append(h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'FUNDING CAMPAIGNS'), h('h2', {}, 'Keep the whole application together.'),
    h('p', {}, 'Compare opportunities, prepare answers and turn missing details into next actions. Saved locally, with your sources beside the work.')),
    shelf, summary, editor, h('div', {class: 'campaign-save-bar'}, h('div', {class: 'button-row'}, saveButton, prepareButton), status), feedback, transfers, output);
  status.textContent = dirty ? 'Unsaved changes' : savedId ? 'Saved on this computer' : 'Not saved yet';
  renderEditor(); renderSummary(); await refreshShelf();
  return root;
}
