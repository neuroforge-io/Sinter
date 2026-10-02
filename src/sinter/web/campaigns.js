/** A local, revisioned funding workspace. Every status is entered by a person. */
import {h, field, selectField, button, notice, download, announce, safeLink, check} from './ui.js';
import {request} from './api.js';
import {renderReport} from './reports.js';
import {campaignClarificationDraft, campaignIdentityFromProfile} from './campaign-letter.js';
import {defaultCampaignOpportunityIndex, isCampaignActionCurrent, isCampaignActionOpen,
  isCampaignActionScopeConfirmed, isOpportunityActionable,
  applicationAnswerAvailability} from './campaign-state.js';
import {applicationWindowGaps, campaignDecision, CAMPAIGN_DECISION_NOTE} from './campaign-decision.js';
import {campaignActionOwnerState, normalizeCampaignActionOwners} from './campaign-owner.js';
import {campaignSourceSnapshotGuidance,
  campaignSourceSnapshotIssue} from './campaign-source-state.js';
import {campaignActionRowsForCalendar, campaignActionRowsForPlan,
  normalizeCampaignActionScopes} from './campaign-plan.js';
import {gardenGuide, GARDEN_PRACTICE} from './garden-practice.js';
import {campaignCommunicationView, COMMUNICATION_ORDERS}
  from './campaign-communication-view.js';
import {campaignCapacity, CAMPAIGN_TEXT_LIMIT, CAMPAIGN_BYTE_LIMIT}
  from './campaign-capacity.js';
import {campaignSourceOptions, matchingCampaignSources}
  from './campaign-source-options.js';
import {selectRequirementSource} from './campaign-requirement-source.js';
import {selectWindowSource} from './campaign-window-source.js';
import {campaignBackupControls, resetCampaignBackupControls} from './campaign-backup.js';
import {CEILING_CURRENCY_OPTIONS, campaignCeilingCurrency,
  campaignFundingAmount, campaignCurrencyComparisonNote} from './campaign-currency.js';
import {createFundingSummaryState, fundingTrackingEditor,
  fundingReferencesSource, renderFundingSummary} from './campaign-funding.js';
import {CAMPAIGN_OPPORTUNITY_LIMIT, OPPORTUNITY_PAGE_SIZE,
  canAddCampaignOpportunity, campaignOpportunityView} from './campaign-opportunity-view.js';

import {campaignBudgetRowState, campaignQuotedBudget, QUOTED_BUDGET_NOTE}
  from './campaign-budget.js';

const blank = () => ({schema: 'sinter-campaign/v1', title: '', organisation: '', objective: '',
  signatory: '', sender_role: '', contact_details: '',
  opportunities: [], requirements: [], answers: [], budget: [], actions: [], sources: [],
  communications: [], assets: []});
const linkedSourceMatchesCheck = (row, sources) => {
  if (!row?.source_id) return true;
  const linked = sources.find(source => source?.id === row.source_id);
  return Boolean(linked && row.source_url === linked.url
    && row.checked_at === linked.checked_at);
};
const opportunityStates = [['researching', 'Researching'], ['open', 'Open'], ['upcoming', 'Upcoming'],
  ['clarification', 'Needs clarification'], ['paused', 'Paused'],
  ['not_pursuing', 'Not pursuing this round'], ['submitted', 'Submitted'], ['closed', 'Closed']];
const opportunityTypes = [['unknown', 'Not classified'], ['cash_grant', 'Cash grant'],
  ['matched_voucher', 'Matched voucher'], ['tax_incentive', 'Tax incentive or rebate'],
  ['equity', 'Equity investment'], ['non_cash_support', 'Non-cash programme or support'],
  ['other', 'Other']];
const applicationWindows = [['unknown', 'Not checked'], ['fixed', 'Fixed closing date'],
  ['rolling', 'Rolling / accepts applications year-round']];
const applicationModes = [['unknown', 'Not confirmed'], ['required', 'Formal application required'],
  ['not_required', 'No formal application recorded']];
const assetKinds = [['product', 'Product'], ['service', 'Service'], ['research', 'Research system'],
  ['prototype', 'Prototype'], ['brand', 'Brand or name'], ['dataset', 'Dataset'],
  ['model', 'Model or adapter'], ['other', 'Other']];
const assetStages = [['unknown', 'Not recorded'], ['concept', 'Concept'], ['prototype', 'Prototype'],
  ['pilot', 'Pilot'], ['released', 'Released'], ['retired', 'Retired']];
const contributorStatuses = [['unknown', 'Not checked · user-entered'],
  ['contributors_identified', 'Contributors identified · user-entered'],
  ['records_to_check', 'Records still to check · user-entered'],
  ['evidence_recorded', 'Reference recorded · unverified']];
const rightsStatuses = [['unknown', 'Not checked · user-entered'],
  ['records_to_check', 'Records still to check · user-entered'],
  ['public_license_stated', 'Public licence stated · company title not established'],
  ['evidence_recorded', 'Reference recorded · unverified']];
const disclosureStatuses = [['unknown', 'Not checked · user-entered'],
  ['records_to_check', 'Records still to check · user-entered'],
  ['date_recorded', 'Date recorded · unverified']];
const priorArtStatuses = [['not_started', 'Not started · user-entered'],
  ['leads_recorded', 'Search leads recorded · unverified'],
  ['preliminary_screen', 'Preliminary screen recorded · not a legal conclusion'],
  ['specialist_review_pending', 'Specialist review pending · user-entered']];
const assetReferenceKinds = [['public_claim', 'Public description'], ['prior_art', 'Prior-art lead'],
  ['rights', 'Rights record'], ['contributors', 'Contributor record'],
  ['disclosure', 'Disclosure record'], ['other', 'Other evidence']];
const checkStates = [['unknown', 'Not checked · user-entered'],
  ['clarification', 'Needs clarification · user-entered'],
  ['met', 'User marked met · unverified'], ['not_met', 'User marked not met · unverified']];
const campaignTabs = [['overview', 'Opportunities'], ['assets', 'Products & IP'],
  ['answers', 'Application answers'],
  ['budget', 'Budget'], ['actions', 'Next actions'], ['communications', 'Communications'],
  ['sources', 'Sources']];
const countCharacters = value => [...value].length;
const newRecordId = () => {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
};
const routeAmountLabel = campaignFundingAmount;
function compatibleCampaign(value) {
  const next = structuredClone(value || blank());
  // Campaign v1 documents saved before correspondence logging have no such key.
  if (!Array.isArray(next.communications)) next.communications = [];
  for (const row of next.communications) {
    if (!Array.isArray(row.evidence_links)) row.evidence_links = [];
    row.evidence_links = row.evidence_links.map(link => ({
      ...link, source_id: link.source_id || '', checked_at: link.checked_at || '',
    }));
  }
  // Older v1 campaign backups predate the product and IP research register.
  if (!Array.isArray(next.assets)) next.assets = [];
  if (!Array.isArray(next.sources)) next.sources = [];
  next.sources = next.sources.map(row => ({...row,
    id: /^[0-9a-f]{32}$/.test(row.id || '') ? row.id : newRecordId(),
    checked_at: row.checked_at || '',
  }));
  next.assets = next.assets.map(row => ({...row,
    id: /^[0-9a-f]{32}$/.test(row.id || '') ? row.id : newRecordId(),
    references: (Array.isArray(row.references) ? row.references : []).map(reference => ({
      ...reference, source_id: reference.source_id || '',
      excerpt: reference.excerpt || '', checked_at: reference.checked_at || '',
    })),
  }));
  for (const row of next.opportunities || []) {
    row.route_type ??= 'unknown';
    row.application_mode ??= 'unknown';
    row.applicant ??= '';
    row.applicant_confirmed ??= false;
    if (!row.application_window) row.application_window = row.deadline ? 'fixed' : 'unknown';
    row.window_source_id ??= '';
    row.window_source_url ??= '';
    row.window_source_quote ??= '';
    row.window_checked_at ??= '';
  }
  for (const row of next.requirements || []) row.source_id ??= '';
  next.actions = normalizeCampaignActionOwners(
    normalizeCampaignActionScopes(next.actions));
  return next;
}
const localDate = () => {
  const now = new Date();
  return [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
};
const displayDate = value => {
  if (!value) return 'Not confirmed';
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? value
    : new Intl.DateTimeFormat('en-AU', {day: 'numeric', month: 'short', year: 'numeric'}).format(parsed);
};
export function opportunityTiming(row) {
  if (row.status === 'closed') return row.deadline
    ? `Recorded closed · closing date ${displayDate(row.deadline)}` : 'Recorded closed';
  if (row.status === 'submitted') return row.deadline
    ? `Submitted · recorded deadline ${displayDate(row.deadline)}` : 'Recorded submitted';
  if (row.status === 'not_pursuing') return row.deadline
    ? `Not pursuing · recorded programme closing date ${displayDate(row.deadline)}`
    : 'Not pursuing this round';
  const kind = row.application_window || (row.deadline ? 'fixed' : 'unknown');
  if (kind === 'rolling') return row.window_checked_at
    ? `Rolling · checked ${displayDate(row.window_checked_at)}` : 'Rolling · source check needed';
  if (kind === 'fixed') {
    if (row.deadline && row.deadline < localDate()) {
      return `Recorded closing date passed · confirm current status (${row.deadline})`;
    }
    return row.deadline ? `Recorded closing date · ${displayDate(row.deadline)}`
      : 'Closing date needed';
  }
  return row.deadline
    ? `Recorded closing date · ${displayDate(row.deadline)} · Application window not verified`
    : 'Application window not verified';
}
export function hasUnverifiedRecordedDeadline(row) {
  const kind = row.application_window || (row.deadline ? 'fixed' : 'unknown');
  return Boolean(row.deadline) && kind === 'unknown'
    && row.status !== 'closed' && row.status !== 'submitted';
}
export async function campaignsPage({setBusy = () => {}, remember = () => {}, seed = {}, onOpenGarden} = {}) {
  let document = compatibleCampaign(seed.document || blank()), savedId = seed.id || null, revision = seed.revision || null;
  let dirty = Boolean(seed.dirty), selected = Number.isSafeInteger(seed.selected) && seed.selected >= 0 ? seed.selected : 0;
  let practice = seed.practice || null;
  const practiceGuide = onOpenGarden ? gardenGuide('campaigns', onOpenGarden) : h('div');
  practiceGuide.hidden = practice !== GARDEN_PRACTICE;
  let tab = campaignTabs.some(([id]) => id === seed.tab) ? seed.tab : 'overview', busy = false;
  let expandedActionRows = null;
  let budgetOpenState = new WeakMap();
  const renderedBudgetRows = new WeakMap();
  // These choices belong to the in-memory editor, never the saved campaign.
  if (Array.isArray(seed.budgetDisclosures)
      && seed.budgetDisclosures.length === document.budget.length) {
    document.budget.forEach((row, index) => {
      if (typeof seed.budgetDisclosures[index] === 'boolean') {
        budgetOpenState.set(row, seed.budgetDisclosures[index]);
      }
    });
  }
  let pendingBudgetFocus = null;
  let toolbarObserver = null, toolbarObserverFrame = null;
  let sourceQuery = typeof seed.sourceQuery === 'string' ? seed.sourceQuery : '';
  let opportunityQuery = typeof seed.opportunityQuery === 'string' ? seed.opportunityQuery : '';
  let opportunityStatus = opportunityStates.some(([key]) => key === seed.opportunityStatus)
    ? seed.opportunityStatus : 'all';
  let opportunityPage = Number.isSafeInteger(seed.opportunityPage) ? Math.max(0, seed.opportunityPage) : 0;
  let assetQuery = typeof seed.assetQuery === 'string' ? seed.assetQuery : '';
  let communicationQuery = typeof seed.communicationQuery === 'string' ? seed.communicationQuery : '';
  let communicationRoute = typeof seed.communicationRoute === 'string' ? seed.communicationRoute : null;
  let communicationOrder = COMMUNICATION_ORDERS.some(([value]) => value === seed.communicationOrder)
    ? seed.communicationOrder : 'record';
  let communicationOpenState = new WeakMap();
  let pendingAssetOpenId = '';
  let pendingFocus = null;
  let pendingActionFocus = null;
  const root = h('div', {class: 'campaign-page'}), shelf = h('div', {class: 'campaign-shelf'});
  const feedback = h('div', {class: 'campaign-save-feedback', 'aria-live': 'polite', tabindex: 0}), status = h('span', {class: 'campaign-save-state', role: 'status'});
  const summary = h('div', {class: 'campaign-summary'}), editor = h('div', {class: 'campaign-editor'}), output = h('div', {id: 'campaign-output', class: 'campaign-output'});
  const sectionNavigation = h('nav', {class: 'campaign-section-navigation non-print', 'aria-label': 'Campaign sections navigation'});
  const capacity = h('p', {class: 'fine', 'aria-label': 'Campaign capacity'});
  const decisionCard = h('section', {class: 'campaign-decision-card', 'aria-label': 'Campaign decision and next move'});
  const savedList = h('div', {class: 'campaign-saved-list'});
  let knownCampaigns = [];
  const backupControls = campaignBackupControls(() => document);
  const saveButton = button('Save campaign', () => save(), 'primary');
  const prepareButton = button('Prepare campaign brief', () => prepare(), 'quiet');
  const newButton = button('Start a new campaign', newCampaign, 'quiet');
  const fundingState = createFundingSummaryState();
  let fundingProblem = '';
  let renderedFundingSummary = null, renderedFundingProblem = '';
  const fundingStatus = h('p', {class: 'fine', role: 'status', 'aria-live': 'polite'});
  const fundingContent = h('div', {class: 'campaign-funding-content'});
  const fundingButton = button('Update funding totals', updateFundingTotals, 'quiet');
  const fundingPanel = h('section', {class: 'campaign-funding-summary',
    'aria-label': 'Current campaign funding totals'},
    h('div', {class: 'campaign-section-heading'}, h('div', {}, h('h3', {}, 'Funding totals'),
      h('p', {class: 'muted'}, 'One calculated view of the current campaign, including unsaved edits. Records remain on this computer; this action does not contact a funder.')),
    fundingButton), fundingStatus, fundingContent);

  function renderFunding() {
    fundingButton.disabled = busy || fundingState.pending || fundingState.closed;
    fundingPanel.dataset.stale = String(fundingState.stale);
    fundingStatus.textContent = fundingState.stale
      ? fundingState.pending
        ? 'Earlier campaign version · totals are stale. Wait for the current request to finish, then update from these edits.'
        : 'Earlier campaign version · totals are stale. Update funding totals before using them.'
      : fundingState.pending ? 'Updating from the current campaign records…'
        : fundingState.summary ? 'Calculated from the current recorded data. Eligibility and income are not independently verified.'
          : 'Totals have not been calculated. Open Funding tracking under a route to record its round, statuses, amounts and evidence, then update totals.';
    if (renderedFundingSummary !== fundingState.summary || renderedFundingProblem !== fundingProblem) {
      fundingContent.replaceChildren(...[
        fundingProblem ? notice(fundingProblem, 'error') : null,
        fundingState.summary ? renderFundingSummary(fundingState.summary) : null,
      ].filter(Boolean));
      renderedFundingSummary = fundingState.summary;
      renderedFundingProblem = fundingProblem;
    }
  }
  async function updateFundingTotals() {
    if (busy || fundingState.closed) return;
    const token = fundingState.begin();
    fundingProblem = ''; lock(true); renderFunding();
    try {
      const result = await request('/api/campaigns/funding-summary', {
        data: {document: structuredClone(document)},
      });
      if (fundingState.accept(token, result)) {
        renderFunding(); announce('Funding totals updated from the current recorded campaign.');
      }
    } catch (problem) {
      if (fundingState.current(token)) { fundingProblem = problem.message; renderFunding(); }
    } finally {
      if (fundingState.finish(token)) { lock(false); renderFunding(); }
    }
  }

  function rememberCampaign() {
    remember('campaigns', {document: structuredClone(document), id: savedId, revision,
      dirty, selected, tab, sourceQuery, assetQuery, communicationQuery,
      opportunityQuery, opportunityStatus, opportunityPage,
      communicationRoute, communicationOrder, practice,
      budgetDisclosures: document.budget.map(row => budgetOpenState.get(row) ?? null)});
  }
  function captureBudgetDisclosures() {
    let updated = false;
    const currentRows = new Set(document.budget);
    for (const details of editor.querySelectorAll('.campaign-budget-row > details')) {
      const row = renderedBudgetRows.get(details);
      // Old campaign controls must not attach their state to replacement rows.
      if (currentRows.has(row) && budgetOpenState.get(row) !== details.open) {
        budgetOpenState.set(row, details.open); updated = true;
      }
    }
    return updated;
  }
  function setBudgetDisclosure(row, open) {
    budgetOpenState.set(row, open);
    // Match a deliberate open to its live native state before any pre-capture.
    for (const details of editor.querySelectorAll('.campaign-budget-row > details')) {
      if (renderedBudgetRows.get(details) === row) details.open = open;
    }
  }
  // A native toggle event may still be queued when the container is removed.
  root.dispose = () => {
    fundingState.close();
    toolbarObserver?.disconnect();
    if (toolbarObserverFrame !== null) cancelAnimationFrame(toolbarObserverFrame);
    captureBudgetDisclosures();
    rememberCampaign();
  };
  function changed() {
    fundingState.edited(); fundingProblem = ''; renderFunding();
    dirty = true; status.textContent = 'Unsaved changes';
    feedback.querySelector('.notice.success')?.remove();
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
    entry.input.dataset.campaignField = key;
    entry.input.addEventListener('input', () => { row[key] = entry.input.value; callback(entry.input); changed(); });
    return entry;
  }
  function choice(label, choices, row, key, callback = () => {}) {
    const entry = selectField(label, choices, row[key]);
    entry.input.dataset.campaignField = key;
    entry.input.addEventListener('change', () => { row[key] = entry.input.value; changed(); callback(); });
    return entry;
  }
  let sourcePickerSequence = 0;
  function campaignSourcePicker(label, selectedId, onSelect) {
    const options = campaignSourceOptions(document.sources);
    const selectedOption = options.find(option => option.source.id === selectedId);
    const listId = `campaign-source-options-${++sourcePickerSequence}`;
    const entry = field(label, 'search', selectedOption?.label || '',
      'Search by title or website, then use a Link source button. Typing does not change the link. Links stay unverified.', {
        autocomplete: 'off', placeholder: 'Search saved sources…',
      });
    entry.input.setAttribute('aria-controls', listId);
    const status = h('small', {class: 'campaign-source-picker-status', role: 'status'},
      selectedOption ? `Linked to ${selectedOption.source.title} · user-entered, unverified.`
        : options.length ? 'No campaign source linked.'
          : 'Add a source in the Sources tab first.');
    const matchStatus = h('small', {class: 'campaign-source-picker-status', role: 'status'});
    const matches = h('div', {class: 'campaign-source-matches', id: listId,
      role: 'group', 'aria-label': 'Matching saved campaign sources', hidden: true});
    function closeMatches() { matches.hidden = true; matchStatus.textContent = ''; }
    function selectSource(option) {
      entry.input.value = option.label;
      status.textContent = `Linked to ${option.source.title} · user-entered, unverified.`;
      clear.hidden = false; closeMatches();
      onSelect(option.source); changed();
    }
    function showMatches() {
      const found = matchingCampaignSources(options, entry.input.value);
      matches.replaceChildren(...found.matches.map(option => {
        const control = button('Link source: ' + option.label, () => selectSource(option), 'quiet');
        control.dataset.campaignSourceId = option.source.id;
        return h('div', {class: 'campaign-source-match'}, control,
          h('small', {class: 'fine'}, option.source.url || 'No saved source URL.'),
          h('small', {class: 'fine'}, 'Source checked date (user-entered): '
            + (option.source.checked_at || 'Not recorded')));
      }));
      matches.hidden = !found.matches.length;
      matchStatus.textContent = !options.length ? 'Add a source in the Sources tab first.'
        : !found.total ? 'No matching saved sources. Try a title or website.'
          : `${found.total} matching saved source${found.total === 1 ? '' : 's'}`
            + (found.total > found.matches.length
              ? ` · showing ${found.matches.length}. Refine the search to find another source.`
              : '. Choose a Link source button.');
    }
    const clear = button('Clear link', () => {
      entry.input.value = '';
      status.textContent = options.length ? 'No campaign source linked.'
        : 'Add a source in the Sources tab first.';
      clear.hidden = true; closeMatches();
      onSelect(null); changed();
      if (entry.input.isConnected) entry.input.focus();
    }, 'quiet');
    clear.hidden = !selectedOption;
    entry.input.addEventListener('input', showMatches);
    entry.input.addEventListener('focus', showMatches);
    entry.input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') {
        showMatches(); const first = matches.querySelector('button');
        if (first) { event.preventDefault(); first.focus(); }
      }
      if (event.key === 'Enter') { event.preventDefault(); showMatches(); }
      if (event.key === 'Escape') { event.preventDefault(); closeMatches(); }
    });
    matches.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault(); entry.input.focus(); closeMatches();
      }
    });
    return {input: entry.input, wrap: h('div', {class: 'campaign-source-picker'},
      entry.wrap, status, clear, matchStatus, matches)};
  }
  function remove(rows, item, label, onRemove = null) {
    return button(label, () => {
      if (onRemove) onRemove();
      rows.splice(rows.indexOf(item), 1); changed(); renderEditor();
    }, 'quiet');
  }
  function lock(value) { busy = value; setBusy(value); saveButton.disabled = value; prepareButton.disabled = value; newButton.disabled = value; fundingButton.disabled = value || fundingState.pending || fundingState.closed; editor.inert = value; sectionNavigation.inert = value; transfers.inert = value; }
  function apply(next, id = null, rev = null, preferActionable = false) {
    const resumeCurrentCampaign = Boolean(id && id === savedId);
    const previousTab = tab;
    const previousSelection = selected;
    const previousOpportunityName = document.opportunities?.[previousSelection]?.name || '';
    const previousSourceQuery = sourceQuery;
    const previousAssetQuery = assetQuery;
    const previousCommunicationView = {query: communicationQuery,
      route: communicationRoute, order: communicationOrder};
    practice = null; practiceGuide.hidden = true;
    document = compatibleCampaign(next); savedId = id; revision = rev; dirty = false;
    fundingState.reset(); fundingProblem = ''; renderFunding();
    resetCampaignBackupControls(backupControls);
    expandedActionRows = null;
    communicationOpenState = new WeakMap();
    budgetOpenState = new WeakMap();
    pendingBudgetFocus = null;
    const retainedSelection = resumeCurrentCampaign && previousOpportunityName
      ? document.opportunities.findIndex(row => row.name === previousOpportunityName) : -1;
    selected = retainedSelection >= 0 ? retainedSelection : preferActionable
      ? defaultCampaignOpportunityIndex(document.opportunities, localDate(), document.sources) : 0;
    tab = resumeCurrentCampaign && campaignTabs.some(([key]) => key === previousTab)
      ? previousTab : 'overview';
    sourceQuery = resumeCurrentCampaign ? previousSourceQuery : '';
    if (!resumeCurrentCampaign) {
      opportunityQuery = ''; opportunityStatus = 'all'; opportunityPage = 0;
    }
    assetQuery = resumeCurrentCampaign ? previousAssetQuery : '';
    communicationQuery = resumeCurrentCampaign ? previousCommunicationView.query : '';
    communicationRoute = resumeCurrentCampaign ? previousCommunicationView.route : null;
    communicationOrder = resumeCurrentCampaign ? previousCommunicationView.order : 'record';
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
    if (captureBudgetDisclosures()) rememberCampaign();
    lock(true); feedback.replaceChildren();
    try {
      const saved = await request('/api/campaigns/save', {data: {document, id: savedId, revision}});
      const openCommunications = document.communications.map(row => communicationOpenState.get(row));
      const openBudgetRows = document.budget.map(row => budgetOpenState.get(row));
      document = saved.document; savedId = saved.id; revision = saved.revision; dirty = false;
      fundingState.edited(); renderFunding();
      communicationOpenState = new WeakMap();
      // The save response retains the submitted canonical order, including hidden rows.
      document.communications.forEach((row, index) => {
        if (openCommunications[index] !== undefined) {
          communicationOpenState.set(row, openCommunications[index]);
        }
      });
      expandedActionRows = null;
      budgetOpenState = new WeakMap();
      document.budget.forEach((row, index) => {
        if (openBudgetRows[index] !== undefined) budgetOpenState.set(row, openBudgetRows[index]);
      });
      renderEditor(); renderSummary();
      rememberCampaign();
      status.textContent = 'Saved on this computer';
      feedback.replaceChildren(notice('Campaign saved. Answers, costs, checks and actions will be here when you return.', 'success'));
      await refreshShelf(); announce('Campaign saved.');
    } catch (problem) { error(problem.message + ' Your edits are still here. Export a campaign backup or use Copy backup text under Import or back up a campaign before reopening another version.'); }
    finally { lock(false); }
  }
  async function prepare() {
    if (busy) return;
    const fundingToken = fundingState.begin();
    fundingProblem = ''; renderFunding();
    lock(true); feedback.replaceChildren();
    try {
      const decision = campaignDecision(document, undefined,
        document.opportunities[selected]?.name || '');
      const report = await request('/api/campaigns/prepare', {data: {
        document, focused_opportunity: decision.focusOpportunity,
      }});
      if (!fundingState.current(fundingToken)) return;
      if (report.funding_summary) fundingState.accept(fundingToken, report.funding_summary);
      renderFunding();
      output.replaceChildren(renderReport(report));
      delete output.dataset.stale; output.classList.remove('campaign-output-stale');
      scrollCampaignTarget(output);
      announce('Campaign brief prepared. Unknowns and review items remain visible.');
    } catch (problem) { if (fundingState.current(fundingToken)) error(problem.message); }
    finally { if (fundingState.finish(fundingToken)) { lock(false); renderFunding(); } }
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
      // Preparation intentionally strips held and historical answer text from
      // shareable report data. Restore text from this locally selected backup
      // only after the server has validated and normalized its structure.
      const backupAnswers = Array.isArray(candidate.answers) ? candidate.answers : [];
      const importedCampaign = report.campaign;
      importedCampaign.answers = importedCampaign.answers.map((answer, index) => ({
        ...answer,
        label: backupAnswers[index]?.label ?? answer.label,
        text: backupAnswers[index]?.text ?? answer.text,
        limit: backupAnswers[index]?.limit ?? answer.limit,
        status: backupAnswers[index]?.status ?? answer.status,
      }));
      apply(importedCampaign); dirty = true; changed();
      feedback.replaceChildren(notice('Campaign imported locally. Save campaign to keep this copy.', 'success'));
    } catch (problem) { error(problem instanceof SyntaxError ? 'This file is not valid campaign JSON. Your current campaign is unchanged.' : problem.message); }
    finally { imported.input.value = ''; lock(false); }
  });

  function renderSummary() {
    const size = campaignCapacity(document);
    const number = value => new Intl.NumberFormat('en-AU').format(value);
    capacity.dataset.capacityState = size.state;
    capacity.className = size.state === 'within' ? 'fine' : 'notice warning';
    capacity.textContent = `Editor estimate: ${number(size.characters)} of ${number(CAMPAIGN_TEXT_LIMIT)} text characters; `
      + `${number(size.bytes)} of ${number(CAMPAIGN_BYTE_LIMIT)} bytes. `
      + (size.state === 'over' ? 'Above the save limit. Export a backup to keep every edit, then split the work into smaller campaigns. '
        : size.state === 'near' ? 'Nearly full. Back up before adding more material; consider a separate campaign for the next case. ' : '')
      + 'Saving checks normalized data and may add record fields. Backups retain unsaved edits.';
    const actionable = new Map(document.opportunities
      .filter(row => isOpportunityActionable(row.status))
      .map(row => [row.name, row]));
    const pending = document.requirements.filter(row => actionable.has(row.opportunity)
      && (!['met', 'not_met'].includes(row.status)
      || ![row.evidence, row.source_url, row.source_quote, row.checked_at].every(value => value?.trim())
      || !linkedSourceMatchesCheck(row, document.sources)));
    const heldAnswers = document.answers.filter(row => row.opportunity
      && actionable.has(row.opportunity)
      && !applicationAnswerAvailability(actionable.get(row.opportunity)).allowed);
    const over = document.answers.filter(row => {
      const opportunity = actionable.get(row.opportunity);
      const eligible = !row.opportunity || (opportunity
        && applicationAnswerAvailability(opportunity).allowed);
      return eligible && row.limit
        && countCharacters(row.text || '') > Number(row.limit);
    });
    const quotes = document.budget.filter(row => (!row.opportunity || actionable.has(row.opportunity))
      && (row.unit_cost == null || row.unit_cost === '' || !row.quote_reference?.trim()));
    const windows = document.opportunities.filter(row => isOpportunityActionable(row.status)
      && applicationWindowGaps(row, localDate(), document.sources).length > 0);
    const actionScopesToConfirm = document.actions.filter(row => isCampaignActionOpen(row)
      && row.scope_confirmed !== true).length;
    const submittedActionsToReview = document.actions.filter(row => isCampaignActionOpen(row)
      && row.scope_confirmed === true && row.opportunity
      && row.submission_phase !== 'post_submission'
      && document.opportunities.some(item => item.name === row.opportunity
        && item.status === 'submitted')).length;
    const reopenedActionsToReview = document.actions.filter(row => isCampaignActionOpen(row)
      && row.scope_confirmed === true && row.opportunity
      && row.submission_phase === 'post_submission'
      && document.opportunities.some(item => item.name === row.opportunity
        && isOpportunityActionable(item.status))).length;
    const inactiveRouteActionsToReview = document.actions.filter(row => isCampaignActionOpen(row)
      && row.scope_confirmed === true && row.opportunity
      && document.opportunities.some(item => item.name === row.opportunity
        && ['closed', 'paused', 'not_pursuing'].includes(item.status))).length;
    const ownersToConfirm = document.actions.filter(row => {
      if (!isCampaignActionOpen(row)
          || !isCampaignActionCurrent(row, document.opportunities)) return false;
      const owner = campaignActionOwnerState(row.owner, row.owner_confirmed,
        row.owner_kind);
      return owner.kind !== 'person' || row.owner_confirmed !== true;
    });
    const actionReviewCount = actionScopesToConfirm + submittedActionsToReview
      + reopenedActionsToReview + inactiveRouteActionsToReview;
    shelf.replaceChildren(...(document.title ? [h('h3', {}, document.title), h('p', {class: 'fine'}, document.organisation)] : []));
    summary.replaceChildren(...[[pending.length, 'requirements to check'],
      [over.length, 'answers to shorten'],
      [heldAnswers.length, 'answer rows held'],
      [quotes.length, 'costs needing a quote'], [windows.length, 'application windows to verify'],
      [document.opportunities.filter(row => isOpportunityActionable(row.status)
        && campaignCurrencyComparisonNote(row)).length, 'funding currencies to review'],
      [ownersToConfirm.length, 'owners to confirm'],
      [actionReviewCount, 'actions to review'],
      [document.actions.filter(row => row.status === 'held').length, 'actions on hold']].map(([count, label]) =>
      h('div', {}, h('strong', {}, count), h('span', {}, label))));
    renderDecisionCard();
  }
  function renderDecisionCard() {
    const result = campaignDecision(document, undefined, document.opportunities[selected]?.name || '');
    const state = h('span', {class: 'campaign-decision-state', 'data-state': result.state}, result.label);
    const repeatsBlocker = result.state === 'not_ready' && result.action.source === 'suggested'
      && result.detail.includes(result.action.task);
    const openRouteChecks = () => {
      tab = 'overview'; rememberCampaign(); renderEditor();
      const focus = editor.querySelector('.campaign-focus') || editor;
      focus.tabIndex = -1; focus.focus({preventScroll: true});
      scrollCampaignTarget(focus);
    };
    const targetDate = result.action.due ? new Date(result.action.due + 'T12:00:00') : null;
    const targetDatePast = Boolean(result.action.due && result.action.due < localDate());
    const taskPreview = result.action.task.length > 260
      ? result.action.task.slice(0, 257).trimEnd() + '…' : result.action.task;
    const action = h('div', {class: 'campaign-decision-action'},
      h('span', {class: 'eyebrow'}, result.action.source === 'recorded'
        ? result.action.opportunity ? `NEXT ACTION · ${result.action.opportunity}` : 'NEXT CAMPAIGN ACTION'
        : 'SUGGESTED ROUTE STEP'),
      h('p', {class: 'campaign-decision-task'}, repeatsBlocker ? 'Start with the blocker in Selected route status.' : taskPreview),
      !repeatsBlocker && taskPreview !== result.action.task
        ? h('p', {class: 'campaign-action-meta'}, 'The full recorded steps stay in the action list.') : null,
      h('p', {class: 'campaign-decision-owner'}, result.action.ownerStatus),
      result.action.due ? h('p', {class: 'campaign-decision-date' + (targetDatePast ? ' is-overdue' : '')},
        'Proposed target: ' + new Intl.DateTimeFormat('en-AU', {dateStyle: 'medium'}).format(targetDate)
          + (targetDatePast ? ' · past — confirm or reset' : '')) : null,
      button(repeatsBlocker ? 'Review route checks' : result.action.actionIndex === undefined ? 'Open next actions' : 'Open full action', () => {
        if (repeatsBlocker) { openRouteChecks(); return; }
        if (result.action.actionIndex !== undefined) {
          expandedActionRows ||= new WeakSet();
          const row = document.actions[result.action.actionIndex];
          if (row) expandedActionRows.add(row);
        }
        tab = 'actions'; rememberCampaign(); renderEditor();
        const recordedAction = result.action.actionIndex === undefined ? null
          : editor.querySelector(`[data-action-index="${result.action.actionIndex}"]`);
        const taskField = recordedAction?.querySelector('textarea');
        scrollCampaignTarget(taskField || recordedAction || editor);
        taskField?.focus({preventScroll: true});
      }, 'quiet'));
    const otherActiveRoutes = document.opportunities.filter(row =>
      isOpportunityActionable(row.status) && row.name !== result.focusOpportunity);
    const otherRoutesNeedReview = otherActiveRoutes.filter(row =>
      campaignDecision(document, undefined, row.name).state !== 'ready_for_review').length;
    decisionCard.replaceChildren(h('div', {class: 'campaign-decision-main'},
      h('h3', {}, 'Selected route status'), state,
      h('p', {class: 'campaign-decision-campaign'}, document.title || 'New campaign'),
      result.focusOpportunity ? h('p', {class: 'campaign-decision-focus'},
        'Selected route: ' + result.focusOpportunity) : null,
      otherRoutesNeedReview ? h('p', {class: 'campaign-decision-meta'},
        `${otherRoutesNeedReview} other active route${otherRoutesNeedReview === 1 ? '' : 's'} also need review.`) : null,
      h('p', {class: 'campaign-decision-detail'}, result.detail)), action,
      h('div', {class: 'campaign-decision-reopen'},
        h('strong', {}, 'Reopen or progress when'),
        h('p', {}, result.reopenCriteria),
        result.state === 'not_ready' && !repeatsBlocker
          ? button('Review route checks', openRouteChecks, 'quiet') : null),
      h('p', {class: 'campaign-decision-note'}, CAMPAIGN_DECISION_NOTE));
  }
  function scopeChoices() { return [['', 'Whole campaign'], ...document.opportunities.map(row => [row.name, row.name])]; }
  function addOpportunity() {
    if (!canAddCampaignOpportunity(document.opportunities)) {
      error(`This campaign has reached its ${CAMPAIGN_OPPORTUNITY_LIMIT}-route limit. Your existing records are unchanged. Export a campaign backup before splitting further routes into another campaign; text and byte limits still apply.`);
      return;
    }
    let number = document.opportunities.length + 1;
    while (document.opportunities.some(row => row.name === 'Opportunity ' + number)) number++;
    document.opportunities.push({name: 'Opportunity ' + number, funder: '', url: '', deadline: '', decision_window: '', ceiling: null, ceiling_currency: 'unconfirmed', fit: '', route_type: 'unknown', status: 'researching'});
    selected = document.opportunities.length - 1;
    opportunityQuery = ''; opportunityStatus = 'all';
    opportunityPage = Math.floor(selected / OPPORTUNITY_PAGE_SIZE);
    changed(); renderEditor();
  }
  function revealSelectedCampaignTab() {
    const tabs = sectionNavigation.querySelector('.campaign-tabs');
    const selectedTab = tabs?.querySelector('[aria-selected="true"]');
    if (!selectedTab) return;
    const bounds = tabs.getBoundingClientRect(), chosen = selectedTab.getBoundingClientRect();
    if (chosen.left < bounds.left) tabs.scrollLeft += chosen.left - bounds.left;
    else if (chosen.right > bounds.right) tabs.scrollLeft += chosen.right - bounds.right;
  }
  function updateCampaignClearance() {
    const saveRegion = root.querySelector('.campaign-save-bar');
    const top = saveRegion ? Number.parseFloat(getComputedStyle(saveRegion).top) || 0 : 0;
    const navigationTop = (saveRegion?.getBoundingClientRect().height || 0) + top + 8;
    root.style.setProperty('--campaign-navigation-top', `${Math.ceil(navigationTop)}px`);
    const clearance = navigationTop + sectionNavigation.getBoundingClientRect().height + 16;
    root.style.setProperty('--campaign-scroll-clearance', `${Math.ceil(clearance)}px`);
  }
  function scrollCampaignTarget(target, focus = false) {
    if (!target) return;
    updateCampaignClearance();
    if (focus) { target.tabIndex = -1; target.focus({preventScroll: true}); }
    target.scrollIntoView({block: 'start', behavior: 'auto'});
  }
  function openCampaignSection(id) {
    tab = id; rememberCampaign(); renderEditor();
    scrollCampaignTarget(editor.querySelector('.campaign-section'), true);
  }
  function renderEditor() {
    if (captureBudgetDisclosures()) rememberCampaign();
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
      const control = button(label, () => openCampaignSection(id), 'campaign-tab');
      control.setAttribute('role', 'tab'); control.setAttribute('aria-selected', String(tab === id)); control.tabIndex = tab === id ? 0 : -1;
      control.addEventListener('keydown', event => {
        const at = campaignTabs.findIndex(([key]) => key === tab);
        const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (offset) { event.preventDefault(); tab = campaignTabs[(at + offset + campaignTabs.length) % campaignTabs.length][0]; rememberCampaign(); renderEditor(); sectionNavigation.querySelector('[aria-selected="true"]').focus({preventScroll: true}); }
      });
      tabs.append(control);
    }
    panel.setAttribute('aria-label', campaignTabs.find(([id]) => id === tab)[1]);
    if (tab === 'overview') renderOpportunities(panel);
    else if (tab === 'answers') renderAnswers(panel);
    else if (tab === 'budget') renderBudget(panel);
    else if (tab === 'actions') renderActions(panel);
    else if (tab === 'communications') renderCommunications(panel);
    else if (tab === 'assets') renderAssets(panel);
    else renderSources(panel);
    if (['budget', 'actions'].includes(tab)) {
      const routeName = document.opportunities[selected]?.name || 'No route selected';
      const scopeNote = tab === 'budget'
        ? 'All current campaign costs.'
        : 'All action scopes remain shown.';
      const context = h('div', {class: 'campaign-section-context'},
        h('p', {}, 'Selected route: ', h('strong', {}, routeName), h('span', {}, scopeNote)),
        button('Campaign status', () => scrollCampaignTarget(decisionCard, true), 'quiet'));
      panel.prepend(context);
    }
    editor.replaceChildren(details, panel);
    sectionNavigation.replaceChildren(tabs);
    revealSelectedCampaignTab();
    if (pendingFocus) {
      updateCampaignClearance();
      const referenceScope = pendingFocus.referenceIndex === undefined ? ''
        : ` .campaign-asset-reference[data-reference-index="${pendingFocus.referenceIndex}"]`;
      const target = editor.querySelector(`.campaign-asset[data-asset-id="${pendingFocus.assetId}"]${referenceScope} [data-campaign-field="${pendingFocus.field}"]`);
      pendingFocus = null;
      if (target) {
        target.focus({preventScroll: true});
        target.scrollIntoView({block: 'center'});
      }
    }
    if (pendingBudgetFocus) {
      updateCampaignClearance();
      const {index, field: fieldName} = pendingBudgetFocus;
      pendingBudgetFocus = null;
      editor.querySelector(`[data-budget-index="${index}"] [data-campaign-field="${fieldName}"]`)?.focus();
    }
    if (pendingActionFocus) {
      updateCampaignClearance();
      const {index, field: fieldName} = pendingActionFocus;
      pendingActionFocus = null;
      const target = editor.querySelector(
        `.campaign-action[data-action-index="${index}"] [data-campaign-field="${fieldName}"]`);
      if (target) {
        target.focus({preventScroll: true});
        target.scrollIntoView({block: 'center'});
      }
    }
    pendingAssetOpenId = '';
  }
  function opportunityPicker(change) {
    const pick = selectField('Working on opportunity', document.opportunities.map((row, index) => [String(index), row.name]), String(selected));
    pick.input.addEventListener('change', () => {
      selected = Number(pick.input.value); rememberCampaign(); change(); renderSummary();
    });
    return pick.wrap;
  }
  function renderOpportunities(panel) {
    panel.append(h('div', {class: 'campaign-section-heading'}, h('div', {}, h('h3', {}, 'Funding and support routes'),
      h('p', {class: 'muted'}, 'Compare cash funding, non-cash programmes, timing, fit and open checks. Closed and paused routes stay visible as historical context.')), button('Add opportunity', addOpportunity, 'quiet')));
    if (!document.opportunities.length) {
      panel.append(h('div', {class: 'campaign-empty'}, h('h4', {}, 'Start with one opportunity'), h('p', {}, 'Add a funder or programme, then record what you know and what needs checking. No eligibility is assumed.'))); return;
    }
    selected = Math.min(selected, document.opportunities.length - 1);
    const rail = h('div', {class: 'campaign-opportunities', 'aria-label': 'Funding and support routes'});
    const search = field('Search funding routes', 'search', opportunityQuery,
      'Search names, funders, links and route notes. This view does not change campaign data or the whole-campaign funding totals.',
      {placeholder: 'Try a funder or programme', maxLength: 200});
    const filter = selectField('Filter funding routes by status',
      [['all', 'All recorded statuses'], ...opportunityStates], opportunityStatus);
    const count = h('p', {class: 'campaign-filter-status', role: 'status',
      'aria-live': 'polite', 'aria-label': 'Funding route list count'});
    const empty = h('p', {class: 'campaign-filter-empty', hidden: true},
      'No funding routes match. Clear the search or change the status filter. The selected editor and all records are retained.');
    const selection = h('p', {class: 'fine', 'aria-label': 'Retained selected funding route'});
    const previous = button('Previous funding routes page', () => {
      if (busy || opportunityPage <= 0) return;
      opportunityPage--; renderOpportunityRail(); rememberCampaign();
    }, 'quiet');
    const next = button('Next funding routes page', () => {
      if (busy || next.disabled) return;
      opportunityPage++; renderOpportunityRail(); rememberCampaign();
    }, 'quiet');
    const showSelected = button('Show selected route in list', () => {
      if (busy) return;
      opportunityQuery = ''; opportunityStatus = 'all';
      search.input.value = ''; filter.input.value = 'all';
      opportunityPage = Math.floor(selected / OPPORTUNITY_PAGE_SIZE);
      renderOpportunityRail(); rememberCampaign();
    }, 'quiet');
    function renderOpportunityRail() {
      const view = campaignOpportunityView(document.opportunities, {
        query: opportunityQuery, status: opportunityStatus, page: opportunityPage,
      });
      opportunityPage = view.page;
      rail.replaceChildren(...view.entries.map(({row, index}) => {
        const choose = button('', () => {
          selected = index; rememberCampaign(); renderEditor(); renderSummary();
        }, 'campaign-opportunity');
        choose.setAttribute('aria-pressed', String(index === selected));
        choose.dataset.opportunityIndex = String(index);
        choose.append(h('strong', {}, row.name), h('span', {}, row.funder || 'Funder to confirm'),
          h('small', {}, opportunityTypes.find(([key]) => key === row.route_type)?.[1] || 'Not classified'),
          h('small', {}, routeAmountLabel(row)), h('small', {}, opportunityTiming(row)));
        return choose;
      }));
      count.textContent = view.matched
        ? `${view.matched} of ${view.total} routes match · showing ${view.start}–${view.end} · page ${view.page + 1} of ${view.pages}`
        : `0 of ${view.total} routes match · no pages`;
      empty.hidden = view.matched !== 0;
      previous.disabled = view.page <= 0;
      next.disabled = !view.pages || view.page >= view.pages - 1;
      const selectedVisible = view.entries.some(({index}) => index === selected);
      selection.textContent = `Selected editor: ${document.opportunities[selected]?.name || 'Untitled route'}. `
        + (selectedVisible ? 'Shown in this page.'
          : view.matchedIndexes.includes(selected) ? 'Retained from another page.'
            : 'Retained outside the current filters.');
      showSelected.hidden = selectedVisible;
    }
    search.input.addEventListener('input', () => {
      opportunityQuery = search.input.value; opportunityPage = 0;
      renderOpportunityRail(); rememberCampaign();
    });
    filter.input.addEventListener('change', () => {
      opportunityStatus = filter.input.value; opportunityPage = 0;
      renderOpportunityRail(); rememberCampaign();
    });
    const routeList = h('div', {class: 'campaign-opportunity-list'},
      search.wrap, filter.wrap, count, empty, rail,
      h('div', {class: 'campaign-opportunity-pagination button-row'}, previous, next),
      selection, showSelected);
    const item = document.opportunities[selected], focus = h('section', {class: 'campaign-focus', 'aria-label': 'Selected opportunity'});
    const headerFunder = h('span', {class: 'eyebrow'}), headerName = h('h3', {}), programme = h('div');
    const windowSourceInfo = h('p', {class: 'campaign-window-source', role: 'status'});
    const maximum = h('dd', {}), deadlineLabel = h('dt', {}), deadlineValue = h('dd', {});
    const recordedDeadlineValue = h('dd', {});
    const recordedDeadline = h('div', {},
      h('dt', {}, 'Recorded closing date'), recordedDeadlineValue);
    const currencyComparison = h('p', {class: 'fine campaign-currency-comparison', role: 'status'});
    const decisionValue = h('dd', {}), statusValue = h('dd', {}), workflowValue = h('dd', {}), fitValue = h('p', {});
    const applicantConfirmationStatus = h('small', {class: 'campaign-action-meta'});
    function updateOpportunityView() {
      renderOpportunityRail();
      headerFunder.textContent = item.funder || 'FUNDER TO CONFIRM';
      headerName.textContent = item.name || 'Untitled opportunity';
      programme.replaceChildren(item.url ? safeLink(item.url, 'Open programme guidance')
        : h('p', {class: 'fine'}, 'Programme link not added yet.'));
      const linkedWindowSource = document.sources.find(source =>
        source.id === item.window_source_id);
      if (linkedWindowSource) {
        const snapshotIssue = campaignSourceSnapshotIssue(item.window_source_url,
          item.window_checked_at, linkedWindowSource);
        windowSourceInfo.replaceChildren(h('span', {},
          'Application-window source · user-entered, unverified: ',
          linkedWindowSource.url ? safeLink(linkedWindowSource.url, linkedWindowSource.title)
            : linkedWindowSource.title,
          snapshotIssue ? ' · ' + campaignSourceSnapshotGuidance(snapshotIssue)
            : ` · quote checked ${displayDate(item.window_checked_at)}`));
      } else {
        windowSourceInfo.textContent = 'No registered application-window source linked; link an official page and recheck the wording.';
      }
      maximum.textContent = routeAmountLabel(item);
      currencyComparison.textContent = campaignCurrencyComparisonNote(item);
      currencyComparison.hidden = !currencyComparison.textContent;
      const windowKind = item.application_window || (item.deadline ? 'fixed' : 'unknown');
      if (item.status === 'closed' || item.status === 'submitted') {
        deadlineLabel.textContent = 'Recorded closing date';
        deadlineValue.textContent = item.deadline ? displayDate(item.deadline) : 'Not recorded';
      } else if (windowKind === 'rolling') {
        deadlineLabel.textContent = 'Application window';
        deadlineValue.textContent = `Rolling${item.window_checked_at ? ` · checked ${displayDate(item.window_checked_at)}` : ' · check date needed'}`;
      } else if (windowKind === 'fixed') {
        deadlineLabel.textContent = 'Recorded closing date';
        deadlineValue.textContent = item.deadline ? displayDate(item.deadline) : 'Closing date needed';
      } else {
        deadlineLabel.textContent = 'Application window';
        deadlineValue.textContent = 'Application window not verified';
      }
      // Retain a recorded date even when current window evidence is unknown.
      // This presentation does not promote the date to a verified open window.
      recordedDeadline.hidden = !hasUnverifiedRecordedDeadline(item);
      recordedDeadlineValue.textContent = item.deadline ? displayDate(item.deadline) : '';
      decisionValue.textContent = item.decision_window || 'Not confirmed';
      statusValue.textContent = opportunityStates.find(([key]) => key === item.status)?.[1] || 'Researching';
      const applicantName = String(item.applicant || '').trim();
      if (item.application_mode === 'required') {
        workflowValue.textContent = !applicantName
          ? 'Application required · applicant needed'
          : item.applicant_confirmed === true
            ? `Application required · applicant confirmed by operator: ${applicantName}`
            : `Application required · applicant confirmation needed: ${applicantName}`;
      } else {
        workflowValue.textContent = item.application_mode === 'not_required'
          ? 'No formal application recorded'
          : 'Application process not confirmed';
      }
      applicantConfirmation.input.disabled = item.application_mode !== 'required'
        || !item.applicant?.trim();
      applicantConfirmation.wrap.hidden = item.application_mode !== 'required';
      if (!applicantName) {
        applicantConfirmationStatus.textContent = 'Enter the named applicant first. Eligibility and authority to submit still need separate checks.';
      } else if (item.applicant_confirmed === true) {
        applicantConfirmationStatus.textContent = 'You recorded this applicant as confirmed directly. Sinter cannot verify the conversation, programme eligibility or authority to submit.';
      } else {
        applicantConfirmationStatus.textContent = 'Confirm the named applicant directly with the person responsible for applying. This does not establish programme eligibility or authority to submit.';
      }
      fitValue.textContent = item.fit || 'Record which project option this opportunity could support and what needs checking.';
    }
    const name = input('Opportunity name', 'text', item, 'name', '', {required: true, maxLength: 200}, () => {
      for (const collection of ['requirements', 'answers', 'budget', 'actions', 'communications']) {
        for (const row of document[collection]) {
          if (row.opportunity === previousName) row.opportunity = item.name;
        }
      }
      for (const asset of document.assets) {
        asset.funding_opportunities = (asset.funding_opportunities || []).map(
          name => name === previousName ? item.name : name);
      }
      previousName = item.name; updateOpportunityView();
    });
    let previousName = item.name;
    const funder = input('Funder', 'text', item, 'funder', '', {maxLength: 300}, updateOpportunityView);
    const url = input('Programme page', 'url', item, 'url', '', {maxLength: 2000}, updateOpportunityView);
    const windowKind = choice('Application window', applicationWindows, item, 'application_window', updateOpportunityView);
    const deadline = input('Recorded closing date', 'date', item, 'deadline', 'User-entered only. Link and recheck the official wording; leave blank for rolling applications.', {}, updateOpportunityView);
    const windowQuote = input('Exact official wording for this window', 'textarea', item, 'window_source_quote', 'Copy the short sentence that confirms the closing date or rolling window. Sinter does not verify the quote.', {rows: 2, maxLength: 2000}, updateOpportunityView);
    const windowChecked = input('Window wording checked on', 'date', item,
      'window_checked_at', 'Use the date you checked the official programme page. '
      + 'Recheck within 90 days and before an application.', {}, updateOpportunityView);
    const windowSourceChange = h('p', {class: 'notice warning', role: 'status',
      'aria-label': 'Application-window source change', hidden: true});
    const windowSource = campaignSourcePicker('Registered source for the application window',
      item.window_source_id, source => {
        const selection = selectWindowSource(item, source);
        Object.assign(item, selection.opportunity);
        if (selection.changedSource) {
          windowQuote.input.value = '';
          windowChecked.input.value = '';
        }
        windowSourceChange.hidden = !selection.changedSource;
        windowSourceChange.textContent = selection.changedSource
          ? (source ? 'Application-window source changed.' : 'Application-window source cleared.')
            + ' Previous wording and its check date were cleared. Re-read the official source, then record both. The closing date remains user-entered.'
          : '';
        updateOpportunityView();
      });
    const decision = input('Decision timing', 'text', item, 'decision_window', 'For example, a decision several months after applications close.', {maxLength: 1000}, updateOpportunityView);
    const routeType = choice('Route type', opportunityTypes, item, 'route_type', updateOpportunityView);
    let applicantConfirmation;
    const applicationMode = choice('Application workflow', applicationModes, item, 'application_mode', () => {
      if (item.application_mode !== 'required') {
        item.applicant_confirmed = false;
        applicantConfirmation.input.checked = false;
        changed();
      }
      updateOpportunityView();
    });
    const applicant = input('Applicant / programme lead', 'text', item,
      'applicant',
      'Enter the exact person or legal entity that will apply. A name alone does not confirm identity, programme eligibility or authority.',
      {maxLength: 300}, () => {
        item.applicant_confirmed = false;
        applicantConfirmation.input.checked = false;
        updateOpportunityView();
      });
    applicantConfirmation = check('I have confirmed this named applicant directly with the person responsible for applying.', item.applicant_confirmed === true);
    applicantConfirmation.input.setAttribute('aria-label', 'Applicant confirmed directly');
    applicantConfirmation.input.addEventListener('change', () => {
      item.applicant_confirmed = applicantConfirmation.input.checked;
      changed(); updateOpportunityView();
    });
    applicantConfirmation.wrap.append(applicantConfirmationStatus);
    const ceiling = input('Funding ceiling amount', 'number', item, 'ceiling', 'Use the amount in the programme terms and choose its currency separately. Leave blank when no cash award or amount is known. A ceiling is not an award or project budget.', {min: 0, step: '.01'}, element => { item.ceiling = element.value || null; updateOpportunityView(); });
    const ceilingCurrency = selectField('Funding ceiling currency', CEILING_CURRENCY_OPTIONS,
      campaignCeilingCurrency(item), 'Project costs remain AUD. No currency conversion is made. For another currency, retain its exact name in Project fit and timing or source notes.');
    ceilingCurrency.input.dataset.campaignField = 'ceiling_currency';
    ceilingCurrency.input.addEventListener('change', () => {
      if (ceilingCurrency.input.value === 'AUD') delete item.ceiling_currency;
      else item.ceiling_currency = ceilingCurrency.input.value;
      changed(); updateOpportunityView();
    });
    const state = choice('Opportunity status', opportunityStates, item, 'status', updateOpportunityView);
    const fit = input('Project fit and timing', 'textarea', item, 'fit', 'Which project option could this support? Record any exclusions or conditions before committing costs.', {rows: 3, maxLength: 6000}, updateOpportunityView);
    const opportunityEditor = h('details', {class: 'campaign-opportunity-editor', open: !item.funder && !item.fit},
      h('summary', {}, 'Edit opportunity details'), h('div', {class: 'form-grid'}, name.wrap, funder.wrap, routeType.wrap), url.wrap,
      windowSourceInfo,
      h('p', {class: 'fine'}, 'Choose the official source before adding its exact window wording and check date. Changing or clearing the source resets both.'),
      windowSource.wrap, windowSourceChange,
      h('div', {class: 'form-grid'}, applicationMode.wrap, applicant.wrap),
      applicantConfirmation.wrap,
      h('div', {class: 'form-grid'}, windowKind.wrap, deadline.wrap, windowChecked.wrap, decision.wrap, ceiling.wrap, ceilingCurrency.wrap, state.wrap), windowQuote.wrap, fit.wrap);
    focus.append(h('header', {class: 'campaign-focus-heading'}, headerFunder, headerName, programme),
      h('dl', {class: 'campaign-opportunity-facts'},
        h('div', {}, h('dt', {}, 'Recorded funding amount / ceiling'), maximum),
        h('div', {}, deadlineLabel, deadlineValue), recordedDeadline,
        h('div', {}, h('dt', {}, 'Application lead'), workflowValue),
        h('div', {}, h('dt', {}, 'Decision timing'), decisionValue),
        h('div', {}, h('dt', {}, 'Status'), statusValue)),
      currencyComparison,
      h('div', {class: 'campaign-fit'}, h('strong', {}, 'Project fit and timing'), fitValue),
      opportunityEditor,
      fundingTrackingEditor(item, {sources: document.sources,
        sourcePicker: campaignSourcePicker, changed}));
    updateOpportunityView();
    const requirements = h('div', {class: 'campaign-checks'});
    function addRequirement() { document.requirements.push({opportunity: item.name, rule: '', status: 'unknown', evidence: '', source_id: '', source_url: '', source_quote: '', checked_at: ''}); changed(); renderEditor(); }
    requirements.append(h('div', {class: 'campaign-section-heading'}, h('h4', {}, 'What must be true?'), button('Add requirement', addRequirement, 'quiet')),
      h('p', {class: 'fine'}, 'Check each condition against current official guidance. These records do not determine overall eligibility.'));
    for (const row of document.requirements.filter(row => row.opportunity === item.name)) {
      const proof = h('p', {class: 'campaign-proof-status', role: 'status'});
      const stateLabel = h('span', {class: 'campaign-check-state'}), preview = h('span', {class: 'campaign-check-preview'});
      function updateProof() {
        const asserted = ['met', 'not_met'].includes(row.status);
        const complete = [row.evidence, row.source_url, row.source_quote, row.checked_at].every(value => value?.trim())
          && linkedSourceMatchesCheck(row, document.sources);
        const linked = document.sources.find(candidate => candidate.id === row.source_id);
        const sourceOutdated = Boolean(row.source_id && !linkedSourceMatchesCheck(row, document.sources));
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
        proof.textContent = `${historical ? 'This route is not active in this campaign; the check is retained for historical reference. ' : ''}Status and source details are user-entered. Sinter has not verified the link, wording, date or assessment.${sourceOutdated ? ` The linked source record is now dated ${linked?.checked_at || 'unknown'}, but this excerpt was checked ${row.checked_at || 'on an unrecorded date'}; re-read the exact wording and update the check date.` : asserted && !complete ? ' The source record is also incomplete.' : ''}`;
      }
      const rule = input('Requirement', 'text', row, 'rule', '', {maxLength: 4000});
      const status = choice('Requirement status', checkStates, row, 'status', updateProof);
      const reason = input('What the evidence establishes or leaves unclear', 'textarea', row, 'evidence', 'This note is user-entered and is not independently verified by Sinter.', {rows: 2, maxLength: 6000}, updateProof);
      const source = input('Source link (user-entered)', 'url', row, 'source_url', 'Sinter does not open or verify this link.', {maxLength: 2000}, updateProof);
      const quote = input('Source wording (user-entered)', 'textarea', row, 'source_quote', 'Paste the exact wording yourself. If the registered source changed, re-read and replace this excerpt.', {rows: 3, maxLength: 4000}, updateProof);
      const date = input('Date this excerpt was checked', 'date', row, 'checked_at', 'Record when you re-read this exact wording. For a registered source, match its current check date.', {}, updateProof);
      const sourcePreview = h('p', {class: 'campaign-window-source'});
      const sourceChange = h('p', {class: 'fine', role: 'status',
        'aria-label': 'Requirement source change', hidden: true});
      function updateSourcePreview(linked) {
        sourcePreview.hidden = !linked;
        sourcePreview.replaceChildren(linked
          ? h('span', {}, 'Linked campaign source · user-entered, unverified: ',
            linked.url ? safeLink(linked.url, linked.title) : linked.title)
          : '');
      }
      const linkedSource = document.sources.find(candidate => candidate.id === row.source_id);
      updateSourcePreview(linkedSource);
      const sourcePicker = campaignSourcePicker('Registered campaign source (optional)',
        row.source_id, linked => {
        const selection = selectRequirementSource(row, linked);
        Object.assign(row, selection.requirement);
        source.input.disabled = Boolean(linked);
        date.wrap.querySelector('label').textContent = linked
          ? 'Date checked for this excerpt · must match linked source' : 'Date checked for this excerpt (user-entered)';
        updateSourcePreview(linked);
        source.input.value = row.source_url || '';
        quote.input.value = row.source_quote || '';
        date.input.value = row.checked_at || '';
        status.input.value = row.status;
        sourceChange.hidden = !selection.changedSource;
        sourceChange.textContent = selection.changedSource
          ? (linked
            ? 'Source link changed. Your explanatory note is kept; recheck it against this source. Previous source wording was cleared.'
            : 'Source link cleared. Your explanatory note is kept; source wording and check date were cleared.')
            + (selection.resetAssessment ? ' The previous assessment was reset to Not checked.' : '')
          : '';
          updateProof();
        });
      source.input.disabled = Boolean(row.source_id);
      if (row.source_id) date.wrap.querySelector('label').textContent = 'Date checked for this excerpt · must match linked source';
      updateProof();
      const heading = h('summary', {}, h('span', {class: 'campaign-check-title'}, row.rule || 'New requirement'), stateLabel, preview);
      rule.input.addEventListener('input', () => { heading.querySelector('.campaign-check-title').textContent = row.rule || 'New requirement'; });
      requirements.append(h('details', {class: 'campaign-requirement', open: !row.rule}, heading,
        h('article', {class: 'campaign-check-editor', 'aria-label': 'Requirement check'}, rule.wrap, status.wrap, proof, reason.wrap,
        h('details', {open: Boolean(row.source_id || row.source_url || row.source_quote)},
          h('summary', {}, 'Supporting source · user-entered, unverified'),
          sourcePicker.wrap, sourceChange, sourcePreview, source.wrap, quote.wrap, date.wrap),
        remove(document.requirements, row, 'Remove requirement'))));
    }
    if (!document.requirements.some(row => row.opportunity === item.name)) requirements.append(h('p', {class: 'fine'}, 'No requirements checked yet. Start with applicant type, timing and permitted costs.'));
    const existingDraftCount = document.communications.filter(row =>
      row.opportunity === item.name && row.direction === 'outgoing' && row.status === 'draft').length;
    if (existingDraftCount) {
      requirements.append(h('p', {class: 'campaign-draft-existing'},
        `${existingDraftCount} unsent clarification draft${existingDraftCount === 1 ? '' : 's'} already recorded for this route. Review them in Communications before creating another; a new draft will be saved as a separate record.`));
    }
    requirements.append(button(existingDraftCount ? 'Create another clarification letter' : 'Draft clarification letter', () => {
      const campaignLink = {id: savedId, revision, opportunity: item.name,
        dirty: dirty || !savedId};
      let draft;
      try { draft = campaignClarificationDraft(document, item, campaignLink); }
      catch (exception) { error(exception.message || 'Could not prepare the clarification draft.'); return; }
      if (draft.openCount > 30) {
        error('This opportunity has more than 30 open checks. Split them across clarification letters before continuing.');
        return;
      }
      delete draft.openCount;
      remember('brief', draft);
      location.hash = 'brief';
    }, 'quiet'));
    focus.append(requirements);
    panel.append(h('div', {class: 'campaign-opportunity-layout'}, routeList, focus));
  }
  function renderAnswers(panel) {
    panel.append(h('h3', {}, 'Prepare application answers'), h('p', {class: 'muted'}, 'Keep the exact form question and its limit together. Drafts can be saved over the limit; they still need shortening before use.'));
    if (!document.opportunities.length) { panel.append(notice('Add a route first so each answer belongs to the right application.')); return; }
    selected = Math.min(selected, document.opportunities.length - 1);
    const selectedOpportunity = document.opportunities[selected];
    const opportunity = selectedOpportunity.name;
    const answerAccess = applicationAnswerAvailability(selectedOpportunity);
    const canPrepare = answerAccess.allowed;
    panel.append(opportunityPicker(renderEditor));
    if (!canPrepare) panel.append(notice(answerAccess.message, 'warning'));
    const addQuestion = button('Add application question', () => {
      document.answers.push({opportunity, label: '', text: '', limit: null, status: 'draft'}); changed(); renderEditor();
    }, 'quiet');
    addQuestion.disabled = !canPrepare;
    panel.append(addQuestion);
    for (const row of document.answers.filter(row => row.opportunity === opportunity)) {
      const label = input('Application question', 'textarea', row, 'label', 'Copy the actual wording from the application form.', {rows: 2, maxLength: 300});
      label.input.disabled = !canPrepare;
      const counter = h('p', {class: 'campaign-character-count', role: 'status'});
      function update() {
        const used = countCharacters(row.text || ''), limit = Number(row.limit);
        counter.textContent = limit > 0 ? `${used} / ${limit} characters${used > limit ? ' · ' + (used - limit) + ' over — shorten before using' : ' · within limit'}` : `${used} characters · confirm the form’s limit`;
        counter.classList.toggle('over-limit', limit > 0 && used > limit);
      }
      const limit = input('Character limit', 'number', row, 'limit', 'Keep this blank if the form does not specify a limit.', {min: 1, max: 20000, step: 1}, element => { row.limit = element.value ? Number(element.value) : null; update(); });
      limit.input.disabled = !canPrepare;
      const answer = input('Draft answer', 'textarea', row, 'text',
        canPrepare ? '' : answerAccess.message,
        {rows: 5, maxLength: 20000, readOnly: !canPrepare,
          placeholder: canPrepare ? '' : 'Saved answer held until this route is confirmed.'},
        () => { row.status = 'draft'; reviewed.input.value = 'draft'; update(); });
      if (!canPrepare) answer.input.value = '';
      const reviewed = choice('Answer review', [['draft', 'Needs review'], ['reviewed', 'Reviewed by me']], row, 'status');
      reviewed.input.disabled = !canPrepare;
      const copied = h('p', {class: 'fine', 'aria-live': 'polite'});
      update();
      const copy = button(answerAccess.copyLabel, async () => {
        try { await navigator.clipboard.writeText(row.text); copied.textContent = row.limit && countCharacters(row.text) > row.limit ? 'Copied as written. Shorten this draft before pasting it into the application.' : 'Answer copied.'; }
        catch { error('Clipboard access is unavailable. Export the campaign brief instead.'); }
      }, 'quiet');
      copy.disabled = !canPrepare;
      panel.append(h('article', {class: 'campaign-row', 'aria-label': 'Application answer'}, label.wrap, h('div', {class: 'form-grid'}, limit.wrap, reviewed.wrap), answer.wrap, counter,
        h('div', {class: 'button-row'}, copy, remove(document.answers, row, 'Remove question')), copied));
    }
  }
  function renderBudget(panel) {
    const total = h('p', {class: 'campaign-budget-total', role: 'status'});
    const progress = h('p', {class: 'fine campaign-budget-progress', 'aria-live': 'polite'});
    const actionable = new Set(document.opportunities
      .filter(row => isOpportunityActionable(row.status)).map(row => row.name));
    const currentRows = document.budget.filter(row => !row.opportunity || actionable.has(row.opportunity));
    const historicalRows = document.budget.filter(row => row.opportunity && !actionable.has(row.opportunity));
    const nextCost = button('Open the next cost to check', () => {
      const next = campaignQuotedBudget(currentRows);
      const row = currentRows[next.nextIndex];
      if (!row) return;
      setBudgetDisclosure(row, true);
      const state = campaignBudgetRowState(row);
      pendingBudgetFocus = {index: document.budget.indexOf(row),
        field: state.quantity === null ? 'quantity' : state.unitCents === null ? 'unit_cost' : 'quote_reference'};
      renderEditor();
    }, 'quiet');
    function invalidateBudgetAnswers() {
      for (const answer of document.answers) {
        if (actionable.has(answer.opportunity)) answer.status = 'draft';
      }
    }
    function updateTotal() {
      const state = campaignQuotedBudget(currentRows);
      total.textContent = state.label;
      progress.textContent = `${state.priced} of ${currentRows.length} recorded costs priced · ${state.missingReferences} reference${state.missingReferences === 1 ? '' : 's'} missing. A recorded reference still needs review.`;
      nextCost.hidden = state.nextIndex < 0;
    }
    panel.append(h('h3', {}, 'Current project costs'),
      h('p', {class: 'muted'}, 'Keep each quoted or estimated amount beside its original reference. Open a cost to check or edit it. Blank prices stay unknown.'),
      total, h('p', {class: 'fine campaign-budget-basis-note'},
        'Quoted amounts may have different or unknown GST bases. No GST conversion was made. Sinter has not qualified an application budget.'),
      h('div', {class: 'button-row'}, nextCost, button('Add budget item', () => {
        const row = {item: '', opportunity: '', quantity: 1, unit_cost: null, quote_reference: ''};
        document.budget.push(row); setBudgetDisclosure(row, true);
        invalidateBudgetAnswers();
        pendingBudgetFocus = {index: document.budget.length - 1, field: 'item'};
        changed(); renderEditor();
      }, 'quiet')), progress,
      h('details', {class: 'campaign-budget-basis-details'},
        h('summary', {}, 'About these amounts'), h('p', {class: 'fine'}, QUOTED_BUDGET_NOTE)));
    for (const route of document.opportunities.filter(row => actionable.has(row.name))) {
      const note = campaignCurrencyComparisonNote(route);
      if (note) panel.append(h('p', {class: 'fine campaign-currency-comparison'}, route.name + ': ' + note));
    }
    const nextRow = currentRows[campaignQuotedBudget(currentRows).nextIndex];
    function renderBudgetRow(row, historical = false) {
      const rowIndex = document.budget.indexOf(row);
      const title = h('strong', {class: 'campaign-budget-row-title'});
      const amount = h('span', {class: 'campaign-budget-row-amount'});
      const metadata = h('small', {class: 'campaign-budget-row-meta'});
      function refreshRow() {
        const state = campaignBudgetRowState(row);
        title.textContent = state.title;
        amount.textContent = state.amount;
        metadata.textContent = `${row.opportunity || 'Whole campaign'} · ${state.reference}${historical ? ' · Historical, excluded from current subtotal' : ''}`;
        amount.dataset.priced = String(state.priced);
      }
      function revised() {
        if (!historical || !row.opportunity || actionable.has(row.opportunity)) invalidateBudgetAnswers();
        refreshRow(); updateTotal();
      }
      const item = input('Budget item', 'text', row, 'item', '', {maxLength: 1000}, revised);
      const scope = choice('Funding opportunity', scopeChoices(), row, 'opportunity', () => {
        setBudgetDisclosure(row, true);
        pendingBudgetFocus = {index: rowIndex, field: 'opportunity'};
        revised(); renderEditor();
      });
      const quantity = input('Quantity', 'number', row, 'quantity', '', {min: 1, max: 100000, step: 1}, element => {
        row.quantity = element.value ? Number(element.value) : null; revised();
      });
      const price = input('Unit cost (AUD)', 'number', row, 'unit_cost', 'Record the price as supplied. Leave blank while waiting for a price.', {min: 0, step: '.01'}, element => {
        row.unit_cost = element.value || null; revised();
      });
      const quote = input('Quote or estimate reference', 'textarea', row, 'quote_reference',
        'Supplier, quote date, stated GST basis and where to find the original. This reference is not verified automatically.', {rows: 3, maxLength: 2000}, revised);
      const details = h('details', {}, h('summary', {}, title, amount, metadata),
        h('div', {class: 'campaign-budget-row-editor'}, h('div', {class: 'form-grid'}, item.wrap, scope.wrap),
          h('div', {class: 'form-grid'}, quantity.wrap, price.wrap), quote.wrap,
          remove(document.budget, row, 'Remove budget item', historical ? null : invalidateBudgetAnswers)));
      renderedBudgetRows.set(details, row);
      details.open = budgetOpenState.get(row) ?? (!historical && row === nextRow);
      budgetOpenState.set(row, details.open);
      details.addEventListener('toggle', () => {
        // Replaced rows and detached editors must not overwrite newer state.
        if (!details.isConnected || !document.budget.includes(row)) return;
        budgetOpenState.set(row, details.open);
        rememberCampaign();
      });
      refreshRow();
      panel.append(h('article', {class: 'campaign-row campaign-budget-row',
        'aria-label': 'Budget item', 'data-budget-index': rowIndex}, details));
    }
    for (const row of currentRows) renderBudgetRow(row);
    if (historicalRows.length) {
      panel.append(h('h4', {}, 'Historical costs · inactive routes'),
        notice('These items belong to closed, submitted, paused or not-pursued routes. They do not contribute to the current project total.', 'warning'));
      for (const row of historicalRows) renderBudgetRow(row, true);
    }
    updateTotal();
  }
  function renderActions(panel) {
    if (expandedActionRows === null) {
      expandedActionRows = new WeakSet();
      const decision = campaignDecision(document, localDate(), document.opportunities[selected]?.name || '');
      const nextIndex = decision.action?.actionIndex;
      if (Number.isInteger(nextIndex) && document.actions[nextIndex]) {
        expandedActionRows.add(document.actions[nextIndex]);
      }
    }
    panel.append(h('h3', {}, 'The next useful step'), h('p', {class: 'muted'}, 'Turn missing quotes, approvals and unanswered conditions into actions. New actions use the selected active route by default; change the scope for campaign-wide work. Submitted-route tasks only return to current work when marked as after-submission follow-up. A name or date is a planning note until the person agrees and timing is confirmed.'),
      button('Add next action', () => {
        const selectedRoute = document.opportunities[selected];
        const scopedRoute = selectedRoute && (isOpportunityActionable(selectedRoute.status)
          || selectedRoute.status === 'submitted');
        const row = {opportunity: scopedRoute ? selectedRoute.name : '',
          scope_confirmed: Boolean(scopedRoute),
          submission_phase: selectedRoute?.status === 'submitted'
            ? 'post_submission' : 'pre_submission',
          task: '', owner: '', owner_kind: 'unassigned', owner_confirmed: false,
          due: '', status: 'open'};
        document.actions.push(row);
        expandedActionRows.add(row);
        pendingActionFocus = {index: document.actions.length - 1, field: 'task'};
        changed(); renderEditor();
      }, 'quiet'));
    function holdReason(row) {
      if (!isCampaignActionScopeConfirmed(row)) return 'Hold reason: scope is not confirmed.';
      if (!row.opportunity) return '';
      const route = document.opportunities.find(item => item.name === row.opportunity);
      if (!route) return 'Hold reason: linked route no longer exists.';
      if (['closed', 'paused', 'not_pursuing'].includes(route.status)) {
        const label = opportunityStates.find(([key]) => key === route.status)?.[1]
          || 'inactive';
        return `Hold reason: route recorded as ${label.toLowerCase()}.`;
      }
      if (route.status === 'submitted' && row.submission_phase !== 'post_submission') {
        return 'Hold reason: submitted route; action is still marked before submission.';
      }
      if (isOpportunityActionable(route.status)
          && row.submission_phase === 'post_submission') {
        return 'Hold reason: action marked after submission; route is active again.';
      }
      return 'Hold reason: scope or route phase needs review.';
    }
    const indexedActions = document.actions.map((row, index) => ({row, index}));
    const sortByUrgency = rows => [...rows].sort((left, right) => {
      const rank = ({row}) => !row.due ? 2 : row.due < localDate() ? 0 : 1;
      const difference = rank(left) - rank(right);
      return difference || (left.row.due && right.row.due
        ? left.row.due.localeCompare(right.row.due) || left.index - right.index
        : left.index - right.index);
    });
    const currentActions = sortByUrgency(indexedActions.filter(({row}) =>
      isCampaignActionOpen(row) && isCampaignActionCurrent(row, document.opportunities)));
    const reviewActions = sortByUrgency(indexedActions.filter(({row}) =>
      isCampaignActionOpen(row) && !isCampaignActionCurrent(row, document.opportunities)));
    const heldActions = indexedActions.filter(({row}) => row.status === 'held');
    const completedActions = indexedActions.filter(({row}) => row.status === 'done');
    const groups = [
      {label: 'Current work', rows: currentActions},
      {label: 'Needs review before current work', rows: reviewActions},
      {label: 'On hold', rows: heldActions},
      {label: 'Completed', rows: completedActions},
    ].filter(group => group.rows.length);
    for (const group of groups) {
      panel.append(h('h4', {class: 'campaign-action-group-heading'},
        `${group.label} · ${group.rows.length}`));
      for (const {row, index: actionIndex} of group.rows) {
        let refreshActionSummary = () => {};
        const task = input('Next action', 'textarea', row, 'task',
          'Write the next step in plain language, including what to check and where to record the result.',
          {rows: 3, maxLength: 2000}, refreshActionSummary);
        const scopeChoices = [
          ...(row.scope_confirmed === true ? [] : [['__confirm_scope__', 'Choose scope · not confirmed']]),
          ['', 'Campaign-wide'], ...document.opportunities.map((item, index) => [`route:${index}`, item.name])];
        const selectedScope = row.scope_confirmed === true
          ? row.opportunity ? `route:${document.opportunities.findIndex(item => item.name === row.opportunity)}` : ''
          : '__confirm_scope__';
        const scope = selectField('Programme or scope', scopeChoices,
          selectedScope);
        scope.input.dataset.campaignField = 'scope';
        scope.input.addEventListener('change', () => {
          if (scope.input.value === '__confirm_scope__') return;
          row.opportunity = scope.input.value.startsWith('route:')
            ? document.opportunities[Number(scope.input.value.slice(6))]?.name || ''
            : '';
          row.scope_confirmed = true;
          pendingActionFocus = {index: actionIndex, field: 'scope'};
          changed(); renderEditor();
        });
        if (row.scope_confirmed !== true) {
          scope.wrap.append(notice('This older action has no recorded scope. Confirm whether it belongs to the whole campaign or a specific opportunity before using it as current work.', 'warning'));
        }
        const scopedOpportunity = document.opportunities.find(item => item.name === row.opportunity);
        const inactiveRoute = ['closed', 'paused', 'not_pursuing'].includes(scopedOpportunity?.status);
        const phaseReviewable = scopedOpportunity?.status === 'submitted'
          || row.submission_phase === 'post_submission';
        const phaseStatus = h('div', {class: 'campaign-action-phase-status', role: 'status', 'aria-live': 'polite'});
        function updatePhaseStatus() {
          phaseStatus.replaceChildren();
          if (row.status === 'done' || row.status === 'held') return;
          if (inactiveRoute) {
            const routeStatus = opportunityStates.find(([key]) => key === scopedOpportunity.status)?.[1]
              || 'inactive';
            phaseStatus.append(notice(`This route is ${routeStatus.toLowerCase()}. The action is held out of current work. Move it to a current route or campaign-wide scope if it still applies, or choose On hold to retain it without treating it as current work. Mark Done only when completed.`, 'warning'));
          } else if (!phaseReviewable) return;
          else if (scopedOpportunity?.status === 'submitted'
              && row.submission_phase !== 'post_submission') {
            phaseStatus.append(notice('This route is submitted. Mark an action as after-submission follow-up only when it is genuinely still needed.', 'warning'));
          } else if (isOpportunityActionable(scopedOpportunity?.status)
              && row.submission_phase === 'post_submission') {
            phaseStatus.append(notice('This action is still marked as after-submission follow-up, but the route is active again. It stays out of current work until you reclassify it as before submission.', 'warning'));
          }
        }
        const phase = phaseReviewable
          ? choice('Action phase', [['pre_submission', 'Before submission · held'],
            ['post_submission', 'After-submission follow-up']], row, 'submission_phase', () => {
              updatePhaseStatus(); refreshActionSummary();
              pendingActionFocus = {index: actionIndex, field: 'submission_phase'};
              renderEditor();
            })
          : null;
        if (phase) {
          phase.wrap.append(phaseStatus);
        }
        if (!phase) scope.wrap.append(phaseStatus);
        updatePhaseStatus();
        const ownerStatus = h('small', {class: 'campaign-action-meta', 'aria-live': 'polite'});
        function updateOwnerStatus() {
          const ownerText = String(row.owner || '').trim();
          const state = campaignActionOwnerState(ownerText, row.owner_confirmed,
            row.owner_kind);
          ownerStatus.textContent = state.detail;
          ownerStatus.dataset.state = state.state;
          acceptance.input.disabled = !state.canAccept;
          acceptance.input.checked = row.owner_confirmed === true;
        }
        const owner = input('Owner name or role', 'text', row, 'owner',
          'Record a person only when you can identify them, or record a role as a suggestion. A role is never treated as a person.',
          {maxLength: 200}, () => {
            const ownerText = String(row.owner || '').trim();
            if (!ownerText || /\bunassigned\b/i.test(ownerText)) {
              row.owner_kind = 'unassigned';
              row.owner = '';
              owner.input.value = '';
            }
            else if (/\b(?:suggested|role suggestion)\b/i.test(ownerText)) {
              row.owner_kind = 'role';
            } else if (row.owner_kind === 'unassigned') row.owner_kind = 'unknown';
            ownerKind.input.value = row.owner_kind;
            row.owner_confirmed = false;
            updateOwnerStatus(); refreshActionSummary();
          });
        owner.wrap.append(ownerStatus);
        const ownerKind = selectField('Owner type', [['unknown', 'Type needs confirmation'],
          ['person', 'Named person'], ['role', 'Suggested role'],
          ['unassigned', 'No owner assigned']], row.owner_kind);
        ownerKind.input.dataset.campaignField = 'owner_kind';
        ownerKind.input.addEventListener('change', () => {
          row.owner_kind = ownerKind.input.value;
          let ownerTypeHint = '';
          const ownerText = String(row.owner || '').trim();
          if (!ownerText || /\bunassigned\b/i.test(ownerText)) {
            row.owner_kind = 'unassigned';
            row.owner = '';
            owner.input.value = '';
            ownerKind.input.value = 'unassigned';
          } else if (row.owner_kind === 'unassigned') {
            row.owner = '';
            owner.input.value = '';
          } else if (/\b(?:suggested|role suggestion)\b/i.test(ownerText)) {
            const requestedKind = row.owner_kind;
            row.owner_kind = 'role';
            ownerKind.input.value = 'role';
            if (requestedKind !== 'role') {
              ownerTypeHint = requestedKind === 'unknown'
                ? 'This entry is marked as a suggested role. Keep it as a role, or replace it with an individual’s name before selecting Named person.'
                : 'This entry is marked as a suggested role. Replace it with an individual’s name before selecting Named person.';
            }
          }
          if (row.owner_kind !== 'person') row.owner_confirmed = false;
          updateOwnerStatus();
          if (ownerTypeHint) ownerStatus.textContent = ownerTypeHint;
          refreshActionSummary(); changed();
        });
        const acceptance = check('This person has accepted', row.owner_confirmed === true);
        acceptance.input.disabled = !campaignActionOwnerState(row.owner,
          row.owner_confirmed, row.owner_kind).canAccept;
        acceptance.input.setAttribute('aria-label', 'This person has accepted this action');
        acceptance.input.addEventListener('change', () => {
          row.owner_confirmed = acceptance.input.checked;
          updateOwnerStatus(); refreshActionSummary(); changed();
        });
        owner.wrap.append(ownerKind.wrap, acceptance.wrap,
          h('small', {class: 'campaign-action-meta'}, 'This is your record; Sinter cannot verify agreement.'));

        const dateStatus = h('p', {class: 'campaign-action-date-status', role: 'status'});
        function updateDateStatus() {
          if (row.status === 'done') {
            dateStatus.textContent = row.due ? 'Completed — proposed target kept for reference.' : 'Completed — no target date was recorded.';
            dateStatus.dataset.state = 'done';
          } else if (row.status === 'held') {
            dateStatus.textContent = row.due
              ? `On hold — proposed target ${displayDate(row.due)} kept for reference; not a current deadline.`
              : 'On hold — no target date was recorded.';
            dateStatus.dataset.state = 'held';
          } else if (!row.due) {
            dateStatus.textContent = 'No target date set. Confirm timing with the owner.';
            dateStatus.dataset.state = 'unset';
          } else if (row.due < localDate()) {
            dateStatus.textContent = `Past proposed target (${displayDate(row.due)}). Confirm whether this is still needed and agree a new date.`;
            dateStatus.dataset.state = 'overdue';
          } else {
            dateStatus.textContent = `Proposed target: ${displayDate(row.due)}. Confirm timing with the owner.`;
            dateStatus.dataset.state = 'target';
          }
        }
        const due = input('Proposed target date', 'date', row, 'due',
          'Planning target only, not a confirmed due date. Agree the timing with the owner.', {},
          () => { updateDateStatus(); refreshActionSummary(); });
        due.input.addEventListener('change', () => {
          pendingActionFocus = {index: actionIndex, field: 'due'};
          renderEditor();
        });
        due.wrap.append(dateStatus);
        const state = choice('Action status', [['open', 'To do'], ['held', 'On hold'], ['done', 'Done']], row, 'status', () => {
          updateDateStatus(); updatePhaseStatus(); refreshActionSummary();
          pendingActionFocus = {index: actionIndex, field: 'status'};
          renderEditor();
        });
        state.wrap.append(h('small', {class: 'campaign-action-meta'},
          'On hold needs newer Sinter; older previews cannot open these backups. Do not mark Done for compatibility.'));
        const taskText = String(row.task || '').trim().replace(/\s+/g, ' ');
        const taskSummary = h('span', {class: 'campaign-action-summary-task'},
          taskText || `Untitled action ${actionIndex + 1}`);
        const metaSummary = h('span', {class: 'campaign-action-summary-meta'});
        const summary = h('summary', {class: 'campaign-action-summary'},
          taskSummary, metaSummary);
        refreshActionSummary = () => {
          taskSummary.textContent = String(row.task || '').trim().replace(/\s+/g, ' ')
            || `Untitled action ${actionIndex + 1}`;
          const currentOwnerSummary = campaignActionOwnerState(row.owner,
            row.owner_confirmed, row.owner_kind).summary;
          const currentScope = row.scope_confirmed === true
            ? row.opportunity || 'Campaign-wide' : 'Scope needs confirmation';
          const currentDate = row.due
            ? `${row.status === 'held' ? 'Retained target' : row.due < localDate() ? 'Past target' : 'Target'} ${displayDate(row.due)}`
            : 'No target date';
          const currentStatus = row.status === 'done' ? 'Done'
            : row.status === 'held' ? 'On hold · not completed' : 'To do';
          const currentHold = group.label === 'Needs review before current work'
            ? holdReason(row) : '';
          const metaChildren = [h('span', {},
            `${currentScope} · ${currentOwnerSummary} · ${currentDate} · ${currentStatus}`)];
          if (currentHold) {
            metaChildren.push(h('strong', {class: 'campaign-action-hold-reason'}, currentHold));
          }
          metaSummary.replaceChildren(...metaChildren);
        };
        refreshActionSummary();
        const details = h('details', {class: 'campaign-action-details', open: expandedActionRows.has(row)},
          summary, row.status === 'held'
            ? notice('On hold by your choice, not completed. Choose To do to resume; scope and route checks still apply.') : null,
          task.wrap, scope.wrap,
          h('div', {class: 'form-grid'}, owner.wrap, due.wrap, state.wrap, phase?.wrap),
          remove(document.actions, row, 'Remove action'));
        details.addEventListener('toggle', () => {
          if (details.open) expandedActionRows.add(row);
          else expandedActionRows.delete(row);
        });
        panel.append(h('article', {class: 'campaign-row campaign-action',
          'aria-label': 'Campaign action', 'data-action-index': String(actionIndex)}, details));
        updateOwnerStatus(); updateDateStatus();
      }
    }
    async function exportPlan(format) {
      try {
        const actions = format === 'calendar'
          ? campaignActionRowsForCalendar(document.actions, document.opportunities)
          : campaignActionRowsForPlan(document.actions, document.opportunities);
        if (format === 'calendar' && !actions.length) {
          feedback.replaceChildren(notice('No current, scoped, open actions with proposed dates are available for the calendar.', 'warning'));
          return;
        }
        const plan = await request('/api/community/plan', {
          data: {title: document.title,
            actions},
        });
        download('sinter-campaign-actions.' + (format === 'calendar' ? 'ics' : 'csv'), plan[format], format === 'calendar' ? 'text/calendar' : 'text/csv');
      } catch (problem) { error(problem.message); }
    }
    if (document.actions.length) panel.append(
      h('p', {class: 'fine'}, 'CSV keeps all actions, including On hold records (status held), for audit. The calendar includes only dated To do actions with a confirmed current scope; held and completed actions are excluded.'),
      h('div', {class: 'button-row'}, button('Download actions CSV', () => exportPlan('csv'), 'quiet'), button('Download action dates', () => exportPlan('calendar'), 'quiet')));
  }
  function renderCommunications(panel) {
    panel.append(h('h3', {}, 'Record correspondence and drafts'),
      h('p', {class: 'muted'}, 'Keep incoming messages, outgoing drafts and sent records with their dates and evidence links. These are your entries: Sinter does not access email, open or verify links, send messages, or confirm that a message was sent or received.'),
      h('p', {class: 'fine'}, 'Only keep message details the campaign needs. Drafts are clearly marked as not sent.'),
      button('Add communication', () => {
        const row = {opportunity: '', date: '', direction: 'outgoing', status: 'draft',
          channel: 'email', counterparty: '', subject: '', content: '', evidence_links: []};
        document.communications.push(row);
        communicationQuery = ''; communicationRoute = null;
        communicationOpenState.set(row, true);
        changed(); tab = 'communications'; renderEditor();
        const target = editor.querySelector(`.campaign-communication[data-communication-index="${document.communications.indexOf(row)}"] [data-campaign-field="subject"]`);
        target?.focus(); target?.scrollIntoView({block: 'nearest'});
      }, 'quiet'));
    if (!document.communications.length) {
      panel.append(h('div', {class: 'campaign-empty'}, h('h4', {}, 'No communications recorded yet'),
        h('p', {}, 'Add a received message or an outgoing draft when there is something to track. Nothing is sent from this page.')));
      return;
    }
    if (communicationRoute && !document.opportunities.some(row => row.name === communicationRoute)) {
      communicationRoute = null;
    }
    const search = field('Find a communication', 'search', communicationQuery,
      'Search subjects, parties, message text, routes and saved evidence wording. This view does not change your records.',
      {placeholder: 'Try a contact, route or phrase from a message', maxLength: 200});
    const routeChoices = [['all', 'All routes and campaign-wide'], ['campaign', 'Campaign-wide'],
      ...document.opportunities.map((row, index) => [`route:${index}`, row.name])];
    const routeValue = communicationRoute === null ? 'all' : communicationRoute === '' ? 'campaign'
      : `route:${document.opportunities.findIndex(row => row.name === communicationRoute)}`;
    const routeFilter = selectField('Communication scope', routeChoices, routeValue);
    const order = selectField('Communication order', COMMUNICATION_ORDERS, communicationOrder);
    const resultCount = h('p', {class: 'campaign-filter-status', 'aria-live': 'polite'});
    const empty = h('p', {class: 'campaign-filter-empty', hidden: true},
      'No communications match this view. Clear the search or choose another scope.');
    const clear = button('Clear communication filters', () => {
      communicationQuery = ''; communicationRoute = null;
      search.input.value = ''; routeFilter.input.value = 'all';
      updateCommunicationView(); rememberCampaign(); search.input.focus();
    }, 'quiet');
    const communicationList = h('div', {class: 'campaign-communication-list'});
    const cards = new Map();
    function updateCommunicationView() {
      const view = campaignCommunicationView(document.communications, {
        query: communicationQuery, route: communicationRoute, order: communicationOrder});
      const shown = new Set(view.map(({index}) => index));
      for (const [index, card] of cards) card.hidden = !shown.has(index);
      const arranged = [...view.map(({index}) => cards.get(index)),
        ...[...cards].filter(([index]) => !shown.has(index)).map(([, card]) => card)];
      const current = [...communicationList.children];
      if (arranged.length !== current.length || arranged.some((card, index) => card !== current[index])) {
        communicationList.replaceChildren(...arranged);
      }
      empty.hidden = view.length !== 0;
      clear.hidden = !communicationQuery && communicationRoute === null;
      const orderLabel = COMMUNICATION_ORDERS.find(([value]) => value === communicationOrder)?.[1]
        || 'Record order';
      resultCount.textContent = `${view.length} of ${document.communications.length} communications · ${orderLabel}.`
        + (communicationOrder === 'record' ? '' : ' Entries without a valid recorded date appear last.');
    }
    search.input.addEventListener('input', () => {
      communicationQuery = search.input.value.trim(); updateCommunicationView(); rememberCampaign();
    });
    routeFilter.input.addEventListener('change', () => {
      const value = routeFilter.input.value;
      communicationRoute = value === 'all' ? null : value === 'campaign' ? ''
        : document.opportunities[Number(value.slice(6))]?.name ?? null;
      updateCommunicationView(); rememberCampaign();
    });
    order.input.addEventListener('change', () => {
      communicationOrder = order.input.value; updateCommunicationView(); rememberCampaign();
    });
    // Commit-time refresh keeps edited wording searchable without moving a row mid-typing.
    communicationList.addEventListener('change', event => {
      // Source search is view-only. Detaching this card on search-field blur
      // interrupts the mouse click on its explicit selection button.
      if (!event.target.closest('.campaign-source-picker')) updateCommunicationView();
    });
    communicationList.addEventListener('click', event => {
      if (event.target.closest('.campaign-source-picker button')) updateCommunicationView();
    });
    panel.append(search.wrap, h('div', {class: 'form-grid'}, routeFilter.wrap, order.wrap),
      clear, resultCount, empty, communicationList);
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
          row.counterparty, row.opportunity || 'Campaign-wide'].filter(Boolean).join(' · ');
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
      const contentCount = h('small', {class: 'campaign-character-count'},
        `${countCharacters(row.content || '')} characters · destination limits vary; check before copying.`);
      content.input.addEventListener('input', () => {
        contentCount.textContent = `${countCharacters(content.input.value)} characters · destination limits vary; check before copying.`;
      });
      content.wrap.append(contentCount);
      const evidence = h('div', {class: 'campaign-communication-evidence'},
        h('h4', {}, 'Evidence links · user-entered, unverified'),
        h('p', {class: 'fine'}, 'For example, a link to a message, attachment or portal record. Sinter does not open or check it.'),
      button('Add evidence link', () => {
        if (evidenceLinks.length >= 10) { error('A communication can have up to 10 evidence links.'); return; }
          evidenceLinks.push({source_id: '', title: '', url: '', notes: '', checked_at: ''}); changed(); renderEditor();
        }, 'quiet'));
      for (const link of evidenceLinks) {
        link.source_id ??= '';
        link.checked_at ??= '';
        const linkTitle = input('Evidence title', 'text', link, 'title',
          'For example, “Email from programme officer” or “Application portal receipt”.', {maxLength: 500});
        const linkUrl = input('Evidence link', 'url', link, 'url',
          'HTTP or HTTPS link only. Links are not opened or verified by Sinter.', {maxLength: 4000});
        const linkNotes = input('Evidence note', 'textarea', link, 'notes', '',
          {rows: 2, maxLength: 2000});
        const savedSource = document.sources.find(source => source.id === link.source_id);
        const linkChecked = input(savedSource
          ? 'Source check date at link time · user-entered'
          : 'Source check date · user-entered', 'date', link, 'checked_at',
        savedSource
          ? 'Preserved from when this evidence was linked. Sinter does not verify the date.'
          : 'Record the source check date. Sinter does not verify it.', {});
        const snapshotWarning = notice('', 'warning');
        function updateSnapshotWarning(source) {
          const differs = Boolean(source && (link.title !== source.title
            || link.url !== source.url || link.checked_at !== source.checked_at));
          snapshotWarning.hidden = !differs;
          snapshotWarning.textContent = differs
            ? 'This saved evidence snapshot differs from the current source record. Its original title, link and check date are preserved. Recheck the source before use; clear and select it again only to replace the snapshot.'
            : '';
        }
        updateSnapshotWarning(savedSource);
        const sourceChoice = campaignSourcePicker('Link to a saved campaign source', link.source_id, source => {
          const isNewLink = Boolean(source && source.id !== link.source_id);
          link.source_id = source?.id || '';
          if (source && isNewLink) {
            link.title = source.title;
            link.url = source.url;
            link.checked_at = source.checked_at;
            linkTitle.input.value = source.title;
            linkUrl.input.value = source.url;
            linkChecked.input.value = source.checked_at;
          }
          linkTitle.input.disabled = Boolean(source);
          linkUrl.input.disabled = Boolean(source);
          linkChecked.input.disabled = Boolean(source);
          linkChecked.wrap.querySelector('label').textContent = source
            ? 'Source check date at link time · user-entered'
            : 'Source check date · user-entered';
          updateSnapshotWarning(source);
        });
        linkTitle.input.disabled = Boolean(savedSource);
        linkUrl.input.disabled = Boolean(savedSource);
        linkChecked.input.disabled = Boolean(savedSource);
        evidence.append(h('article', {class: 'campaign-row', 'aria-label': 'Communication evidence link'},
          sourceChoice.wrap, snapshotWarning, linkTitle.wrap, linkUrl.wrap, linkChecked.wrap, linkNotes.wrap,
          link.url ? safeLink(link.url, 'Open evidence link') : null,
          remove(evidenceLinks, link, 'Remove evidence link')));
      }
      const opportunity = choice('Related opportunity', scopeChoices(), row, 'opportunity', updateSummary);
      const open = communicationOpenState.get(row) ?? (!row.subject && !row.content);
      communicationOpenState.set(row, open);
      const details = h('details', {open}, summary,
          h('div', {class: 'form-grid'}, direction.wrap, statusField.wrap, channel.wrap, date.wrap),
          h('div', {class: 'form-grid'}, counterparty.wrap, subject.wrap, opportunity.wrap),
          content.wrap, evidence, h('p', {class: 'fine'}, 'Status, date, message details and links remain user-entered and unverified.'),
          remove(document.communications, row, 'Remove communication'));
      details.addEventListener('toggle', () => communicationOpenState.set(row, details.open));
      cards.set(index, h('article', {class: 'campaign-row campaign-communication',
        'aria-label': 'Campaign communication', 'data-communication-index': String(index)}, details));
      updateSummary();
    }
    updateCommunicationView();
  }
  function renderAssets(panel) {
    const previouslyOpen = new Map([...editor.querySelectorAll('.campaign-asset[data-asset-id]')]
      .map(card => [card.dataset.assetId, card.firstElementChild?.open || false]));
    const previouslyOpenWorkstreams = new Map([...editor.querySelectorAll(
      '.campaign-asset-workstream[data-workstream-key]')]
      .map(details => [details.dataset.workstreamKey, details.open]));
    const heading = h('div', {class: 'campaign-section-heading'}, h('div', {},
      h('h3', {}, 'Products, research and IP records'),
      h('p', {class: 'muted'}, 'Keep each product or research asset separate. This register is independent of grant eligibility and does not decide who owns an asset, whether it is novel, or whether it can be commercialised.')),
    button('Add product or asset', () => {
      const asset = {id: newRecordId(), name: '', kind: 'product', stage: 'unknown',
        public_summary: '', public_url: '', differentiation_question: '',
        contributors_status: 'unknown', contributor_notes: '',
        rights_status: 'unknown', rights_notes: '', disclosure_status: 'unknown',
        first_public_date: '', disclosure_notes: '', prior_art_status: 'not_started',
        prior_art_notes: '', prior_art_checked_at: '', funding_opportunities: [],
        references: []};
      document.assets.push(asset);
      pendingAssetOpenId = asset.id;
      pendingFocus = {assetId: asset.id, field: 'name'};
      changed(); renderEditor();
    }, 'quiet'));
    panel.append(heading,
      notice('Do not paste confidential invention details, contracts, legal advice, credentials or local file paths here. Add only a short status and a non-sensitive reference. Sinter does not open or verify links.', 'warning'));
      if (!document.assets.length) {
      panel.append(h('div', {class: 'campaign-empty'}, h('h4', {}, 'No products or research assets recorded'),
        h('p', {}, 'Start with the public name and current stage. Leave rights, contributor and disclosure records as not checked until you have supporting evidence.')));
      return;
    }
    const search = field('Find a product or asset', 'search', assetQuery,
      'Search names, types, recorded statuses, route links and non-sensitive notes. Filtering does not change campaign data.',
      {placeholder: 'Try a product name, research topic or funder', maxLength: 200});
    search.input.className = 'campaign-asset-filter';
    const resultCount = h('p', {class: 'campaign-filter-status', 'aria-live': 'polite'});
    const empty = h('p', {class: 'campaign-filter-empty', hidden: true},
      'No products or assets match. Clear the search to see the full register.');
    const clearFilter = button('Clear search', () => {
      search.input.value = '';
      updateAssetFilter(); rememberCampaign(); search.input.focus();
    }, 'quiet');
    clearFilter.hidden = !assetQuery;
    const assetList = h('div', {class: 'campaign-asset-list'});
    panel.append(search.wrap, clearFilter, resultCount, empty, assetList);
    const assetCards = [];
    for (const [index, row] of document.assets.entries()) {
      const workstreamOwner = row.id || row.name || `asset-${index}`;
      const workstream = (key, title, statusOptions, value, ...content) => {
        const selected = statusOptions.find(([option]) => option === value)?.[1]
          || 'Not recorded';
        const state = selected.split(' · ')[0];
        return h('details', {
        class: 'campaign-asset-workstream',
        'data-workstream-key': `${workstreamOwner}:${key}`,
        open: previouslyOpenWorkstreams.get(`${workstreamOwner}:${key}`) || false,
      }, h('summary', {}, h('strong', {}, title), h('span', {class: 'fine'}, state)),
      ...content);
      };
      const refs = Array.isArray(row.references) ? row.references : (row.references = []);
      const name = input('Product or asset name', 'text', row, 'name',
        'Use one row per distinct product, research system, model, dataset or name.',
        {required: true, maxLength: 250});
      const heading = h('strong', {}, row.name || 'Untitled product or asset');
      const meta = h('small', {class: 'campaign-asset-meta'}, '');
      function updateHeading() {
        heading.textContent = row.name || 'Untitled product or asset';
        const rightsLabel = rightsStatuses.find(([key]) => key === row.rights_status)?.[1]
          || 'Rights not checked';
        const priorArtLabel = priorArtStatuses.find(([key]) => key === row.prior_art_status)?.[1]
          || 'Prior art not started';
        meta.textContent = `${assetKinds.find(([key]) => key === row.kind)?.[1] || 'Other'} · ${assetStages.find(([key]) => key === row.stage)?.[1] || 'Not recorded'} · ${rightsLabel} · ${priorArtLabel}`;
      }
      name.input.addEventListener('input', updateHeading);
      const kind = choice('Asset type', assetKinds, row, 'kind', updateHeading);
      const stage = choice('Current stage', assetStages, row, 'stage', updateHeading);
      const publicSummary = input('Public description · user-entered', 'textarea', row,
        'public_summary', 'Summarise what a public page says. Keep it separate from internal technical detail and claims about novelty.', {rows: 3, maxLength: 3000});
      const publicUrl = input('Public description link', 'url', row, 'public_url',
        'HTTP or HTTPS only. Sinter will not open or verify this link.', {maxLength: 4000});
      const differentiation = input('What difference should the research test?', 'textarea', row,
        'differentiation_question', 'Write a question about the exact technical contribution, not an unsupported novelty or patentability claim.', {rows: 3, maxLength: 3000});

      const contributorStatus = choice('Contributor record status', contributorStatuses,
        row, 'contributors_status');
      const contributorNotes = input('Contributor record note', 'textarea', row,
        'contributor_notes', 'Use a short, non-sensitive status. Record names only when needed for an authorised internal register.', {rows: 2, maxLength: 2000});
      const rightsStatus = choice('Rights and title record status', rightsStatuses,
        row, 'rights_status');
      const rightsNotes = input('Rights record note', 'textarea', row, 'rights_notes',
        'A public licence is not proof that the company owns every contribution. Do not paste contract terms or legal advice.', {rows: 2, maxLength: 2000});
      const disclosureStatus = choice('First disclosure record status', disclosureStatuses,
        row, 'disclosure_status');
      const disclosureDate = input('First public disclosure date · if known', 'date', row,
        'first_public_date', 'Enter a date only when supported by a record. This field does not verify it.', {});
      const disclosureNotes = input('Disclosure record note', 'textarea', row,
        'disclosure_notes', 'For example, identify the kind of dated source to locate. Avoid confidential invention detail.', {rows: 2, maxLength: 2000});
      const priorArtStatus = choice('Prior-art research stage', priorArtStatuses,
        row, 'prior_art_status');
      const priorArtChecked = input('Prior-art check date · user-entered', 'date', row,
        'prior_art_checked_at', 'A recorded date is not evidence that a search was comprehensive.', {});
      const priorArtNotes = input('Prior-art research question or note', 'textarea', row,
        'prior_art_notes', 'Record the search scope, unresolved questions and closest leads. This is not a legal opinion.', {rows: 3, maxLength: 3000});
      const funding = h('fieldset', {class: 'campaign-asset-funding'},
        h('legend', {}, 'Funding routes to assess'),
        h('p', {class: 'fine'}, 'Selecting a route records a research link only; it does not imply fit or eligibility.'));
      row.funding_opportunities = Array.isArray(row.funding_opportunities)
        ? row.funding_opportunities : [];
      const fundingChecks = [];
      const fundingLimit = h('p', {class: 'fine', 'aria-live': 'polite'});
      function updateFundingLimit() {
        const limitReached = row.funding_opportunities.length >= 10;
        for (const item of fundingChecks) {
          item.input.disabled = limitReached && !item.input.checked;
        }
        fundingLimit.textContent = `${row.funding_opportunities.length} of ${fundingChecks.length} available route links selected. `
          + (limitReached ? 'Maximum 10 links; remove one before adding another.'
            : 'Maximum 10 links per product or asset.');
      }
      if (!document.opportunities.length) {
        funding.append(h('p', {class: 'fine'}, 'Add a funding opportunity before linking this asset to a route.'));
      } else {
        for (const opportunity of document.opportunities) {
          const linked = check(opportunity.name,
            row.funding_opportunities.includes(opportunity.name));
          linked.input.setAttribute('aria-label',
            `Assess ${row.name || 'this asset'} under ${opportunity.name}`);
          fundingChecks.push(linked);
          linked.input.addEventListener('change', () => {
            const values = new Set(row.funding_opportunities);
            if (linked.input.checked) values.add(opportunity.name);
            else values.delete(opportunity.name);
            row.funding_opportunities = [...values];
            updateFundingLimit();
            changed();
          });
          funding.append(linked.wrap);
        }
        funding.append(fundingLimit);
        updateFundingLimit();
      }
      const references = h('div', {class: 'campaign-asset-references'},
        h('h4', {}, 'Non-sensitive evidence references'),
        h('p', {class: 'fine'}, 'Add a public source, repository record or opaque internal reference you are authorised to use. Links remain unverified; do not add uploads or local paths.'),
        button('Add evidence reference', () => {
          if (refs.length >= 20) { error('Each product or asset can have up to 20 evidence references.'); return; }
          refs.push({kind: 'other', source_id: '', title: '', url: '',
            excerpt: '', checked_at: '', notes: ''});
          pendingFocus = {assetId: row.id, field: 'source_id', referenceIndex: refs.length - 1};
          changed(); renderEditor();
        }, 'quiet'));
      for (const [referenceIndex, reference] of refs.entries()) {
        const referenceKind = choice('Evidence type', assetReferenceKinds,
          reference, 'kind');
        const sourceChoice = campaignSourcePicker('Link a campaign source (optional)',
          reference.source_id, source => {
            if (reference.source_id !== (source?.id || '')) {
              reference.excerpt = '';
              reference.checked_at = source?.checked_at || '';
            }
            reference.source_id = source?.id || '';
            if (source) {
              reference.title = source.title;
              reference.url = source.url;
            }
            pendingFocus = {assetId: row.id, field: 'excerpt', referenceIndex};
            renderEditor();
          });
        sourceChoice.input.dataset.campaignField = 'source_id';
        const linkedSource = document.sources.find(item => item.id === reference.source_id);
        const title = linkedSource ? h('p', {class: 'fine'},
          `Campaign source: ${linkedSource.title}`)
          : input('Reference title (required)', 'text', reference, 'title',
            'Use a clear name for the evidence; no file will be uploaded.',
            {required: true, maxLength: 500});
        const url = linkedSource ? (linkedSource.url
          ? safeLink(linkedSource.url, 'Open linked campaign source')
          : h('span', {class: 'fine'}, 'No source link recorded'))
          : input('HTTP or HTTPS link · optional', 'url', reference, 'url',
            'Sinter does not open or verify the link. Do not use local file paths.', {maxLength: 4000});
        const excerpt = input('Relevant passage · quote or short paraphrase',
          'textarea', reference, 'excerpt',
          'Copy only the short passage that supports this specific record; clearly paraphrase rather than using quotation marks if it is not verbatim.',
          {rows: 2, maxLength: 3000});
        const checkedAt = input('Reference checked date · user-entered',
          'date', reference, 'checked_at',
          'This records when you reviewed the reference. Sinter does not verify it.', {});
        const notes = input('Non-sensitive reference note', 'textarea', reference,
          'notes', '', {rows: 2, maxLength: 2000});
        references.append(h('div', {class: 'campaign-asset-reference',
          'data-reference-index': referenceIndex},
          h('div', {class: 'form-grid'}, referenceKind.wrap, sourceChoice.wrap),
          title.wrap || title, url.wrap || url, excerpt.wrap, checkedAt.wrap, notes.wrap,
          remove(refs, reference, 'Remove reference')));
      }
      const summary = h('summary', {}, heading, meta);
      const opened = previouslyOpen.get(row.id) ?? pendingAssetOpenId === row.id;
      const card = h('article', {class: 'campaign-row campaign-asset',
        'data-asset-id': row.id,
        'aria-label': `${row.name || 'Untitled product or asset'} record`},
      h('details', {open: opened}, summary,
        h('div', {class: 'form-grid'}, name.wrap, kind.wrap, stage.wrap),
        h('div', {class: 'campaign-asset-public'}, publicSummary.wrap, publicUrl.wrap,
          differentiation.wrap),
        funding,
        h('div', {class: 'campaign-asset-workstreams'},
          workstream('contributors', 'Contributors', contributorStatuses, row.contributors_status,
            contributorStatus.wrap, contributorNotes.wrap),
          workstream('rights', 'Rights and title', rightsStatuses, row.rights_status,
            rightsStatus.wrap, rightsNotes.wrap),
          workstream('disclosure', 'Disclosure', disclosureStatuses, row.disclosure_status,
            disclosureStatus.wrap, disclosureDate.wrap, disclosureNotes.wrap),
          workstream('prior-art', 'Prior art', priorArtStatuses, row.prior_art_status,
            priorArtStatus.wrap, priorArtChecked.wrap, priorArtNotes.wrap)),
        references,
        remove(document.assets, row, 'Remove product or asset')));
      card.dataset.search = [row.name, row.kind, row.stage, row.public_summary,
        row.differentiation_question, row.contributors_status, row.contributor_notes,
        row.rights_status, row.rights_notes, row.disclosure_status, row.disclosure_notes,
        row.prior_art_status, row.prior_art_notes, ...(row.funding_opportunities || []),
        ...refs.flatMap(reference => [reference.kind, reference.title, reference.url,
          reference.excerpt, reference.notes])].join(' ').toLocaleLowerCase();
      assetCards.push(card);
      assetList.append(card);
      updateHeading();
    }
    function updateAssetFilter() {
      assetQuery = search.input.value.trim();
      const query = assetQuery.toLocaleLowerCase();
      let shown = 0;
      for (const card of assetCards) {
        card.hidden = Boolean(query && !card.dataset.search.includes(query));
        if (!card.hidden) shown++;
      }
      empty.hidden = shown !== 0;
      clearFilter.hidden = !query;
      resultCount.textContent = query
        ? `${shown} of ${assetCards.length} products and assets match “${assetQuery}”.`
        : `${assetCards.length} products and assets · search names, notes or routes.`;
    }
    search.input.addEventListener('input', () => {
      updateAssetFilter(); rememberCampaign();
    });
    updateAssetFilter();
  }
  function renderSources(panel) {
    const previouslyOpen = new Map([...editor.querySelectorAll(
      '.campaign-source-details[data-source-id]')]
      .map(details => [details.dataset.sourceId, details.open]));
    const heading = h('div', {class: 'campaign-section-heading'}, h('div', {},
      h('h3', {}, 'Keep the original guidance close'),
      h('p', {class: 'muted'}, 'Links stay as entered; Sinter does not fetch or verify them. Search the register and open only the records you need.')),
      button('Add source', () => { document.sources.push({id: newRecordId(),
        title: '', url: '', notes: '', checked_at: ''}); changed(); renderEditor(); }, 'quiet'));
    const search = field('Search sources', 'search', sourceQuery,
      'Search titles, links and notes. This filter does not change campaign data.',
      {placeholder: 'Try a product, funder or source title', maxLength: 200});
    search.input.className = 'campaign-source-filter';
    const resultCount = h('p', {class: 'campaign-filter-status', 'aria-live': 'polite'});
    const empty = h('p', {class: 'campaign-filter-empty', hidden: true},
      'No sources match. Clear the search or add a source.');
    const sourceList = h('div', {class: 'campaign-source-list'});
    function updateSourceFilter() {
      sourceQuery = search.input.value.trim();
      const query = sourceQuery.toLocaleLowerCase();
      let shown = 0;
      for (const card of sourceList.children) {
        card.hidden = Boolean(query && !card.dataset.search.includes(query));
        if (!card.hidden) shown++;
      }
      empty.hidden = shown !== 0;
      resultCount.textContent = query
        ? `${shown} of ${sourceList.children.length} sources match “${sourceQuery}”.`
        : `${sourceList.children.length} sources · search by title, link or notes.`;
    }
    for (const row of document.sources) {
      const title = input('Source title (required)', 'text', row, 'title', '',
        {required: true, maxLength: 500});
      const url = input('Source link', 'url', row, 'url', '', {maxLength: 2000});
      const notes = input('Source wording and notes', 'textarea', row, 'notes', 'Preserve wording that supports a requirement, deadline or exclusion.', {rows: 5, maxLength: 6000});
      const checkedAt = input('Source checked date · user-entered', 'date', row,
        'checked_at', 'Record the date you checked the source. Sinter does not fetch it.', {});
      const summaryTitle = h('strong', {}, row.title || 'Untitled source');
      const summaryDate = h('span', {class: 'fine'}, row.checked_at
        ? `Checked ${row.checked_at}` : 'Check date not recorded');
      const card = h('article', {class: 'campaign-row campaign-source-record',
        'aria-label': `Campaign source: ${row.title || 'Untitled source'}`},
        h('details', {class: 'campaign-source-details', 'data-source-id': row.id,
          open: previouslyOpen.get(row.id) ?? !row.title},
        h('summary', {}, summaryTitle, summaryDate),
        h('div', {class: 'campaign-source-fields'}, title.wrap, url.wrap, notes.wrap,
          checkedAt.wrap, row.url ? safeLink(row.url, 'Open source') : h('span'),
          button('Remove source', () => {
          const linked = document.assets.some(asset => asset.references?.some(
            reference => reference.source_id === row.id))
            || document.requirements.some(requirement => requirement.source_id === row.id)
            || document.opportunities.some(opportunity => opportunity.window_source_id === row.id)
            || document.opportunities.some(opportunity => fundingReferencesSource(opportunity, row.id))
            || document.communications.some(communication =>
              communication.evidence_links?.some(link => link.source_id === row.id));
          if (linked) {
            error('This source is linked to a product, eligibility check, route window, funding record or communication. Unlink or replace those references before removing the source.');
            return;
          }
          document.sources.splice(document.sources.indexOf(row), 1);
          changed(); renderEditor();
          }, 'quiet'))));
      function updateCardSearch() {
        summaryTitle.textContent = row.title || 'Untitled source';
        card.dataset.search = [row.title || '', row.url || '', row.notes || '']
          .join(' ').toLocaleLowerCase();
        updateSourceFilter();
      }
      title.input.addEventListener('input', updateCardSearch);
      url.input.addEventListener('input', updateCardSearch);
      notes.input.addEventListener('input', updateCardSearch);
      updateCardSearch();
      sourceList.append(card);
    }
    search.input.addEventListener('input', updateSourceFilter);
    panel.append(heading, search.wrap, resultCount, empty, sourceList);
    updateSourceFilter();
  }

  function newCampaign() { if (!busy && canReplace()) { apply(blank()); feedback.replaceChildren(); } }
  const savedPanel = h('section', {class: 'campaign-saved-panel', 'aria-label': 'Saved campaigns'},
    h('div', {class: 'campaign-section-heading'}, h('div', {}, h('h3', {}, 'Your campaigns'),
      h('p', {class: 'muted'}, 'Your latest saved campaign opens automatically. You can switch campaigns here at any time.')),
      newButton), savedList);
  const transfers = h('details', {class: 'campaign-transfers'}, h('summary', {}, 'Import or back up a campaign'), imported.wrap,
    h('div', {class: 'button-row'}, button('Export campaign backup', exportBackup, 'quiet'),
      button('Delete saved campaign', async () => {
        if (!savedId) { error('This campaign has not been saved.'); return; }
        if (!window.confirm('Delete this saved campaign? Export a backup first if you need a copy.')) return;
        try { await request('/api/campaigns/delete', {data: {id: savedId, revision}}); apply(blank()); await refreshShelf(); }
        catch (problem) { error(problem.message); }
      }, 'danger')), backupControls);
  root.append(h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'CAMPAIGNS'), h('h2', {}, 'Keep the whole application together.'),
    h('p', {}, 'Compare opportunities, map products and IP questions to funding routes, prepare answers and turn missing details into next actions. Saved locally, with your sources beside the work.')),
    h('div', {class: 'campaign-save-bar non-print', role: 'region', 'aria-label': 'Campaign save and preview'},
      h('div', {class: 'button-row'}, saveButton, prepareButton), status, feedback),
    practiceGuide, sectionNavigation, decisionCard, savedPanel, shelf, summary, fundingPanel, capacity, editor, transfers, output);
  status.textContent = dirty ? 'Unsaved changes' : savedId ? 'Saved on this computer' : 'Not saved yet';
  renderEditor(); renderSummary(); renderFunding();
  const existing = await refreshShelf();
  if (!seed.document && !seed.id && !seed.dirty && existing.length) {
    try {
      const latest = await request('/api/campaigns/' + existing[0].id);
      apply(latest.document, latest.id || existing[0].id, latest.revision, true);
      feedback.replaceChildren(notice('Most recently updated campaign opened. Choose a different one in Your campaigns, or start a new campaign.', 'success'));
    } catch (problem) { error('Could not reopen your latest campaign. ' + problem.message); }
  }
  // The app attaches this returned workspace before the next animation frame.
  // Discarded route renders never start an observer on detached controls.
  toolbarObserverFrame = requestAnimationFrame(() => {
    toolbarObserverFrame = null;
    if (!root.isConnected) return;
    toolbarObserver = new ResizeObserver(updateCampaignClearance);
    toolbarObserver.observe(root.querySelector('.campaign-save-bar'));
    toolbarObserver.observe(sectionNavigation);
    revealSelectedCampaignTab();
    updateCampaignClearance();
  });
  return root;
}
