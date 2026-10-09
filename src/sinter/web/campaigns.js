/** A local, revisioned funding workspace. Every status is entered by a person. */
import {h, field, selectField, button, notice, download, announce, safeLink, check} from './ui.js';
import {request} from './api.js';
import {renderReport} from './reports.js';
import {campaignClarificationDraft, campaignIdentityFromProfile} from './campaign-letter.js';
import {defaultCampaignOpportunityIndex, isCampaignActionCurrent, isCampaignActionOpen,
  isCampaignActionScopeConfirmed, isOpportunityActionable,
  applicationAnswerAvailability, canDraftApplicationAnswer} from './campaign-state.js';
import {campaignAnswerCounts} from './campaign-answer-counts.js';
import {applicationWindowGaps, campaignDecision, CAMPAIGN_DECISION_NOTE} from './campaign-decision.js';
import {campaignRequirementNeedsReview} from './campaign-requirement-policy.js';
import {CAMPAIGN_ROUTE_PURPOSES, campaignRoutePurpose,
  campaignRoutePurposeLabel, campaignRoutePurposeConflict, isNonApplicationRoute}
  from './campaign-route-purpose.js';
import {campaignActionOwnerState, normalizeCampaignActionOwners} from './campaign-owner.js';
import {campaignSourceSnapshotGuidance,
  campaignSourceSnapshotIssue} from './campaign-source-state.js';
import {campaignActionRowsForCalendar, campaignActionRowsForPlan,
  normalizeCampaignActionScopes} from './campaign-plan.js';
import {gardenGuide, GARDEN_PRACTICE} from './garden-practice.js';
import {COMMUNICATION_ORDERS, COMMUNICATION_STATUSES}
  from './campaign-communication-view.js';
import {renderCampaignCommunications} from './campaign-communications.js';
import {campaignCapacity, CAMPAIGN_TEXT_LIMIT, CAMPAIGN_BYTE_LIMIT}
  from './campaign-capacity.js';
import {campaignSourceOptions, matchingCampaignSources}
  from './campaign-source-options.js';
import {selectRequirementSource} from './campaign-requirement-source.js';
import {assetSourceReplacement, sourceHistoryReferences, sourceHistoryCount,
  captureSourceReplacementGuard} from './campaign-source-history.js';
import {selectWindowSource} from './campaign-window-source.js';
import {campaignBackupControls, resetCampaignBackupControls} from './campaign-backup.js';
import {campaignFeedback} from './campaign-feedback.js';
import {acknowledgedCampaign} from './campaign-save.js';
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
  let admittingSave = false;
  let focusedCopyDialog = null;
  let sourceReplacementDialog = null;
  let disposed = false;
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
  let communicationStatus = COMMUNICATION_STATUSES.some(([value]) => value === seed.communicationStatus)
    ? seed.communicationStatus : 'all';
  let communicationOpenState = new WeakMap();
  let pendingAssetOpenId = '';
  let pendingFocus = null;
  let pendingActionFocus = null;
  const root = h('div', {class: 'campaign-page'}), shelf = h('div', {class: 'campaign-shelf'});
  const feedbackView = campaignFeedback(() => saveButton), {feedback} = feedbackView;
  const status = h('span', {class: 'campaign-save-state', role: 'status'});
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
    if (admittingSave) return;
    remember('campaigns', {document: structuredClone(document), id: savedId, revision,
      dirty, selected, tab, sourceQuery, assetQuery, communicationQuery,
      opportunityQuery, opportunityStatus, opportunityPage,
      communicationRoute, communicationOrder, communicationStatus, practice,
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
    disposed = true;
    sourceReplacementDialog?.close();
    if (focusedCopyDialog) {
      focusedCopyDialog.close(); focusedCopyDialog.remove(); focusedCopyDialog = null;
    }
    feedbackView.dispose();
    fundingState.close();
    toolbarObserver?.disconnect();
    window.removeEventListener('resize', updateCampaignClearance);
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
  function campaignSourcePicker(label, selectedId, onSelect, beforeSelect = null,
    selectionCurrent = () => true) {
    const options = campaignSourceOptions(document.sources);
    const selectedOption = options.find(option => option.source.id === selectedId);
    const listId = `campaign-source-options-${++sourcePickerSequence}`;
    const entry = field(label, 'search', selectedOption?.label || '',
      'Search by title or website, then use a Link source button. Typing does not change the link. Links stay unverified.', {
        autocomplete: 'off', placeholder: 'Search saved sources…',
      });
    entry.input.setAttribute('aria-controls', listId);
    const status = h('small', {class: 'campaign-source-picker-status', role: 'status'},
      selectedOption ? 'Source linked · unverified.'
        : options.length ? 'No campaign source linked.'
          : 'Add a source in the Sources tab first.');
    const matchStatus = h('small', {class: 'campaign-source-picker-status', role: 'status'});
    const matches = h('div', {class: 'campaign-source-matches', id: listId,
      role: 'group', 'aria-label': 'Matching saved campaign sources', hidden: true});
    function closeMatches() { matches.hidden = true; matchStatus.textContent = ''; }
    let selecting = false;
    async function selectSource(option) {
      if (selecting) return;
      selecting = true;
      try {
        // A cancelled or rejected replacement must not alter any picker control.
        if (beforeSelect && !await beforeSelect(option?.source || null)) return;
        // Admission can resolve just before another ready operation applies or
        // removes this editor. Recheck at the actual control/data commit boundary.
        if (disposed || !entry.input.isConnected || !selectionCurrent()) return;
        entry.input.value = option?.label || '';
        status.textContent = option ? 'Source linked · unverified.'
          : options.length ? 'No campaign source linked.' : 'Add a source in the Sources tab first.';
        clear.hidden = !option; closeMatches();
        onSelect(option?.source || null); changed();
        if (!option && entry.input.isConnected) entry.input.focus();
      } catch (exception) {
        error(exception.message || 'Could not change the source. Your local work is unchanged.');
      } finally { selecting = false; }
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
    const clear = button('Clear link', () => selectSource(null), 'quiet');
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
  function historicalSourceView(row) {
    const entries = row.source_history || [];
    const view = h('div', {class: 'campaign-source-history'});
    if (!entries.length) return view;
    view.append(h('details', {},
      h('summary', {}, `Historical sources (${entries.length}) · excluded from current checks`),
      h('p', {class: 'fine'}, 'Previous wording and assessments are retained exactly as entered. They are unverified historical records, not current eligibility or IP evidence. Full campaign backups and campaign notes include them; older previews may reject these backups.'),
      ...entries.map((entry, index) => h('details', {},
        h('summary', {}, `Historical snapshot ${index + 1} · source ${entry.reason}`),
        historicalSourceMaterial(entry)))));
    return view;
  }
  function historicalSourceMaterial(entry) {
    const labels = {opportunity: 'Previous route name', rule: 'Previous requirement',
      status: 'Previous user-entered assessment', evidence: 'Previous applicant evidence',
      source_id: 'Retained source ID', source_url: 'Previous source URL',
      source_quote: 'Previous source wording', checked_at: 'Previous check date (user-entered)',
      kind: 'Previous evidence type', title: 'Previous reference title', url: 'Previous source URL',
      excerpt: 'Previous source passage', notes: 'Previous reference note'};
    const material = h('div', {}, h('p', {class: 'fine'}, 'Historical · unverified · excluded from current checks.'));
    for (const [key, value] of Object.entries(entry.record)) {
      material.append(h('p', {}, h('strong', {}, labels[key] + ':' )),
        h('pre', {class: 'campaign-source-text'}, value || 'Blank as recorded.'));
    }
    if (entry.assessment) {
      const labels = {contributors_status: 'contributor', rights_status: 'rights',
        disclosure_status: 'disclosure', prior_art_status: 'prior-art'};
      const old = entry.assessment, label = labels[old.status_field];
      material.append(h('p', {}, h('strong', {}, `Previous ${label} assessment (unverified):`)),
        h('pre', {class: 'campaign-source-text'}, old.status));
      if (Object.hasOwn(old, 'date')) material.append(
        h('p', {}, h('strong', {}, `Previous ${label} date (user-entered):`)),
        h('pre', {class: 'campaign-source-text'}, old.date || 'Blank as recorded.'));
    }
    return material;
  }
  function proposedSourceMaterial(source) {
    const material = h('section', {'aria-label': 'Proposed source register record'},
      h('h3', {}, 'Proposed source · user-entered, unverified'),
      h('p', {class: 'fine'}, 'These are the full saved register fields. Its checked date and notes will not become the current passage or excerpt check date. Re-open the source and review the passage yourself.'));
    for (const [key, label] of [['id', 'Source ID'], ['title', 'Source title'],
      ['url', 'Source URL'], ['checked_at', 'Register checked date (user-entered)'],
      ['notes', 'Original source wording and notes']]) {
      material.append(h('p', {}, h('strong', {}, label + ':')),
        h('pre', {class: 'campaign-source-text'}, source[key] || 'Blank as recorded.'));
    }
    return material;
  }
  async function admitSourceReplacement(candidate, previous, nextSource, changes, isCurrent) {
    const returnFocus = root.ownerDocument.activeElement;
    async function admit() {
      // This route validates locally. Its report projection is never editor data.
      await request('/api/campaigns/prepare', {data: {document: candidate}});
      if (!isCurrent()) {
        throw new Error('The campaign changed while checking this replacement. Review the current record and choose the source again.');
      }
    }
    if (!previous) { await admit(); return true; }
    if (sourceReplacementDialog) return false;
    return new Promise(resolve => {
      let approved = false, closed = false, pending = false;
      const progress = h('div', {role: 'status', 'aria-live': 'polite'});
      const cancel = button('Cancel', () => dialog.close(), 'quiet');
      const replace = button(nextSource ? 'Replace source' : 'Clear source link', async () => {
        if (pending) return;
        pending = true; replace.disabled = true;
        progress.replaceChildren(h('p', {}, 'Checking local size and record limits…'));
        try {
          await admit();
          if (closed) return;
          approved = true; dialog.close();
        } catch (exception) {
          if (!closed) progress.replaceChildren(notice(
            (exception.message || 'This replacement could not be admitted.')
            + ' The source, picker and unsaved state are unchanged. Export a backup or reduce scope before trying again.', 'error'));
        } finally { pending = false; replace.disabled = false; }
      }, 'primary');
      const dialog = h('dialog', {class: 'action-confirmation campaign-focused-copy',
        'aria-labelledby': 'campaign-source-replacement-title'},
        h('h2', {id: 'campaign-source-replacement-title'}, nextSource ? 'Replace this source?' : 'Clear this source link?'),
        h('div', {class: 'campaign-focused-body', tabindex: 0, role: 'region',
          'aria-label': 'Source replacement and exact historical record'},
          h('p', {}, nextSource ? `New source: ${nextSource.title}.` : 'No campaign source will remain linked.'),
          h('p', {}, 'The previous record below will be preserved as historical, unverified evidence. The current passage and check date will be empty and need a fresh review. ', changes),
          h('p', {class: 'fine'}, 'Historical snapshots use the existing record and size limits. Nothing is saved or sent. Older previews may reject backups containing source history.'),
          nextSource ? proposedSourceMaterial(nextSource) : h('p', {}, 'Proposed source: no campaign source linked.'),
          historicalSourceMaterial(previous), progress),
        h('div', {class: 'button-row'}, cancel, replace));
      sourceReplacementDialog = dialog;
      dialog.addEventListener('close', () => {
        closed = true; dialog.remove();
        if (sourceReplacementDialog === dialog) sourceReplacementDialog = null;
        if (returnFocus?.isConnected) returnFocus.focus({preventScroll: true});
        resolve(approved);
      }, {once: true});
      root.ownerDocument.body.append(dialog); dialog.showModal(); cancel.focus();
    });
  }
  function remove(rows, item, label, onRemove = null) {
    return button(label, () => {
      if (onRemove) onRemove();
      rows.splice(rows.indexOf(item), 1); changed(); renderEditor();
    }, 'quiet');
  }
  function lock(value) { busy = value; setBusy(value); saveButton.disabled = value; prepareButton.disabled = value; newButton.disabled = value; fundingButton.disabled = value || fundingState.pending || fundingState.closed; editor.inert = value; decisionCard.inert = value; sectionNavigation.inert = value; transfers.inert = value; }
  function apply(next, id = null, rev = null, preferActionable = false, focusedRoute = '') {
    const resumeCurrentCampaign = Boolean(id && id === savedId);
    const previousTab = tab;
    const previousSelection = selected;
    const previousOpportunityName = document.opportunities?.[previousSelection]?.name || '';
    const previousSourceQuery = sourceQuery;
    const previousAssetQuery = assetQuery;
    const previousCommunicationView = {query: communicationQuery,
      route: communicationRoute, order: communicationOrder, status: communicationStatus};
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
    const explicitSelection = focusedRoute
      ? document.opportunities.findIndex(row => row.name === focusedRoute) : -1;
    selected = explicitSelection >= 0 ? explicitSelection : retainedSelection >= 0 ? retainedSelection : preferActionable
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
    communicationStatus = resumeCurrentCampaign ? previousCommunicationView.status : 'all';
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
  function admitSavedCampaign(reply) {
    // Some renderers add local defaults. Keep the decoded reply untouched as
    // evidence if a later renderer refuses the candidate.
    const saved = structuredClone(acknowledgedCampaign(reply));
    const before = {document, savedId, revision, dirty, selected, tab,
      sourceQuery, opportunityQuery, opportunityStatus, opportunityPage, assetQuery,
      communicationQuery, communicationRoute, communicationOrder, communicationStatus, communicationOpenState,
      budgetOpenState, expandedActionRows, pendingFocus, pendingActionFocus,
      pendingBudgetFocus, pendingAssetOpenId};
    const areas = [editor, sectionNavigation, shelf, summary, decisionCard];
    const children = areas.map(area => [...area.childNodes]);
    const oldCapacity = {text: capacity.textContent, className: capacity.className,
      state: capacity.getAttribute('data-capacity-state')};
    const oldStyle = root.getAttribute('style');
    admittingSave = true;
    try {
      const openCommunications = document.communications.map(row => communicationOpenState.get(row));
      const openBudgetRows = document.budget.map(row => budgetOpenState.get(row));
      document = saved.document; savedId = saved.id; revision = saved.revision; dirty = false;
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
      return saved;
    } catch (cause) {
      ({document, savedId, revision, dirty, selected, tab,
        sourceQuery, opportunityQuery, opportunityStatus, opportunityPage, assetQuery,
        communicationQuery, communicationRoute, communicationOrder, communicationStatus, communicationOpenState,
        budgetOpenState, expandedActionRows, pendingFocus, pendingActionFocus,
        pendingBudgetFocus, pendingAssetOpenId} = before);
      let rollbackError;
      try {
        areas.forEach((area, index) => area.replaceChildren(...children[index]));
        capacity.textContent = oldCapacity.text; capacity.className = oldCapacity.className;
        if (oldCapacity.state === null) capacity.removeAttribute('data-capacity-state');
        else capacity.setAttribute('data-capacity-state', oldCapacity.state);
        if (oldStyle === null) root.removeAttribute('style');
        else root.setAttribute('style', oldStyle);
      } catch (problem) { rollbackError = problem; }
      const failure = new Error('The save reply could not be opened. Your earlier campaign inputs are retained.'
        + (rollbackError ? ' Restoring the editor view also failed; back up the retained inputs before leaving.' : ''));
      failure.cause = cause; failure.partialResult = reply;
      if (rollbackError) failure.rollbackError = rollbackError;
      throw failure;
    } finally { admittingSave = false; }
  }
  async function save() {
    if (busy) return;
    if (captureBudgetDisclosures()) rememberCampaign();
    lock(true); feedback.replaceChildren();
    try {
      await request('/api/campaigns/save', {data: {document, id: savedId, revision},
        acceptResponse: admitSavedCampaign});
      fundingState.edited(); renderFunding();
      rememberCampaign();
      status.textContent = 'Saved on this computer';
      feedback.replaceChildren(notice('Campaign saved. Answers, costs, checks and actions will be here when you return.', 'success'));
      announce('Campaign saved.');
      try { await refreshShelf(); }
      catch (problem) {
        feedback.replaceChildren(notice('Campaign saved on this computer. Only the saved-campaign list could not be refreshed. You do not need to save again. ' + problem.message, 'warning'));
      }
    } catch (problem) {
      const state = problem.requestState;
      const saveRequest = state?.path === '/api/campaigns/save' && state.method === 'POST';
      const outcome = saveRequest && state.outcome === 'unconfirmed'
        ? ' The save may have finished, but Sinter did not receive confirmation. Back up these edits and check the saved campaign before explicitly choosing Save campaign again.'
        : saveRequest && state.outcome === 'not-sent' ? ' The save was not started.' : '';
      error(problem.message + outcome + ' Your edits are still here. Export a campaign backup or use Copy backup text under Import or back up a campaign before reopening another version.');
    }
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
  function focusedCopy(route, returnFocus) {
    if (busy || focusedCopyDialog) return;
    // Work on the complete editor snapshot, never a shareable report projection.
    const snapshot = structuredClone(document);
    const parent = {id: savedId, revision, dirty};
    let preview = null, pending = false, closed = false;
    const name = field('Name for the focused campaign', 'text',
      `${snapshot.title} — ${route}`, 'Choose a name for this separate copy.', {maxLength: 200});
    const wide = check('Also include campaign-wide actions, costs and communications');
    const assets = check('Include linked products and IP evidence, keeping all their route links');
    const sources = check('Also include every other source record from the original');
    const progress = h('div', {role: 'status', 'aria-live': 'polite'});
    const material = h('div', {class: 'campaign-focused-material'});
    const cancel = button('Cancel', () => dialog.close(), 'quiet');
    const downloadCopy = button('Download focused backup', () => {
      if (preview && !pending) download('sinter-focused-campaign.json',
        JSON.stringify(preview.document, null, 2), 'application/json');
    }, 'quiet');
    const open = button('Open unsaved focused campaign', () => {
      if (!preview || pending || !canReplace()) return;
      const next = structuredClone(preview.document);
      dialog.close();
      apply(next, null, null, false, route); changed();
      feedback.replaceChildren(notice('Focused copy opened with unsaved changes. No existing saved campaign was changed. Save campaign to create a separate record; nothing was sent or submitted.', 'success'));
      scrollCampaignTarget(status, true);
    }, 'primary');
    downloadCopy.disabled = true; open.disabled = true;
    const controls = [name.input, wide.input, assets.input, sources.input];
    function invalidate() {
      preview = null; material.replaceChildren(); progress.replaceChildren();
      downloadCopy.disabled = true; open.disabled = true;
    }
    for (const control of controls) control.addEventListener('input', invalidate);
    const inspect = button('Preview selected material', async () => {
      if (pending) return;
      invalidate(); pending = true; inspect.disabled = true;
      for (const control of controls) control.disabled = true;
      progress.textContent = 'Preparing a local copy preview. The original is unchanged.';
      try {
        const result = await request('/api/campaigns/focus', {data: {
          document: snapshot, opportunity: route, title: name.input.value, parent,
          options: {campaign_wide: wide.input.checked,
            linked_assets: assets.input.checked, all_sources: sources.input.checked},
        }});
        if (closed) return;
        preview = result;
        progress.replaceChildren(notice(result.notice));
        if (result.dependency_routes.length) material.append(notice(
          'Additional route records are included to preserve product links: '
          + result.dependency_routes.join('; ')
          + '. Their checks, answers, actions and communications are omitted unless they belong to the selected route.', 'warning'));
        const labels = {opportunities: 'Routes', requirements: 'Checks', answers: 'Answers',
          budget: 'Costs', actions: 'Actions', communications: 'Communications',
          assets: 'Products and IP', sources: 'Sources'};
        for (const [key, label] of Object.entries(labels)) {
          const kept = result.included[key], left = result.omitted[key];
          const rows = result.included_material[key].map((row, index) =>
            h('article', {class: 'campaign-focused-record'},
              h('h4', {}, row.rule || row.label || row.task || row.subject
                || row.name || row.title || row.item || `${label} row ${kept[index]}`),
              h('p', {class: 'fine'}, `Original row ${kept[index]}`
                + (row.status ? ' · Recorded status: ' + row.status.replaceAll('_', ' ') : '')),
              ...['text', 'content', 'evidence', 'source_quote', 'notes', 'fit', 'public_summary']
                .filter(field => typeof row[field] === 'string' && row[field])
                .map(field => h('p', {class: 'campaign-focused-record-text'}, row[field]))));
          material.append(h('details', {}, h('summary', {},
            `${label}: ${kept.length} included, ${left.length} omitted`),
          h('p', {class: 'fine'}, 'Original row numbers: included '
            + (kept.join(', ') || 'none') + '; omitted ' + (left.join(', ') || 'none') + '.'),
          h('h4', {}, 'Included material'),
          ...(rows.length ? rows : [h('p', {class: 'fine'}, 'None selected.')]),
          h('details', {}, h('summary', {}, 'Complete included records'),
            h('pre', {tabindex: 0}, JSON.stringify(result.included_material[key], null, 2))),
          h('details', {}, h('summary', {}, 'Omitted material — retained in the original'),
            h('pre', {tabindex: 0}, JSON.stringify(result.omitted_material[key], null, 2)))));
        }
        material.append(h('details', {}, h('summary', {}, 'Campaign details and added copy provenance'),
          h('pre', {tabindex: 0}, JSON.stringify(Object.fromEntries(Object.entries(result.document)
            .filter(([key]) => !Object.hasOwn(labels, key))), null, 2)),
          h('pre', {tabindex: 0}, JSON.stringify(result.document.sources.find(
            source => source.id === result.lineage_source_id), null, 2))));
        downloadCopy.disabled = false; open.disabled = false;
      } catch (problem) {
        if (!closed) progress.replaceChildren(notice(problem.message
          + ' The original and its edits are unchanged. Reduce the explicit selection; no material was truncated.', 'error'));
      } finally {
        pending = false; inspect.disabled = false;
        for (const control of controls) control.disabled = false;
      }
    }, 'quiet');
    const dialog = h('dialog', {class: 'action-confirmation campaign-focused-copy',
      'aria-labelledby': 'campaign-focused-title'},
    h('h2', {id: 'campaign-focused-title'}, 'Make a focused campaign'),
    h('div', {class: 'campaign-focused-body', tabindex: 0, role: 'region',
      'aria-label': 'Focused campaign selection and material'},
    h('p', {}, 'Selected route: ', h('strong', {}, route),
      '. Preview the full material before opening a separate unsaved copy. Statuses and historical evidence stay as recorded; copying does not verify them.'),
    name.wrap, wide.wrap, assets.wrap, sources.wrap,
    h('p', {class: 'fine'}, 'The organisation, objective and signatory details are copied as entered. Linked sources are always kept. Other-route work stays in the original.'),
    button('Download original snapshot backup', () => download('sinter-original-campaign-snapshot.json',
      JSON.stringify(snapshot, null, 2), 'application/json'), 'quiet'),
    inspect, progress, material),
    h('div', {class: 'button-row'}, cancel, downloadCopy, open));
    focusedCopyDialog = dialog;
    dialog.addEventListener('close', () => {
      closed = true; dialog.remove();
      if (focusedCopyDialog === dialog) focusedCopyDialog = null;
      if (returnFocus?.isConnected) returnFocus.focus({preventScroll: true});
    }, {once: true});
    root.ownerDocument.body.append(dialog);
    dialog.showModal(); name.input.focus();
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
      && campaignRequirementNeedsReview(row, localDate(), document.sources));
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
      && !isNonApplicationRoute(row)
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
      [quotes.length, 'cost records needing details'], [windows.length, 'application windows to verify'],
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
      if (busy || disposed) return;
      tab = 'overview'; rememberCampaign(); renderEditor();
      const focus = editor.querySelector('.campaign-focus') || editor;
      focus.tabIndex = -1; focus.focus({preventScroll: true});
      scrollCampaignTarget(focus);
    };
    const openRecordedAction = index => {
      if (busy || disposed) return;
      if (index !== undefined) {
        expandedActionRows ||= new WeakSet();
        const row = document.actions[index];
        if (row) expandedActionRows.add(row);
      }
      tab = 'actions'; rememberCampaign(); renderEditor();
      const recordedAction = index === undefined ? null
        : editor.querySelector(`[data-action-index="${index}"]`);
      const taskField = recordedAction?.querySelector('textarea');
      scrollCampaignTarget(taskField || recordedAction || editor);
      taskField?.focus({preventScroll: true});
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
        openRecordedAction(result.action.actionIndex);
      }, 'quiet'));
    const portfolio = result.portfolioAction;
    const otherWork = portfolio ? h('details', {class: 'campaign-decision-portfolio'},
      h('summary', {}, `Other route’s current work · ${portfolio.opportunity}`),
      h('p', {class: 'campaign-decision-task'}, portfolio.task),
      h('p', {class: 'campaign-decision-owner'}, portfolio.ownerStatus),
      portfolio.due ? h('p', {class: 'campaign-decision-date'},
        'Proposed target: ' + new Intl.DateTimeFormat('en-AU', {dateStyle: 'medium'})
          .format(new Date(portfolio.due + 'T12:00:00'))
          + (portfolio.due < localDate() ? ' · past — confirm or reset' : '')) : null,
      button('Open recorded action', () => openRecordedAction(portfolio.actionIndex), 'quiet')) : null;
    const otherActiveRoutes = document.opportunities.filter(row =>
      isOpportunityActionable(row.status) && row.name !== result.focusOpportunity);
    const otherRoutesNeedReview = otherActiveRoutes.filter(row =>
      campaignDecision(document, undefined, row.name).state === 'not_ready'
      || (isNonApplicationRoute(row) && document.requirements.some(check =>
        check.opportunity === row.name && campaignRequirementNeedsReview(
          check, localDate(), document.sources)))).length;
    const focusedRoute = document.opportunities.find(row => row.name === result.focusOpportunity);
    if (isNonApplicationRoute(focusedRoute) && isOpportunityActionable(focusedRoute.status)
        && result.action.source === 'suggested') {
      action.append(button('Add suggested action', () => {
        if (busy || disposed) return;
        const row = {opportunity: focusedRoute.name, scope_confirmed: true,
          submission_phase: 'pre_submission', task: result.action.task,
          owner: '', owner_kind: 'unassigned', owner_confirmed: false,
          due: '', status: 'open'};
        document.actions.push(row);
        expandedActionRows ||= new WeakSet(); expandedActionRows.add(row);
        pendingActionFocus = {index: document.actions.length - 1, field: 'task'};
        tab = 'actions'; changed(); renderEditor();
      }, 'quiet'));
    }
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
    if (otherWork) decisionCard.append(otherWork);
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
    if (disposed) return;
    const saveRegion = root.querySelector('.campaign-save-bar');
    const top = saveRegion ? Number.parseFloat(getComputedStyle(saveRegion).top) || 0 : 0;
    const navigationTop = (saveRegion?.getBoundingClientRect().height || 0) + top + 8;
    const clearance = navigationTop + sectionNavigation.getBoundingClientRect().height + 16;
    // When sticky controls leave less than one usable target, let them scroll
    // normally. Measure their unchanged natural heights to avoid mode oscillation.
    const scrolling = clearance + 44 > window.innerHeight;
    root.dataset.campaignChrome = scrolling ? 'scroll' : 'sticky';
    root.style.setProperty('--campaign-navigation-top', `${scrolling ? 0 : Math.ceil(navigationTop)}px`);
    root.style.setProperty('--campaign-scroll-clearance', `${scrolling ? 0 : Math.ceil(clearance)}px`);
    revealSelectedCampaignTab();
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
      h('p', {class: 'muted'}, 'Compare funding and support, or explicitly record a discussion or research route. Closed and paused routes stay visible as historical context.')), button('Add opportunity', addOpportunity, 'quiet')));
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
        const planning = isNonApplicationRoute(row);
        choose.append(...[h('strong', {}, row.name), h('span', {}, row.funder
          || (planning ? 'Counterpart not recorded' : 'Funder to confirm')),
          h('small', {}, planning ? campaignRoutePurposeLabel(row)
            : opportunityTypes.find(([key]) => key === row.route_type)?.[1] || 'Not classified'),
          !planning || row.ceiling != null ? h('small', {}, routeAmountLabel(row)) : null,
          h('small', {}, planning ? opportunityStates.find(([key]) => key === row.status)?.[1]
            || 'Recorded status' : opportunityTiming(row))].filter(child => child != null));
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
    const planning = isNonApplicationRoute(item);
    function rerenderRouteField(key) {
      const editOpen = focus.querySelector('.campaign-opportunity-editor')?.open;
      const recordsOpen = focus.querySelector('.campaign-application-records')?.open;
      renderEditor();
      const nextEditor = editor.querySelector('.campaign-opportunity-editor');
      if (nextEditor && editOpen !== undefined) nextEditor.open = editOpen;
      const nextRecords = editor.querySelector('.campaign-application-records');
      if (nextRecords && recordsOpen !== undefined) nextRecords.open = recordsOpen;
      const nextField = editor.querySelector(`[data-campaign-field="${key}"]`);
      if (key === 'application_mode') {
        for (let ancestor = nextField?.closest('details'); ancestor;
          ancestor = ancestor.parentElement?.closest('details')) ancestor.open = true;
      }
      nextField?.focus({preventScroll: true});
    }
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
      headerFunder.textContent = item.funder || (planning ? 'COUNTERPART NOT RECORDED' : 'FUNDER TO CONFIRM');
      headerName.textContent = item.name || 'Untitled opportunity';
      programme.replaceChildren(item.url ? safeLink(item.url, planning ? 'Open route reference' : 'Open programme guidance')
        : h('p', {class: 'fine'}, planning ? 'Reference link not added yet.' : 'Programme link not added yet.'));
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
      fitValue.textContent = item.fit || (planning
        ? 'Record the scope, what is known and the next question to check.'
        : 'Record which project option this opportunity could support and what needs checking.');
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
    const funder = input(planning ? 'Contact / counterpart' : 'Funder', 'text', item, 'funder', '', {maxLength: 300}, updateOpportunityView);
    const url = input(planning ? 'Reference page' : 'Programme page', 'url', item, 'url', '', {maxLength: 2000}, updateOpportunityView);
    const purpose = selectField('Route purpose', CAMPAIGN_ROUTE_PURPOSES,
      campaignRoutePurpose(item), 'Choose explicitly. Existing records are not classified automatically; this label does not confirm eligibility or an exemption from applying.');
    purpose.input.dataset.campaignField = 'purpose';
    purpose.input.addEventListener('change', () => {
      item.purpose = purpose.input.value; changed(); rerenderRouteField('purpose');
    });
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
      if (['discussion', 'research', 'application'].includes(campaignRoutePurpose(item))) rerenderRouteField('application_mode');
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
    const fit = input(planning ? 'Scope and open questions' : 'Project fit and timing', 'textarea', item, 'fit', planning
      ? 'Record the discussion or research scope and uncertainty. Internal notes are not automatically added to outgoing drafts.'
      : 'Which project option could this support? Record any exclusions or conditions before committing costs.', {rows: 3, maxLength: 6000}, updateOpportunityView);
    const applicationFields = h('div', {}, windowSourceInfo,
      h('p', {class: 'fine'}, 'Choose the official source before adding its exact window wording and check date. Changing or clearing the source resets both.'),
      windowSource.wrap, windowSourceChange,
      h('div', {class: 'form-grid'}, applicationMode.wrap, applicant.wrap),
      applicantConfirmation.wrap,
      h('div', {class: 'form-grid'}, windowKind.wrap, deadline.wrap, windowChecked.wrap, decision.wrap, ceiling.wrap, ceilingCurrency.wrap), windowQuote.wrap);
    const opportunityEditor = h('details', {class: 'campaign-opportunity-editor', open: !item.funder && !item.fit},
      h('summary', {}, 'Edit opportunity details'), h('div', {class: 'form-grid'}, name.wrap, funder.wrap, routeType.wrap), url.wrap,
      state.wrap, fit.wrap, planning ? h('details', {class: 'campaign-application-records'},
        h('summary', {}, 'Retained application and funding records'),
        h('p', {class: 'fine'}, 'These records remain intact. A discussion or research label does not establish that an application is unnecessary. Record a required application explicitly to restore its full checks.'), applicationFields) : applicationFields);
    const purposeConflict = campaignRoutePurposeConflict(item);
    const copyRoute = button('Make focused campaign…', () => focusedCopy(item.name, copyRoute), 'quiet');
    focus.append(...[h('header', {class: 'campaign-focus-heading'}, headerFunder, headerName, programme),
      copyRoute,
      purpose.wrap,
      purposeConflict ? notice(purposeConflict, 'warning') : null,
      h('dl', {class: 'campaign-opportunity-facts'},
        !planning || item.ceiling != null ? h('div', {}, h('dt', {}, 'Recorded funding amount / ceiling'), maximum) : null,
        !planning ? h('div', {}, deadlineLabel, deadlineValue) : null, !planning ? recordedDeadline : null,
        !planning ? h('div', {}, h('dt', {}, 'Application lead'), workflowValue) : null,
        h('div', {}, h('dt', {}, 'Decision timing'), decisionValue),
        h('div', {}, h('dt', {}, 'Status'), statusValue)),
      currencyComparison,
      h('div', {class: 'campaign-fit'}, h('strong', {}, planning ? 'Scope and open questions' : 'Project fit and timing'), fitValue),
      opportunityEditor,
      planning ? h('details', {}, h('summary', {}, 'Retained funding history'),
        fundingTrackingEditor(item, {sources: document.sources, sourcePicker: campaignSourcePicker, changed}))
        : fundingTrackingEditor(item, {sources: document.sources, sourcePicker: campaignSourcePicker, changed})].filter(child => child != null));
    updateOpportunityView();
    const requirements = h('div', {class: 'campaign-checks'});
    function addRequirement() {
      if (sourceHistoryCount(document.requirements) >= 200) {
        error('Use at most 200 requirement records including historical source snapshots. Export a backup before reducing scope.'); return;
      }
      document.requirements.push({opportunity: item.name, rule: '', status: 'unknown', evidence: '', source_id: '', source_url: '', source_quote: '', checked_at: ''}); changed(); renderEditor();
    }
    requirements.append(h('div', {class: 'campaign-section-heading'}, h('h4', {}, 'What must be true?'), button('Add requirement', addRequirement, 'quiet')),
      h('p', {class: 'fine'}, planning
        ? 'Retain the conditions and questions relevant to this route. Review their original source and uncertainty; no agreement or research conclusion is established.'
        : 'Check each condition against current official guidance. These records do not determine overall eligibility.'));
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
      let approvedSelection = null;
      const sourceHistory = historicalSourceView(row);
      const sourcePicker = campaignSourcePicker('Registered campaign source (optional)',
        row.source_id, linked => {
        const selection = approvedSelection;
        approvedSelection = null;
        const historyRetained = (selection.requirement.source_history || []).length
          > (row.source_history || []).length;
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
            ? 'Source link changed. Your explanatory note is kept; recheck it against this source.'
              + (historyRetained ? ' Previous source wording is retained in Historical sources.' : '')
            : 'Source link cleared. Your explanatory note is kept'
              + (historyRetained ? '; previous wording and check date are retained in Historical sources.' : '.'))
            + (selection.resetAssessment ? ' The previous assessment was reset to Not checked.' : '')
          : '';
          sourceHistory.replaceChildren(...historicalSourceView(row).childNodes);
          updateProof();
        }, async linked => {
          const selection = selectRequirementSource(row, linked);
          if (!selection.changedSource) return false;
          const index = document.requirements.indexOf(row);
          if (index < 0) return false;
          const candidate = structuredClone(document);
          candidate.requirements[index] = structuredClone(selection.requirement);
          const isCurrent = captureSourceReplacementGuard(document, row, () => document,
            () => !disposed && root.isConnected);
          const history = selection.requirement.source_history || [];
          const previous = history.length > (row.source_history || []).length ? history.at(-1) : null;
          if (!await admitSourceReplacement(candidate, previous, linked,
            selection.resetAssessment ? 'The previous assessment will become Not checked.' : 'Your explanatory note and open assessment remain as entered.', isCurrent)) return false;
          approvedSelection = {...selection, isCurrent}; return true;
        }, () => Boolean(approvedSelection?.isCurrent()));
      source.input.disabled = Boolean(row.source_id);
      if (row.source_id) date.wrap.querySelector('label').textContent = 'Date checked for this excerpt · must match linked source';
      updateProof();
      const heading = h('summary', {}, h('span', {class: 'campaign-check-title'}, row.rule || 'New requirement'), stateLabel, preview);
      rule.input.addEventListener('input', () => { heading.querySelector('.campaign-check-title').textContent = row.rule || 'New requirement'; });
      requirements.append(h('details', {class: 'campaign-requirement', open: !row.rule}, heading,
        h('article', {class: 'campaign-check-editor', 'aria-label': 'Requirement check'}, rule.wrap, status.wrap, proof, reason.wrap,
        h('details', {open: Boolean(row.source_id || row.source_url || row.source_quote)},
          h('summary', {}, 'Supporting source · user-entered, unverified'),
          sourcePicker.wrap, sourceChange, sourcePreview, source.wrap, quote.wrap, date.wrap), sourceHistory,
        remove(document.requirements, row, 'Remove requirement'))));
    }
    if (!document.requirements.some(row => row.opportunity === item.name)) requirements.append(h('p', {class: 'fine'}, planning
      ? 'No checks recorded yet. Start with the question to clarify and the source or counterpart that could resolve it.'
      : 'No requirements checked yet. Start with applicant type, timing and permitted costs.'));
    const existingDraftCount = document.communications.filter(row =>
      row.opportunity === item.name && row.direction === 'outgoing' && row.status === 'draft').length;
    if (existingDraftCount) {
      requirements.append(h('p', {class: 'campaign-draft-existing'},
        `${existingDraftCount} unsent clarification draft${existingDraftCount === 1 ? '' : 's'} already recorded for this route. Review them in Communications before creating another; a new draft will be saved as a separate record.`));
    }
    requirements.append(button(existingDraftCount ? 'Create another clarification letter' : 'Draft clarification letter', () => {
      const conflict = campaignRoutePurposeConflict(item);
      if (conflict) { error(conflict + ' Resolve this local record before creating a clarification letter.'); return; }
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
    const canUse = answerAccess.allowed;
    const canDraft = canDraftApplicationAnswer(selectedOpportunity);
    panel.append(opportunityPicker(renderEditor));
    if (!canUse) panel.append(notice(answerAccess.message, 'warning'));
    const addQuestion = button('Add application question', () => {
      document.answers.push({opportunity, label: '', text: '', limit: null, status: 'draft'}); changed(); renderEditor();
    }, 'quiet');
    addQuestion.disabled = !canDraft;
    panel.append(addQuestion);
    for (const row of document.answers.filter(row => row.opportunity === opportunity)) {
      let previousQuestion = row.label;
      let previousLimit = row.limit == null ? null : Number(row.limit);
      const resetReview = () => { row.status = 'draft'; reviewed.input.value = 'draft'; };
      const label = input('Application question', 'textarea', row, 'label', 'Copy the actual wording from the application form.', {rows: 2, maxLength: 300}, element => {
        if (element.value !== previousQuestion) resetReview();
        previousQuestion = element.value;
      });
      label.input.disabled = !canDraft;
      const counter = h('p', {class: 'campaign-character-count', role: 'status'});
      function update() {
        const {characters: used, words} = campaignAnswerCounts(row.text || '');
        const limit = Number(row.limit);
        const characterStatus = limit > 0 ? `${used} / ${limit} characters${used > limit ? ' · ' + (used - limit) + ' over — shorten before using' : ' · within limit'}` : `${used} characters · confirm the form’s limit`;
        counter.textContent = `${characterStatus} · about ${words} ${words === 1 ? 'word' : 'words'}`;
        counter.classList.toggle('over-limit', limit > 0 && used > limit);
      }
      const limit = input('Character limit', 'number', row, 'limit', 'Character limits only. For a word limit, leave this blank and check the portal’s word counter.', {min: 1, max: 20000, step: 1}, element => {
        row.limit = element.value ? Number(element.value) : null;
        if (row.limit !== previousLimit) resetReview();
        previousLimit = row.limit;
        update();
      });
      limit.input.disabled = !canDraft;
      const answer = input('Draft answer', 'textarea', row, 'text',
        canDraft ? '' : answerAccess.message,
        {rows: 5, maxLength: 20000, readOnly: !canDraft,
          placeholder: canDraft ? '' : 'Saved answer held until this route is confirmed.'},
        () => { row.status = 'draft'; reviewed.input.value = 'draft'; update(); });
      if (!canDraft) answer.input.value = '';
      const reviewed = choice('Answer review', [['draft', 'Needs review'], ['reviewed', 'Reviewed by me']], row, 'status');
      reviewed.input.disabled = !canUse;
      const copied = h('p', {class: 'fine', 'aria-live': 'polite'});
      update();
      const copy = button(answerAccess.copyLabel, async () => {
        try { await navigator.clipboard.writeText(row.text); copied.textContent = row.limit && countCharacters(row.text) > row.limit ? 'Copied as written. Shorten this draft before pasting it into the application.' : 'Answer copied.'; }
        catch { error('Clipboard access is unavailable. Export the campaign brief instead.'); }
      }, 'quiet');
      copy.disabled = !canUse;
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
        'Recorded amounts may be quotes or planning estimates; GST bases may differ or be unknown. No GST conversion was made. Sinter has not qualified an application budget.'),
      h('div', {class: 'button-row'}, nextCost, button('Add budget item', () => {
        const selectedRoute = document.opportunities[selected];
        const row = {item: '', opportunity: actionable.has(selectedRoute?.name) ? selectedRoute.name : '',
          quantity: 1, unit_cost: null, quote_reference: ''};
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
        'For a quote, record the supplier, quote date, GST basis and original. For an estimate, record its author, date and basis. References are unverified.', {rows: 3, maxLength: 2000}, revised);
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
          {rows: 3, maxLength: 2000}, () => refreshActionSummary());
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
    const view = {
      get query() { return communicationQuery; }, set query(value) { communicationQuery = value; },
      get route() { return communicationRoute; }, set route(value) { communicationRoute = value; },
      get order() { return communicationOrder; }, set order(value) { communicationOrder = value; },
      get status() { return communicationStatus; }, set status(value) { communicationStatus = value; },
    };
    renderCampaignCommunications(panel, {document, view, openState: communicationOpenState,
      editor, input, choice, changed, renderEditor, rememberCampaign, error, remove,
      scopeChoices, campaignSourcePicker});
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
          if (sourceHistoryCount(refs) >= 20) { error('Each product or asset can have up to 20 evidence references including historical source snapshots. Export a backup before reducing scope.'); return; }
          refs.push({kind: 'other', source_id: '', title: '', url: '',
            excerpt: '', checked_at: '', notes: ''});
          pendingFocus = {assetId: row.id, field: 'source_id', referenceIndex: refs.length - 1};
          changed(); renderEditor();
        }, 'quiet'));
      for (const [referenceIndex, reference] of refs.entries()) {
        const referenceKind = choice('Evidence type', assetReferenceKinds,
          reference, 'kind');
        let approvedSelection = null;
        const sourceChoice = campaignSourcePicker('Link a campaign source (optional)',
          reference.source_id, source => {
            Object.assign(reference, approvedSelection.reference);
            Object.assign(row, approvedSelection.assetChanges);
            approvedSelection = null;
            pendingFocus = {assetId: row.id, field: 'excerpt', referenceIndex};
            renderEditor();
          }, async source => {
            const selection = assetSourceReplacement(reference, source, row);
            if (!selection.changedSource) return false;
            const index = document.assets.indexOf(row);
            if (index < 0 || refs[referenceIndex] !== reference) return false;
            const candidate = structuredClone(document);
            Object.assign(candidate.assets[index], selection.assetChanges);
            candidate.assets[index].references[referenceIndex] = structuredClone(selection.reference);
            const isCurrent = captureSourceReplacementGuard(document, reference, () => document,
              () => !disposed && root.isConnected, row);
            const history = selection.reference.source_history || [];
            const previous = history.length > (reference.source_history || []).length ? history.at(-1) : null;
            if (!await admitSourceReplacement(candidate, previous, source,
              Object.keys(selection.assetChanges).length
                ? 'The associated IP workstream assessment and its date will need a fresh review. Other workstreams and the product stage remain as entered.'
                : 'Other product records remain as entered.', isCurrent)) return false;
            approvedSelection = {...selection, isCurrent}; return true;
          }, () => Boolean(approvedSelection?.isCurrent()));
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
          historicalSourceView(reference),
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
            reference => reference.source_id === row.id || sourceHistoryReferences(reference, row.id)))
            || document.requirements.some(requirement => requirement.source_id === row.id || sourceHistoryReferences(requirement, row.id))
            || document.opportunities.some(opportunity => opportunity.window_source_id === row.id)
            || document.opportunities.some(opportunity => fundingReferencesSource(opportunity, row.id))
            || document.communications.some(communication =>
              communication.evidence_links?.some(link => link.source_id === row.id));
          if (linked) {
            error('This source is retained by a current or historical product reference, eligibility check, route window, funding record or communication. Keep it while those records are retained. Export a full backup before reducing scope.');
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
  root.append(h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'CAMPAIGNS'), h('h2', {}, 'Keep the whole campaign together.'),
    h('p', {}, 'Compare opportunities, map products and IP questions to funding routes, prepare answers and turn missing details into next actions. Saved locally, with your sources beside the work.')),
    h('div', {class: 'campaign-save-bar non-print', role: 'region', 'aria-label': 'Campaign save and preview'},
      h('div', {class: 'button-row'}, saveButton, prepareButton), status, feedbackView.panel),
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
    // A height-only resize may not change either observed element's dimensions.
    window.addEventListener('resize', updateCampaignClearance);
    if (typeof ResizeObserver === 'function') {
      toolbarObserver = new ResizeObserver(updateCampaignClearance);
      toolbarObserver.observe(root.querySelector('.campaign-save-bar'));
      toolbarObserver.observe(sectionNavigation);
    } else {
      toolbarObserver = new MutationObserver(updateCampaignClearance);
      const changes = {childList: true, characterData: true, attributes: true, subtree: true};
      toolbarObserver.observe(root.querySelector('.campaign-save-bar'), changes);
      toolbarObserver.observe(sectionNavigation, changes);
    }
    revealSelectedCampaignTab();
    updateCampaignClearance();
  });
  return root;
}
