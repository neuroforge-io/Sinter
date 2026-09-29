/** A local, revisioned funding workspace. Every status is entered by a person. */
import {h, field, selectField, button, notice, download, announce, safeLink, check} from './ui.js';
import {request} from './api.js';
import {renderReport} from './reports.js';
import {campaignClarificationDraft, campaignIdentityFromProfile} from './campaign-letter.js';
import {isOpportunityActionable} from './campaign-state.js';
import {campaignDecision} from './campaign-decision.js';

const blank = () => ({schema: 'sinter-campaign/v1', title: '', organisation: '', objective: '',
  signatory: '', sender_role: '', contact_details: '',
  opportunities: [], requirements: [], answers: [], budget: [], actions: [], sources: [], communications: []});
const opportunityStates = [['researching', 'Researching'], ['open', 'Open'], ['upcoming', 'Upcoming'],
  ['clarification', 'Needs clarification'], ['paused', 'Paused'],
  ['not_pursuing', 'Not pursuing this round'], ['submitted', 'Submitted'], ['closed', 'Closed']];
const checkStates = [['unknown', 'Not checked · user-entered'],
  ['clarification', 'Needs clarification · user-entered'],
  ['met', 'User marked met · unverified'], ['not_met', 'User marked not met · unverified']];
const campaignTabs = [['overview', 'Opportunities'], ['answers', 'Application answers'],
  ['budget', 'Budget'], ['actions', 'Next actions'], ['communications', 'Communications'],
  ['sources', 'Sources']];
const countCharacters = value => [...value].length;
const money = value => value == null || value === '' ? 'Not confirmed' : new Intl.NumberFormat('en-AU', {style: 'currency', currency: 'AUD'}).format(Number(value));
function compatibleCampaign(value) {
  const next = structuredClone(value || blank());
  // Campaign v1 documents saved before correspondence logging have no such key.
  if (!Array.isArray(next.communications)) next.communications = [];
  return next;
}
const localDate = () => {
  const now = new Date();
  return [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
};
function opportunityTiming(row) {
  if (row.status === 'closed') return row.deadline ? `Closed · ${row.deadline}` : 'Closed';
  if (row.status === 'submitted') return row.deadline ? `Submitted · ${row.deadline}` : 'Submitted';
  if (row.status === 'not_pursuing') return row.deadline ? `Not pursuing · programme closes ${row.deadline}` : 'Not pursuing this round';
  if (row.deadline && row.deadline < localDate()) return `Date passed · check status (${row.deadline})`;
  return row.deadline ? `Closes ${row.deadline}` : 'Deadline not confirmed';
}
function defaultOpportunityIndex(next) {
  const rows = Array.isArray(next?.opportunities) ? next.opportunities : [];
  for (const state of ['open', 'upcoming', 'researching', 'clarification']) {
    const match = rows.findIndex(row => row.status === state
      && (!row.deadline || row.deadline >= localDate()));
    if (match >= 0) return match;
  }
  return rows.length ? 0 : 0;
}

export async function campaignsPage({setBusy = () => {}, remember = () => {}, seed = {}} = {}) {
  let document = compatibleCampaign(seed.document || blank()), savedId = seed.id || null, revision = seed.revision || null;
  let dirty = Boolean(seed.dirty), selected = Number.isSafeInteger(seed.selected) && seed.selected >= 0 ? seed.selected : 0;
  let tab = campaignTabs.some(([id]) => id === seed.tab) ? seed.tab : 'overview', busy = false;
  const root = h('div', {class: 'campaign-page'}), shelf = h('div', {class: 'campaign-shelf'});
  const feedback = h('div', {'aria-live': 'polite'}), status = h('span', {class: 'campaign-save-state', role: 'status'});
  const summary = h('div', {class: 'campaign-summary'}), editor = h('div'), output = h('div', {id: 'campaign-output', class: 'campaign-output'});
  const decisionCard = h('section', {class: 'campaign-decision-card', 'aria-label': 'Campaign decision and next move'});
  const savedList = h('div', {class: 'campaign-saved-list'});
  let knownCampaigns = [];
  const saveButton = button('Save campaign', () => save(), 'primary');
  const prepareButton = button('Prepare campaign brief', () => prepare(), 'quiet');

  function rememberCampaign() {
    remember('campaigns', {document: structuredClone(document), id: savedId, revision,
      dirty, selected, tab});
  }
  function changed() {
    dirty = true; status.textContent = 'Unsaved changes';
    if (output.children.length && output.dataset.stale !== 'true') {
      output.dataset.stale = 'true'; output.classList.add('campaign-output-stale');
      output.prepend(notice('This brief reflects an earlier campaign version. Re-prepare it before copying, downloading, saving or using it.', 'warning'));
      const report = output.querySelector('.report-area');
      if (report) {
        report.inert = true;
        for (const control of report.querySelectorAll('button, input, textarea, select')) control.disabled = true;
        for (const link of report.querySelectorAll('a')) {
          link.setAttribute('aria-disabled', 'true'); link.tabIndex = -1;
        }
      }
    }
    rememberCampaign();
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
  function apply(next, id = null, rev = null, preferActionable = false) {
    document = compatibleCampaign(next); savedId = id; revision = rev; dirty = false;
    selected = preferActionable ? defaultOpportunityIndex(document) : 0; tab = 'overview';
    status.textContent = id ? 'Saved on this computer' : 'Not saved yet'; output.replaceChildren();
    delete output.dataset.stale; output.classList.remove('campaign-output-stale');
    editor.replaceChildren();
    rememberCampaign();
    renderShelf(); renderEditor(); renderSummary();
  }
  function canReplace() { return !dirty || window.confirm('Replace these unsaved campaign edits? Export a backup or save them first if you need to keep them.'); }
  function renderShelf() {
    savedList.replaceChildren(...knownCampaigns.map(item => h('div', {
      class: 'campaign-saved-item' + (item.id === savedId ? ' is-current' : '')},
      h('div', {}, h('strong', {}, item.title),
        h('small', {}, `${item.id === savedId ? 'Current campaign · ' : ''}Revision ${item.revision}`)),
      button(item.id === savedId ? 'Continue' : 'Open', async () => {
        if (busy || !canReplace()) return;
        lock(true);
        try { const saved = await request('/api/campaigns/' + item.id); apply(saved.document, saved.id || item.id, saved.revision, true); feedback.replaceChildren(notice('Campaign opened. Continue where you left off.', 'success')); }
        catch (problem) { error(problem.message); }
        finally { lock(false); }
      }, 'quiet'))));
    for (const [index, item] of knownCampaigns.entries()) {
      const control = savedList.children[index]?.querySelector('button');
      if (control) control.setAttribute('aria-label', `${item.id === savedId ? 'Continue' : 'Open'} ${item.title}`);
    }
    if (!knownCampaigns.length) savedList.append(h('p', {class: 'fine'}, 'No saved campaigns yet. Start one below and it will be available here next time.'));
  }
  async function refreshShelf() {
    const result = await request('/api/campaigns');
    knownCampaigns = result.campaigns;
    renderShelf();
    return knownCampaigns;
  }
  async function save() {
    if (busy) return;
    lock(true); feedback.replaceChildren();
    try {
      const saved = await request('/api/campaigns/save', {data: {document, id: savedId, revision}});
      document = saved.document; savedId = saved.id; revision = saved.revision; dirty = false;
      renderEditor(); renderSummary();
      rememberCampaign();
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
      output.replaceChildren(renderReport(report));
      delete output.dataset.stale; output.classList.remove('campaign-output-stale');
      output.scrollIntoView({block: 'start'});
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
    const actionable = new Set(document.opportunities
      .filter(row => isOpportunityActionable(row.status))
      .map(row => row.name));
    const pending = document.requirements.filter(row => actionable.has(row.opportunity)
      && (!['met', 'not_met'].includes(row.status)
      || ![row.evidence, row.source_url, row.source_quote, row.checked_at].every(value => value?.trim())));
    const over = document.answers.filter(row => (!row.opportunity || actionable.has(row.opportunity))
      && row.limit && countCharacters(row.text || '') > Number(row.limit));
    const quotes = document.budget.filter(row => (!row.opportunity || actionable.has(row.opportunity))
      && (row.unit_cost == null || row.unit_cost === '' || !row.quote_reference?.trim()));
    const ownersToConfirm = document.actions.filter(row => row.status !== 'done'
      && (!row.owner_confirmed || !String(row.owner || '').trim() || /\bunassigned\b/i.test(row.owner)));
    shelf.replaceChildren(...(document.title ? [h('h3', {}, document.title), h('p', {class: 'fine'}, document.organisation)] : []));
    summary.replaceChildren(...[[pending.length, 'requirements to check'], [over.length, 'answers over their limit'],
      [quotes.length, 'costs needing a quote'], [ownersToConfirm.length, 'owners to confirm']].map(([count, label]) =>
      h('div', {}, h('strong', {}, count), h('span', {}, label))));
    renderDecisionCard();
  }
  function renderDecisionCard() {
    const result = campaignDecision(document, undefined, document.opportunities[selected]?.name || '');
    const state = h('span', {class: 'campaign-decision-state', 'data-state': result.state}, result.label);
    const targetDate = result.action.due ? new Date(result.action.due + 'T12:00:00') : null;
    const targetDatePast = Boolean(result.action.due && result.action.due < localDate());
    const action = h('div', {class: 'campaign-decision-action'},
      h('span', {class: 'eyebrow'}, result.action.source === 'recorded' ? 'NEXT CAMPAIGN ACTION' : 'SUGGESTED ROUTE STEP'),
      h('p', {class: 'campaign-decision-task'}, result.action.task),
      h('p', {class: 'campaign-decision-owner'}, result.action.ownerStatus),
      result.action.due ? h('p', {class: 'campaign-decision-date' + (targetDatePast ? ' is-overdue' : '')},
        'Proposed target: ' + new Intl.DateTimeFormat('en-AU', {dateStyle: 'medium'}).format(targetDate)
          + (targetDatePast ? ' · past — confirm or reset' : '')) : null,
      button('Open next actions', () => {
        tab = 'actions'; rememberCampaign(); renderEditor(); editor.scrollIntoView({block: 'start'});
      }, 'quiet'));
    decisionCard.replaceChildren(h('div', {class: 'campaign-decision-main'},
      h('h3', {}, 'Decision at a glance'), state,
      h('p', {class: 'campaign-decision-campaign'}, document.title || 'New campaign'),
      result.focusOpportunity ? h('p', {class: 'campaign-decision-focus'},
        'Route in focus: ' + result.focusOpportunity) : null,
      h('p', {class: 'campaign-decision-detail'}, result.detail)), action,
      h('div', {class: 'campaign-decision-reopen'},
        h('strong', {}, 'Reopen or progress when'),
        h('p', {}, result.reopenCriteria)),
      h('p', {class: 'campaign-decision-note'}, 'Based only on campaign entries. Source links and assessments are not verified by Sinter; this card does not establish eligibility or permission to submit.'));
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
    const objective = input('What will this campaign make possible?', 'textarea', document, 'objective', 'Describe the project, who benefits and the intended timing. Short labelled paragraphs such as “Purpose:” and “Still to confirm:” make the brief easier to scan.', {rows: 3, maxLength: 12000});
    const signatory = input('Authorised campaign signatory', 'text', document, 'signatory', 'Leave blank until a person has agreed to be named on campaign letters.', {maxLength: 200});
    const senderRole = input('Signatory role', 'text', document, 'sender_role', 'For example, P&C President. Leave blank if not confirmed.', {maxLength: 200});
    const contactDetails = input('Campaign contact details', 'textarea', document, 'contact_details', 'Only include contact details approved for this campaign.', {rows: 3, maxLength: 4096});
    const useProfile = button('Use saved profile details', async () => {
      useProfile.disabled = true;
      try {
        const response = await request('/api/settings');
        const identity = campaignIdentityFromProfile(response.settings || {}, document);
        const copied = Object.keys(identity);
        if (!copied.length) {
          feedback.replaceChildren(notice('No saved profile details fit the blank campaign fields. Add details in Settings, or enter campaign-approved details here.', 'warning'));
          return;
        }
        Object.assign(document, identity);
        changed(); renderEditor();
        feedback.replaceChildren(notice('Copied ' + copied.map(key => ({
          signatory: 'name', sender_role: 'role', organisation: 'organisation', contact_details: 'contact details',
        }[key])).join(', ') + ' from your local profile into blank fields. Review authority and campaign approval before using them in correspondence. Nothing was sent.', 'success'));
      } catch (problem) { error(problem.message); }
      finally { useProfile.disabled = false; }
    }, 'quiet');
    const details = h('details', {class: 'campaign-details', open: detailsOpen}, h('summary', {}, 'Campaign details'), title.wrap, organisation.wrap, objective.wrap,
      h('h4', {}, 'Who may sign campaign letters?'),
      h('p', {class: 'fine'}, 'Use local profile details only when the person is authorised for this campaign. Copied values stay in this campaign until you remove them; Sinter does not send them.'),
      h('div', {class: 'button-row'}, useProfile), signatory.wrap, senderRole.wrap, contactDetails.wrap);
    const tabs = h('div', {class: 'campaign-tabs', role: 'tablist', 'aria-label': 'Campaign sections'});
    const panel = h('section', {class: 'campaign-section', role: 'tabpanel'});
    for (const [id, label] of campaignTabs) {
      const control = button(label, () => { tab = id; rememberCampaign(); renderEditor(); }, 'campaign-tab');
      control.setAttribute('role', 'tab'); control.setAttribute('aria-selected', String(tab === id)); control.tabIndex = tab === id ? 0 : -1;
      control.addEventListener('keydown', event => {
        const at = campaignTabs.findIndex(([key]) => key === tab);
        const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (offset) { event.preventDefault(); tab = campaignTabs[(at + offset + campaignTabs.length) % campaignTabs.length][0]; rememberCampaign(); renderEditor(); editor.querySelector('[aria-selected="true"]').focus(); }
      });
      tabs.append(control);
    }
    panel.setAttribute('aria-label', campaignTabs.find(([id]) => id === tab)[1]);
    if (tab === 'overview') renderOpportunities(panel);
    else if (tab === 'answers') renderAnswers(panel);
    else if (tab === 'budget') renderBudget(panel);
    else if (tab === 'actions') renderActions(panel);
    else if (tab === 'communications') renderCommunications(panel);
    else renderSources(panel);
    editor.replaceChildren(details, tabs, panel);
  }
  function opportunityPicker(change) {
    const pick = selectField('Working on opportunity', document.opportunities.map((row, index) => [String(index), row.name]), String(selected));
    pick.input.addEventListener('change', () => {
      selected = Number(pick.input.value); rememberCampaign(); change(); renderSummary();
    });
    return pick.wrap;
  }
  function renderOpportunities(panel) {
    panel.append(h('div', {class: 'campaign-section-heading'}, h('div', {}, h('h3', {}, 'Funding opportunities in this campaign'),
      h('p', {class: 'muted'}, 'Compare timing, project fit and checks. Closed and paused routes stay visible as historical context.')), button('Add opportunity', addOpportunity, 'quiet')));
    if (!document.opportunities.length) {
      panel.append(h('div', {class: 'campaign-empty'}, h('h4', {}, 'Start with one opportunity'), h('p', {}, 'Add a funder or programme, then record what you know and what needs checking. No eligibility is assumed.'))); return;
    }
    const rail = h('div', {class: 'campaign-opportunities', 'aria-label': 'Funding opportunities'});
    const cards = [];
    document.opportunities.forEach((row, index) => {
      const choose = button('', () => {
        selected = index; rememberCampaign(); renderEditor(); renderSummary();
      }, 'campaign-opportunity');
      choose.setAttribute('aria-pressed', String(index === selected));
      const cardName = h('strong', {}, row.name), cardFunder = h('span', {}, row.funder || 'Funder to confirm');
      const cardAmount = h('small', {}, row.ceiling == null || row.ceiling === '' ? 'Amount to confirm' : 'Up to ' + money(row.ceiling));
      const cardTiming = h('small', {}, opportunityTiming(row));
      choose.append(cardName, cardFunder, cardAmount, cardTiming);
      cards.push({choose, cardName, cardFunder, cardAmount, cardTiming});
      rail.append(choose);
    });
    selected = Math.min(selected, document.opportunities.length - 1);
    const item = document.opportunities[selected], focus = h('section', {class: 'campaign-focus', 'aria-label': 'Selected opportunity'});
    const headerFunder = h('span', {class: 'eyebrow'}), headerName = h('h3', {}), programme = h('div');
    const maximum = h('dd', {}), deadlineLabel = h('dt', {}), deadlineValue = h('dd', {});
    const decisionValue = h('dd', {}), statusValue = h('dd', {}), fitValue = h('p', {});
    function updateOpportunityView() {
      const card = cards[selected];
      if (card) {
        card.cardName.textContent = item.name || 'Untitled opportunity';
        card.cardFunder.textContent = item.funder || 'Funder to confirm';
        card.cardAmount.textContent = item.ceiling == null || item.ceiling === ''
          ? 'Amount to confirm' : 'Up to ' + money(item.ceiling);
        card.cardTiming.textContent = opportunityTiming(item);
      }
      headerFunder.textContent = item.funder || 'FUNDER TO CONFIRM';
      headerName.textContent = item.name || 'Untitled opportunity';
      programme.replaceChildren(item.url ? safeLink(item.url, 'Open programme guidance')
        : h('p', {class: 'fine'}, 'Programme link not added yet.'));
      maximum.textContent = money(item.ceiling);
      deadlineLabel.textContent = item.status === 'closed' || item.status === 'submitted'
        ? (item.status === 'closed' ? 'Closed on' : 'Application deadline') : 'Application closes';
      deadlineValue.textContent = item.deadline || 'Not confirmed';
      decisionValue.textContent = item.decision_window || 'Not confirmed';
      statusValue.textContent = opportunityStates.find(([key]) => key === item.status)?.[1] || 'Researching';
      fitValue.textContent = item.fit || 'Record which project option this opportunity could support and what needs checking.';
    }
    const name = input('Opportunity name', 'text', item, 'name', '', {required: true, maxLength: 200}, () => {
      for (const collection of ['requirements', 'answers', 'budget', 'communications']) {
        for (const row of document[collection]) {
          if (row.opportunity === previousName) row.opportunity = item.name;
        }
      }
      previousName = item.name; updateOpportunityView();
    });
    let previousName = item.name;
    const funder = input('Funder', 'text', item, 'funder', '', {maxLength: 300}, updateOpportunityView);
    const url = input('Programme page', 'url', item, 'url', '', {maxLength: 2000}, updateOpportunityView);
    const deadline = input('Confirmed closing date', 'date', item, 'deadline', 'Leave blank if the date has not been checked.', {}, updateOpportunityView);
    const decision = input('Decision timing', 'text', item, 'decision_window', 'For example, a decision several months after applications close.', {maxLength: 1000}, updateOpportunityView);
    const ceiling = input('Maximum available (AUD)', 'number', item, 'ceiling', 'An amount offered is not an award or project budget.', {min: 0, step: '.01'}, element => { item.ceiling = element.value || null; updateOpportunityView(); });
    const state = choice('Opportunity status', opportunityStates, item, 'status', updateOpportunityView);
    const fit = input('Project fit and timing', 'textarea', item, 'fit', 'Which project option could this support? Record any exclusions or conditions before committing costs.', {rows: 3, maxLength: 6000}, updateOpportunityView);
    const opportunityEditor = h('details', {class: 'campaign-opportunity-editor', open: !item.funder && !item.fit},
      h('summary', {}, 'Edit opportunity details'), h('div', {class: 'form-grid'}, name.wrap, funder.wrap), url.wrap,
      h('div', {class: 'form-grid'}, deadline.wrap, decision.wrap, ceiling.wrap, state.wrap), fit.wrap);
    focus.append(h('header', {class: 'campaign-focus-heading'}, headerFunder, headerName, programme),
      h('dl', {class: 'campaign-opportunity-facts'},
        h('div', {}, h('dt', {}, 'Maximum available'), maximum),
        h('div', {}, deadlineLabel, deadlineValue),
        h('div', {}, h('dt', {}, 'Decision timing'), decisionValue),
        h('div', {}, h('dt', {}, 'Status'), statusValue)),
      h('div', {class: 'campaign-fit'}, h('strong', {}, 'Project fit and timing'), fitValue),
      opportunityEditor);
    updateOpportunityView();
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
        const historical = !isOpportunityActionable(item.status);
        stateLabel.textContent = historical ? 'Historical record · ' : '';
        stateLabel.textContent += row.status === 'met' ? 'User-marked met · unverified'
          : row.status === 'not_met' ? 'User-marked not met · unverified'
            : row.status === 'clarification' ? 'Needs clarification · user-entered'
              : 'Not checked · user-entered';
        // No Sinter source-verification record exists for campaign checks.
        // Populated freeform fields must never look like a verified result.
        stateLabel.dataset.state = 'unverified';
        const note = row.evidence?.trim() || '';
        preview.textContent = note ? note.length > 180 ? note.slice(0, 180) + '… Open for the full note.' : note : 'No evidence note added yet.';
        proof.textContent = `${historical ? 'This route is not active in this campaign; the check is retained for historical reference. ' : ''}Status and source details are user-entered. Sinter has not verified the link, wording, date or assessment.${asserted && !complete ? ' The source record is also incomplete.' : ''}`;
      }
      const rule = input('Requirement', 'text', row, 'rule', '', {maxLength: 4000});
      const status = choice('Requirement status', checkStates, row, 'status', updateProof);
      const reason = input('What the evidence establishes or leaves unclear', 'textarea', row, 'evidence', 'This note is user-entered and is not independently verified by Sinter.', {rows: 2, maxLength: 6000}, updateProof);
      const source = input('Source link (user-entered)', 'url', row, 'source_url', 'Sinter does not open or verify this link.', {maxLength: 2000}, updateProof);
      const quote = input('Source wording (user-entered)', 'textarea', row, 'source_quote', 'Paste the exact wording yourself. Sinter does not check it against the source.', {rows: 3, maxLength: 4000}, updateProof);
      const date = input('Date checked (user-entered)', 'date', row, 'checked_at', 'Sinter cannot verify when this source was checked.', {}, updateProof);
      updateProof();
      const heading = h('summary', {}, h('span', {class: 'campaign-check-title'}, row.rule || 'New requirement'), stateLabel, preview);
      rule.input.addEventListener('input', () => { heading.querySelector('.campaign-check-title').textContent = row.rule || 'New requirement'; });
      requirements.append(h('details', {class: 'campaign-requirement', open: !row.rule}, heading,
        h('article', {class: 'campaign-check-editor', 'aria-label': 'Requirement check'}, rule.wrap, status.wrap, proof, reason.wrap,
        h('details', {open: Boolean(row.source_url || row.source_quote)}, h('summary', {}, 'Supporting source · user-entered, unverified'), source.wrap, quote.wrap, date.wrap),
        remove(document.requirements, row, 'Remove requirement'))));
    }
    if (!document.requirements.some(row => row.opportunity === item.name)) requirements.append(h('p', {class: 'fine'}, 'No requirements checked yet. Start with applicant type, timing and permitted costs.'));
    requirements.append(button('Draft clarification letter', () => {
      const campaignLink = {id: savedId, revision, opportunity: item.name,
        dirty: dirty || !savedId};
      const draft = campaignClarificationDraft(document, item, campaignLink);
      if (draft.openCount > 30) {
        error('This opportunity has more than 30 open checks. Split them across clarification letters before continuing.');
        return;
      }
      delete draft.openCount;
      remember('brief', draft);
      location.hash = 'brief';
    }, 'quiet'));
    focus.append(requirements);
    panel.append(h('div', {class: 'campaign-opportunity-layout'}, rail, focus));
  }
  function renderAnswers(panel) {
    panel.append(h('h3', {}, 'Prepare answers for the funder’s form'), h('p', {class: 'muted'}, 'Keep the exact question and its limit together. Drafts can be saved over the limit; they still need shortening before use.'));
    if (!document.opportunities.length) { panel.append(notice('Add an opportunity first so each answer belongs to the right application.')); return; }
    selected = Math.min(selected, document.opportunities.length - 1);
    const selectedOpportunity = document.opportunities[selected];
    const opportunity = selectedOpportunity.name;
    const active = isOpportunityActionable(selectedOpportunity.status);
    panel.append(opportunityPicker(renderEditor));
    if (!active) {
      panel.append(notice('This route is inactive. Its saved answers are superseded historical drafts, may contain unconfirmed assumptions, and are not for submission. Copying is disabled. Their presence does not show whether anything was submitted; verify the original portal record separately.', 'warning'));
    }
    const addQuestion = button('Add application question', () => {
      document.answers.push({opportunity, label: '', text: '', limit: null, status: 'draft'}); changed(); renderEditor();
    }, 'quiet');
    addQuestion.disabled = !active;
    panel.append(addQuestion);
    for (const row of document.answers.filter(row => row.opportunity === opportunity)) {
      const label = input('Application question', 'textarea', row, 'label', 'Copy the actual wording from the application form.', {rows: 2, maxLength: 300});
      const counter = h('p', {class: 'campaign-character-count', role: 'status'});
      function update() {
        const used = countCharacters(row.text || ''), limit = Number(row.limit);
        counter.textContent = limit > 0 ? `${used} / ${limit} characters${used > limit ? ' · ' + (used - limit) + ' over — shorten before using' : ' · within limit'}` : `${used} characters · confirm the form’s limit`;
        counter.classList.toggle('over-limit', limit > 0 && used > limit);
      }
      const limit = input('Character limit', 'number', row, 'limit', 'Keep this blank if the form does not specify a limit.', {min: 1, max: 20000, step: 1}, element => { row.limit = element.value ? Number(element.value) : null; update(); });
      const answer = input('Draft answer', 'textarea', row, 'text', active ? '' : 'Historical draft · reopen the route to edit.', {rows: 5, maxLength: 20000, readOnly: !active}, () => { row.status = 'draft'; reviewed.input.value = 'draft'; update(); });
      const reviewed = choice('Answer review', [['draft', 'Needs review'], ['reviewed', 'Reviewed by me']], row, 'status');
      const copied = h('p', {class: 'fine', 'aria-live': 'polite'});
      update();
      const copy = button(active ? 'Copy this answer' : 'Copy unavailable · inactive route', async () => {
        try { await navigator.clipboard.writeText(row.text); copied.textContent = row.limit && countCharacters(row.text) > row.limit ? 'Copied as written. Shorten this draft before pasting it into the application.' : 'Answer copied.'; }
        catch { error('Clipboard access is unavailable. Export the campaign brief instead.'); }
      }, 'quiet');
      copy.disabled = !active;
      panel.append(h('article', {class: 'campaign-row', 'aria-label': 'Application answer'}, label.wrap, h('div', {class: 'form-grid'}, limit.wrap, reviewed.wrap), answer.wrap, counter,
        h('div', {class: 'button-row'}, copy, remove(document.answers, row, 'Remove question')), copied));
    }
  }
  function renderBudget(panel) {
    const total = h('p', {class: 'campaign-budget-total', role: 'status'});
    const actionable = new Set(document.opportunities
      .filter(row => isOpportunityActionable(row.status))
      .map(row => row.name));
    function updateTotal() {
      let cents = 0n, unknown = 0, priced = 0;
      const currentRows = document.budget.filter(row => !row.opportunity || actionable.has(row.opportunity));
      for (const row of currentRows) {
        const matched = /^(\d+)(?:\.(\d{1,2}))?$/.exec(String(row.unit_cost ?? ''));
        if (!matched || !/^\d+$/.test(String(row.quantity)) || Number(row.quantity) < 1) { unknown++; continue; }
        priced++;
        cents += (BigInt(matched[1]) * 100n + BigInt((matched[2] || '').padEnd(2, '0'))) * BigInt(row.quantity);
      }
      total.textContent = !currentRows.length ? 'No costs recorded for active opportunities. The current project total is unknown.' : !priced
        ? `No costs priced yet · ${unknown} item${unknown === 1 ? '' : 's'} awaiting prices`
        : `Known cost estimate: $${(cents / 100n).toLocaleString('en-AU')}.${String(cents % 100n).padStart(2, '0')}${unknown ? ' · ' + unknown + ' uncosted item' + (unknown === 1 ? '' : 's') + ' — total incomplete' : ''}`;
    }
    panel.append(h('h3', {}, 'Current project costs'), h('p', {class: 'muted'}, 'Use AUD and keep the GST basis in the quote reference. Blank costs remain unknown. Estimates without a supplier quote still need checking.'), total,
      button('Add budget item', () => { document.budget.push({item: '', opportunity: '', quantity: 1, unit_cost: null, quote_reference: ''}); changed(); renderEditor(); }, 'quiet'));
    function renderBudgetRow(row) {
      const item = input('Budget item', 'text', row, 'item', '', {maxLength: 1000});
      const scope = choice('Funding opportunity', scopeChoices(), row, 'opportunity', () => renderEditor());
      function revised() { for (const answer of document.answers) answer.status = 'draft'; updateTotal(); }
      const quantity = input('Quantity', 'number', row, 'quantity', '', {min: 1, max: 100000, step: 1}, element => { row.quantity = element.value ? Number(element.value) : null; revised(); });
      const price = input('Unit cost (AUD)', 'number', row, 'unit_cost', 'Leave blank while waiting for a price.', {min: 0, step: '.01'}, element => { row.unit_cost = element.value || null; revised(); });
      const quote = input('Quote or estimate reference', 'textarea', row, 'quote_reference', 'Supplier, quote date, GST basis and where to find the quote. Leave blank if no quote is available.', {rows: 2, maxLength: 2000});
      panel.append(h('article', {class: 'campaign-row', 'aria-label': 'Budget item'}, h('div', {class: 'form-grid'}, item.wrap, scope.wrap), h('div', {class: 'form-grid'}, quantity.wrap, price.wrap), quote.wrap,
        remove(document.budget, row, 'Remove budget item')));
    }
    const currentRows = document.budget.filter(row => !row.opportunity || actionable.has(row.opportunity));
    const historicalRows = document.budget.filter(row => row.opportunity && !actionable.has(row.opportunity));
    for (const row of currentRows) renderBudgetRow(row);
    if (historicalRows.length) {
      panel.append(h('h4', {}, 'Historical costs · inactive routes'),
        notice('These items belong to closed, submitted, paused or not-pursued routes. They do not contribute to the current project total.', 'warning'));
      for (const row of historicalRows) renderBudgetRow(row);
    }
    updateTotal();
  }
  function renderActions(panel) {
    panel.append(h('h3', {}, 'The next useful step'), h('p', {class: 'muted'}, 'Turn missing quotes, approvals and unanswered conditions into actions. A name or date is a planning note until the person agrees and the timing is confirmed.'),
      button('Add next action', () => { document.actions.push({task: '', owner: '', owner_confirmed: false, due: '', status: 'open'}); changed(); renderEditor(); }, 'quiet'));
    for (const row of document.actions) {
      const task = input('Next action', 'text', row, 'task', '', {maxLength: 2000});
      const ownerStatus = h('small', {class: 'campaign-action-meta', 'aria-live': 'polite'});
      function updateOwnerStatus() {
        const ownerText = String(row.owner || '').trim();
        ownerStatus.textContent = !ownerText
          ? 'Unassigned — no person is recorded.'
          : /\bunassigned\b/i.test(ownerText)
            ? 'Role suggestion only — a person must accept this action.'
            : row.owner_confirmed
              ? 'User marked accepted — confirm directly with this person.'
              : 'Name recorded — acceptance not recorded.';
        ownerStatus.dataset.state = !ownerText || /\bunassigned\b/i.test(ownerText) ? 'unassigned' : row.owner_confirmed ? 'accepted' : 'confirm';
        acceptance.input.disabled = !ownerText || /\bunassigned\b/i.test(ownerText);
        acceptance.input.checked = row.owner_confirmed === true;
      }
      const owner = input('Person or suggested role', 'text', row, 'owner', 'Enter a person’s name only after they agree. A role name is a suggestion until a person accepts.', {maxLength: 200}, () => { row.owner_confirmed = false; updateOwnerStatus(); });
      owner.wrap.append(ownerStatus);
      const acceptance = check('This person has accepted', row.owner_confirmed === true);
      acceptance.input.disabled = !String(row.owner || '').trim() || /\bunassigned\b/i.test(row.owner);
      acceptance.input.setAttribute('aria-label', 'This person has accepted this action');
      acceptance.input.addEventListener('change', () => {
        row.owner_confirmed = acceptance.input.checked; updateOwnerStatus(); changed();
      });
      owner.wrap.append(acceptance.wrap, h('small', {class: 'campaign-action-meta'}, 'This is your record; Sinter cannot verify agreement.'));

      const dateStatus = h('p', {class: 'campaign-action-date-status', role: 'status'});
      function updateDateStatus() {
        if (row.status === 'done') {
          dateStatus.textContent = row.due ? 'Completed — proposed target kept for reference.' : 'Completed — no target date was recorded.';
          dateStatus.dataset.state = 'done';
        } else if (!row.due) {
          dateStatus.textContent = 'No target date set. Confirm timing with the owner.';
          dateStatus.dataset.state = 'unset';
        } else if (row.due < localDate()) {
          dateStatus.textContent = `Past proposed target (${row.due}). Confirm whether this is still needed and agree a new date.`;
          dateStatus.dataset.state = 'overdue';
        } else {
          dateStatus.textContent = `Proposed target: ${row.due}. Confirm timing with the owner.`;
          dateStatus.dataset.state = 'target';
        }
      }
      const due = input('Proposed target date', 'date', row, 'due', 'Planning target only, not a confirmed due date. Agree the timing with the owner.', {}, updateDateStatus);
      due.wrap.append(dateStatus);
      const state = choice('Action status', [['open', 'To do'], ['done', 'Done']], row, 'status', updateDateStatus);
      panel.append(h('article', {class: 'campaign-row campaign-action', 'aria-label': 'Campaign action'}, task.wrap, h('div', {class: 'form-grid'}, owner.wrap, due.wrap, state.wrap), remove(document.actions, row, 'Remove action')));
      updateOwnerStatus(); updateDateStatus();
    }
    async function exportPlan(format) {
      try {
        const plan = await request('/api/community/plan', {data: {title: document.title, actions: document.actions.map(row => ({action: row.task, owner: row.owner_confirmed ? `${row.owner} (user-marked accepted; verify directly)` : row.owner ? `${row.owner} (acceptance not recorded)` : 'Unassigned', due: row.due, status: row.status === 'done' ? 'done' : 'not_started'}))}});
        download('sinter-campaign-actions.' + (format === 'calendar' ? 'ics' : 'csv'), plan[format], format === 'calendar' ? 'text/calendar' : 'text/csv');
      } catch (problem) { error(problem.message); }
    }
    if (document.actions.length) panel.append(h('div', {class: 'button-row'}, button('Download actions CSV', () => exportPlan('csv'), 'quiet'), button('Download action dates', () => exportPlan('calendar'), 'quiet')));
  }
  function renderCommunications(panel) {
    const previouslyOpen = [...editor.querySelectorAll('.campaign-communication > details')]
      .map(details => details.open);
    panel.append(h('h3', {}, 'Record correspondence and drafts'),
      h('p', {class: 'muted'}, 'Keep incoming messages, outgoing drafts and sent records with their dates and evidence links. These are your entries: Sinter does not access email, open or verify links, send messages, or confirm that a message was sent or received.'),
      h('p', {class: 'fine'}, 'Only keep message details the campaign needs. Drafts are clearly marked as not sent.'),
      button('Add communication', () => {
        document.communications.push({opportunity: '', date: '', direction: 'outgoing', status: 'draft',
          channel: 'email', counterparty: '', subject: '', content: '', evidence_links: []});
        changed(); tab = 'communications'; renderEditor();
      }, 'quiet'));
    if (!document.communications.length) {
      panel.append(h('div', {class: 'campaign-empty'}, h('h4', {}, 'No communications recorded yet'),
        h('p', {}, 'Add a received message or an outgoing draft when there is something to track. Nothing is sent from this page.')));
      return;
    }
    const directionOptions = [['incoming', 'Incoming'], ['outgoing', 'Outgoing']];
    const channelOptions = [['email', 'Email'], ['letter', 'Letter'], ['phone', 'Phone call'],
      ['meeting', 'Meeting'], ['portal', 'Application portal'], ['other', 'Other']];
    for (const [index, row] of document.communications.entries()) {
      const evidenceLinks = Array.isArray(row.evidence_links) ? row.evidence_links : (row.evidence_links = []);
      const state = h('span', {class: 'campaign-communication-state', 'data-state': row.status},
        row.status === 'draft' ? 'Draft · not sent · user-entered'
          : row.status === 'sent' ? 'Recorded as sent · user-entered, unverified'
            : 'Recorded as received · user-entered, unverified');
      const summaryTitle = h('strong', {}, row.subject || 'Untitled communication');
      const summaryDetails = h('span', {class: 'fine'});
      function updateSummary() {
        const channelLabel = channelOptions.find(([value]) => value === row.channel)?.[1]
          || 'Other';
        summaryDetails.textContent = [row.date || 'Date not recorded',
          row.direction === 'incoming' ? 'Incoming' : 'Outgoing', channelLabel,
          row.counterparty].filter(Boolean).join(' · ');
      }
      const summary = h('summary', {}, summaryTitle, state, summaryDetails);
      const direction = choice('Direction', directionOptions, row, 'direction', () => {
        row.status = row.direction === 'incoming' ? 'received'
          : row.status === 'received' ? 'draft' : row.status;
        state.textContent = row.status === 'draft' ? 'Draft · not sent · user-entered'
          : row.status === 'sent' ? 'Recorded as sent · user-entered, unverified'
            : 'Recorded as received · user-entered, unverified';
        state.dataset.state = row.status;
        updateSummary();
        changed(); renderEditor();
      });
      const statusChoices = row.direction === 'incoming'
        ? [['received', 'Received · recorded by you']]
        : [['draft', 'Draft · not sent'], ['sent', 'Sent · recorded by you']];
      const statusField = choice('Communication status', statusChoices, row, 'status', () => {
        state.textContent = row.status === 'draft' ? 'Draft · not sent · user-entered'
          : row.status === 'sent' ? 'Recorded as sent · user-entered, unverified'
            : 'Recorded as received · user-entered, unverified';
        state.dataset.state = row.status;
        updateSummary();
      });
      const channel = choice('Channel', channelOptions, row, 'channel', updateSummary);
      const date = input('Communication date (user-entered)', 'date', row, 'date',
        'Enter the date shown by your records. For a draft, leave blank unless you have a separate date to record. Sinter does not infer or verify it.', {}, updateSummary);
      const counterparty = input('Person or organisation', 'text', row, 'counterparty',
        'Who the message was with. This is a user-entered record.', {maxLength: 300}, updateSummary);
      const subject = input('Subject or short title', 'text', row, 'subject', '', {maxLength: 1000}, () => {
        summaryTitle.textContent = row.subject || 'Untitled communication';
        updateSummary();
      });
      const content = input('Message text or summary', 'textarea', row, 'content',
        'Paste the relevant message or a useful summary. Stored with this campaign on this computer; include only details the campaign needs.',
        {rows: 6, maxLength: 20000});
      const evidence = h('div', {class: 'campaign-communication-evidence'},
        h('h4', {}, 'Evidence links · user-entered, unverified'),
        h('p', {class: 'fine'}, 'For example, a link to a message, attachment or portal record. Sinter does not open or check it.'),
        button('Add evidence link', () => {
          if (evidenceLinks.length >= 10) { error('A communication can have up to 10 evidence links.'); return; }
          evidenceLinks.push({title: '', url: '', notes: ''}); changed(); renderEditor();
        }, 'quiet'));
      for (const link of evidenceLinks) {
        const linkTitle = input('Evidence title', 'text', link, 'title',
          'For example, “Email from programme officer” or “Application portal receipt”.', {maxLength: 500});
        const linkUrl = input('Evidence link', 'url', link, 'url',
          'HTTP or HTTPS link only. Links are not opened or verified by Sinter.', {maxLength: 4000});
        const linkNotes = input('Evidence note', 'textarea', link, 'notes', '',
          {rows: 2, maxLength: 2000});
        evidence.append(h('article', {class: 'campaign-row', 'aria-label': 'Communication evidence link'},
          linkTitle.wrap, linkUrl.wrap, linkNotes.wrap,
          link.url ? safeLink(link.url, 'Open evidence link') : null,
          remove(evidenceLinks, link, 'Remove evidence link')));
      }
      const opportunity = choice('Related opportunity', scopeChoices(), row, 'opportunity');
      panel.append(h('article', {class: 'campaign-row campaign-communication', 'aria-label': 'Campaign communication'},
        h('details', {open: previouslyOpen[index] ?? (!row.subject && !row.content)}, summary,
          h('div', {class: 'form-grid'}, direction.wrap, statusField.wrap, channel.wrap, date.wrap),
          h('div', {class: 'form-grid'}, counterparty.wrap, subject.wrap, opportunity.wrap),
          content.wrap, evidence, h('p', {class: 'fine'}, 'Status, date, message details and links remain user-entered and unverified.'),
          remove(document.communications, row, 'Remove communication'))));
      updateSummary();
    }
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

  function newCampaign() { if (canReplace()) { apply(blank()); feedback.replaceChildren(); } }
  const savedPanel = h('section', {class: 'campaign-saved-panel', 'aria-label': 'Saved campaigns'},
    h('div', {class: 'campaign-section-heading'}, h('div', {}, h('h3', {}, 'Your campaigns'),
      h('p', {class: 'muted'}, 'Your latest saved campaign opens automatically. You can switch campaigns here at any time.')),
      button('Start a new campaign', newCampaign, 'quiet')), savedList);
  const transfers = h('details', {class: 'campaign-transfers'}, h('summary', {}, 'Import or back up a campaign'), imported.wrap,
    h('div', {class: 'button-row'}, button('Export campaign backup', exportBackup, 'quiet'),
      button('Delete saved campaign', async () => {
        if (!savedId) { error('This campaign has not been saved.'); return; }
        if (!window.confirm('Delete this saved campaign? Export a backup first if you need a copy.')) return;
        try { await request('/api/campaigns/delete', {data: {id: savedId, revision}}); apply(blank()); await refreshShelf(); }
        catch (problem) { error(problem.message); }
      }, 'danger')));
  root.append(h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'FUNDING CAMPAIGNS'), h('h2', {}, 'Keep the whole application together.'),
    h('p', {}, 'Compare opportunities, prepare answers and turn missing details into next actions. Saved locally, with your sources beside the work.')),
    decisionCard, savedPanel, shelf, summary, editor, h('div', {class: 'campaign-save-bar'}, h('div', {class: 'button-row'}, saveButton, prepareButton), status), feedback, transfers, output);
  status.textContent = dirty ? 'Unsaved changes' : savedId ? 'Saved on this computer' : 'Not saved yet';
  renderEditor(); renderSummary();
  const existing = await refreshShelf();
  if (!seed.document && !seed.id && !seed.dirty && existing.length) {
    try {
      const latest = await request('/api/campaigns/' + existing[0].id);
      apply(latest.document, latest.id || existing[0].id, latest.revision, true);
      feedback.replaceChildren(notice('Most recently updated campaign opened. Choose a different one above or start a new campaign.', 'success'));
    } catch (problem) { error('Could not reopen your latest campaign. ' + problem.message); }
  }
  return root;
}
