/** Manual funding records and server-calculated totals; no client-side sums. */
import {h, field, selectField, safeLink} from './ui.js';
import {CEILING_CURRENCY_OPTIONS} from './campaign-currency.js';
import {campaignSourceSnapshotGuidance,
  campaignSourceSnapshotIssue} from './campaign-source-state.js';

export const FUNDING_AMOUNT_KEYS = Object.freeze(['target', 'requested', 'awarded', 'received']);
const claimKeys = ['eligibility_evidence', 'ceiling_evidence'];
const amountRecord = () => ({amount: null, currency: 'unconfirmed', source_id: '',
  source_url: '', source_quote: '', checked_at: '', notes: ''});
const claimRecord = () => ({source_id: '', source_url: '', source_quote: '', checked_at: '', evidence: ''});
const trackingRecord = () => ({round_key: '', benefit_type: 'unknown', eligibility: 'unknown',
  ceiling_scope: 'unknown', application_status: 'unknown', award_status: 'unknown',
  receipt_status: 'unknown', closure_reason: 'unknown',
  ...Object.fromEntries(FUNDING_AMOUNT_KEYS.map(key => [key, amountRecord()])),
  ...Object.fromEntries(claimKeys.map(key => [key, claimRecord()]))});

// Rendering an old record must not silently create new saved data.
export function fundingTrackingView(opportunity = {}) {
  const saved = opportunity.funding_tracking || {};
  const result = {...trackingRecord(), ...structuredClone(saved)};
  for (const key of FUNDING_AMOUNT_KEYS) result[key] = {...amountRecord(), ...saved[key]};
  for (const key of claimKeys) result[key] = {...claimRecord(), ...saved[key]};
  return result;
}

export function editFundingTracking(opportunity, path, value) {
  if (!opportunity.funding_tracking) opportunity.funding_tracking = fundingTrackingView(opportunity);
  const [key, child] = path;
  if (child) {
    const initial = FUNDING_AMOUNT_KEYS.includes(key) ? amountRecord() : claimRecord();
    opportunity.funding_tracking[key] = {...initial, ...opportunity.funding_tracking[key], [child]: value};
  } else opportunity.funding_tracking[key] = value;
}

export function selectFundingClaimSource(opportunity, key, source) {
  const current = fundingTrackingView(opportunity)[key];
  const sourceId = source?.id || '', sourceUrl = source?.url || '';
  const changedSource = current.source_id !== sourceId || current.source_url !== sourceUrl;
  editFundingTracking(opportunity, [key, 'source_id'], sourceId);
  editFundingTracking(opportunity, [key, 'source_url'], sourceUrl);
  if (changedSource) {
    editFundingTracking(opportunity, [key, 'source_quote'], '');
    editFundingTracking(opportunity, [key, 'checked_at'], '');
  }
  return changedSource;
}

export function selectFundingAmountSource(opportunity, key, source) {
  const current = fundingTrackingView(opportunity)[key];
  const sourceId = source?.id || '', sourceUrl = source?.url || '';
  const changedSource = current.source_id !== sourceId || current.source_url !== sourceUrl;
  editFundingTracking(opportunity, [key, 'source_id'], sourceId);
  editFundingTracking(opportunity, [key, 'source_url'], sourceUrl);
  if (changedSource) {
    editFundingTracking(opportunity, [key, 'source_quote'], '');
    // This is copied source-record metadata, never a checked amount assertion.
    editFundingTracking(opportunity, [key, 'checked_at'], source?.checked_at || '');
  }
  return changedSource;
}

export function fundingReferencesSource(opportunity, sourceId) {
  const tracking = opportunity.funding_tracking;
  return Boolean(tracking && [...FUNDING_AMOUNT_KEYS, ...claimKeys]
    .some(key => tracking[key]?.source_id === sourceId));
}

/** Guard the editor's cached view against edits, replacements and late replies. */
export function createFundingSummaryState() {
  const owner = {};
  let version = 0, sequence = 0, closed = false, pending = false;
  let summary = null, stale = false;
  return {
    get summary() { return summary; },
    get stale() { return stale; },
    get pending() { return pending; },
    get closed() { return closed; },
    edited() { version++; stale = Boolean(summary); },
    reset() { version++; sequence++; pending = false; summary = null; stale = false; },
    begin() { pending = true; return {owner, version, sequence: ++sequence}; },
    current(token) { return !closed && token.owner === owner
      && token.version === version && token.sequence === sequence; },
    accept(token, value) {
      if (!this.current(token)) return false;
      if (value?.schema !== 'sinter-funding-summary/v1') {
        throw new Error('The funding summary response is not supported. Your campaign is unchanged.');
      }
      summary = value; stale = false; return true;
    },
    finish(token) {
      if (closed || token.owner !== owner || token.sequence !== sequence) return false;
      pending = false; return true;
    },
    close() { closed = true; sequence++; pending = false; },
  };
}

const trackingChoices = [
  ['benefit_type', 'Benefit being tracked', [['unknown', 'Not confirmed'], ['cash', 'Cash'], ['credits', 'Credits']],
    'One benefit type per round is supported. Mixed cash-and-credit rounds need reconciliation and are not combined; no cash value is inferred for credits.'],
  ['eligibility', 'Applicant eligibility', [['unknown', 'Not checked'], ['eligible', 'Recorded eligible'], ['ineligible', 'Recorded ineligible']],
    'A manual claim. Link current eligibility wording and explain how it applies below. Sinter does not verify it.'],
  ['ceiling_scope', 'Who the advertised ceiling applies to', [['unknown', 'Not checked'], ['individual', 'One applicant / project'], ['program_pool', 'Whole programme pool']],
    'A programme pool is not an individual funding ceiling. Link the exact terms below.'],
  ['application_status', 'Application record', [['unknown', 'Not recorded'], ['not_applied', 'Not applied'], ['preparing', 'Preparing'], ['submitted', 'Submitted']],
    'Record an actual application state. A submitted application also needs Opportunity status set to Submitted in Edit opportunity details. Change both records yourself; contradictory states exclude requested amounts. Enquiries and preparation are not submissions.'],
  ['award_status', 'Award record', [['unknown', 'Not recorded'], ['not_awarded', 'Not awarded'], ['awarded', 'Awarded']],
    'Only record awarded when an award has been confirmed. An application is not an award.'],
  ['receipt_status', 'Receipt record', [['unknown', 'Not recorded'], ['not_received', 'Not received'], ['received', 'Received']],
    'Record actual received cash or credits separately from an award.'],
  ['closure_reason', 'Closed outcome', [['unknown', 'Not recorded'], ['round_closed', 'Round closed'], ['declined', 'Declined'], ['withdrawn', 'Withdrawn'], ['ineligible', 'Ineligible'], ['not_pursued', 'Not pursued'], ['other', 'Other recorded outcome']],
    'Retain the outcome for this round. Closing a route does not create an application, award or receipt.'],
];

export function fundingTrackingEditor(opportunity, {sources, sourcePicker, changed}) {
  const view = fundingTrackingView(opportunity);
  function text(label, path, type = 'text', help = '', props = {}, after = () => {}) {
    const value = path.length === 1 ? view[path[0]] : view[path[0]][path[1]];
    const entry = field(label, type, value ?? '', help, props);
    entry.input.dataset.fundingField = path.join('.');
    entry.input.addEventListener('input', () => {
      // Keep the entered decimal text intact for shared server validation.
      editFundingTracking(opportunity, path,
        type === 'number' && entry.input.value === '' ? null : entry.input.value);
      changed(); after();
    });
    return entry;
  }
  const round = text('Programme round key', ['round_key'], 'text',
    'Use the same exact key for repeated records of the same programme round. Duplicate keys are excluded from amounts until reviewed; do not split one round to inflate totals.', {maxLength: 200});
  const choices = trackingChoices.map(([key, label, options, help]) => {
    const entry = selectField(label, options, view[key], help);
    entry.input.dataset.fundingField = key;
    entry.input.addEventListener('change', () => {
      editFundingTracking(opportunity, [key], entry.input.value); changed();
    });
    return entry.wrap;
  });
  const amounts = FUNDING_AMOUNT_KEYS.map(key => {
    const title = ({target: 'Target', requested: 'Requested', awarded: 'Awarded', received: 'Received'})[key];
    const amount = text(title + ' amount', [key, 'amount'], 'number',
      'Enter the cumulative amount for this round, benefit and currency, not an individual instalment. Leave blank if unknown; zero is an explicit recorded zero. Amounts do not change event statuses.', {min: 0, step: '.01', max: 1_000_000_000});
    const currency = selectField(title + ' currency', CEILING_CURRENCY_OPTIONS, view[key].currency,
      'Choose the recorded denomination. No currency conversion is made.');
    currency.input.dataset.fundingField = key + '.currency';
    currency.input.addEventListener('change', () => {
      editFundingTracking(opportunity, [key, 'currency'], currency.input.value); changed();
    });
    const linked = h('p', {class: 'campaign-window-source', role: 'status'});
    function showLink() {
      const record = opportunity.funding_tracking?.[key] || view[key];
      const source = sources.find(row => row.id === record.source_id);
      const issue = campaignSourceSnapshotIssue(record.source_url, record.checked_at, source);
      linked.replaceChildren(source
        ? h('span', {}, 'Amount source · user-entered, unverified: ',
          source.url ? safeLink(source.url, source.title) : source.title,
          ' · ', issue ? campaignSourceSnapshotGuidance(issue)
            : 'Saved URL and check date match the source record; the amount and wording remain unverified.')
        : record.source_id ? 'The linked amount source is missing. Reconnect it before using this amount.'
          : 'No amount source linked.');
    }
    const url = text(title + ' source URL snapshot', [key, 'source_url'], 'url',
      'The selected saved URL is copied here. Keep the exact page for the amount wording.', {maxLength: 4000}, showLink);
    const quote = text(title + ' exact amount wording', [key, 'source_quote'], 'textarea',
      'Enter the exact relevant wording yourself; saved source notes are not copied as evidence.', {rows: 3, maxLength: 2000}, showLink);
    const date = text(title + ' amount wording checked date', [key, 'checked_at'], 'date',
      'Linking copies the saved source’s user-entered check date. Re-read this amount wording and correct the date before use.', {}, showLink);
    const picker = sourcePicker(title + ' amount source', view[key].source_id, source => {
      const reset = selectFundingAmountSource(opportunity, key, source);
      const record = opportunity.funding_tracking[key];
      url.input.value = record.source_url;
      if (reset) { quote.input.value = ''; date.input.value = record.checked_at; }
      showLink();
    });
    const notes = text(title + ' amount notes', [key, 'notes'], 'textarea',
      'Record the basis, conditions and whether this is a proposed or confirmed amount.', {rows: 2, maxLength: 2000});
    showLink();
    return h('details', {class: 'campaign-funding-amount'}, h('summary', {}, title + ' amount and source'),
      h('div', {class: 'form-grid'}, amount.wrap, currency.wrap), notes.wrap,
      h('details', {class: 'campaign-funding-amount-evidence'},
        h('summary', {}, title + ' amount evidence'),
        picker.wrap, linked, url.wrap, quote.wrap, date.wrap));
  });
  function claimEditor(key, title) {
    const status = h('p', {class: 'campaign-proof-status', role: 'status'});
    function currentClaim() { return opportunity.funding_tracking?.[key] || view[key]; }
    function showClaim() {
      const claim = currentClaim(), source = sources.find(row => row.id === claim.source_id);
      const issue = campaignSourceSnapshotIssue(claim.source_url, claim.checked_at, source);
      status.replaceChildren(h('span', {}, 'User-entered claim; Sinter has not verified this evidence. ',
        source ? [source.url ? safeLink(source.url, source.title) : source.title, ' · '] : [],
        !claim.source_id ? 'No saved evidence source linked. Add and link the official source before recording its exact wording.'
          : issue ? campaignSourceSnapshotGuidance(issue)
          : !claim.source_quote?.trim() || !claim.evidence?.trim()
            ? 'Add the exact wording and explain what it establishes.'
            : 'The saved URL and check date match the linked source record. This is not independent verification.'));
    }
    const url = text(title + ' source URL snapshot', [key, 'source_url'], 'url',
      'Keep the exact URL for the wording below. Link the saved source before recording its wording and check date.', {maxLength: 4000}, showClaim);
    const quote = text(title + ' exact source wording', [key, 'source_quote'], 'textarea',
      'Re-read the linked page and enter its exact relevant wording yourself.', {rows: 3, maxLength: 2000}, showClaim);
    const date = text(title + ' wording checked date', [key, 'checked_at'], 'date',
      'Record when you re-read this wording. It must match the linked source record to support availability.', {}, showClaim);
    const evidence = text(title + ' explanation', [key, 'evidence'], 'textarea',
      'Explain what this wording establishes for this applicant or ceiling. It remains a manual claim.', {rows: 2, maxLength: 2000}, showClaim);
    const source = sourcePicker(title + ' saved source', view[key].source_id, selected => {
      const reset = selectFundingClaimSource(opportunity, key, selected);
      const claim = currentClaim(); url.input.value = claim.source_url;
      if (reset) { quote.input.value = ''; date.input.value = ''; }
      showClaim();
    });
    showClaim();
    return h('details', {class: 'campaign-funding-claim'},
      h('summary', {}, title + ' evidence'),
      h('p', {class: 'fine'}, 'Choose the source first. Changing its ID or URL clears the previous wording and check date; the explanation is retained.'),
      source.wrap, status, url.wrap, quote.wrap, date.wrap, evidence.wrap);
  }
  return h('details', {class: 'campaign-funding-tracking'}, h('summary', {}, 'Funding tracking'),
    h('p', {class: 'fine'}, 'These are manual records, not eligibility verification or confirmed income. Available funding requires current eligibility and individual-ceiling evidence plus an open, current application window. Totals cover this campaign only.'),
    round.wrap, h('div', {class: 'form-grid'}, choices),
    claimEditor('eligibility_evidence', 'Eligibility'), claimEditor('ceiling_evidence', 'Individual ceiling'),
    h('p', {class: 'fine'}, 'The advertised ceiling stays in Edit opportunity details. Targets are plans; requested amounts belong to applications. Awarded and received amounts each need their own recorded status and source.'),
    amounts);
}

const stageLabels = [['available', 'Available'], ['targets', 'Targets'], ['submitted', 'Submitted'],
  ['awarded', 'Awarded'], ['received', 'Received'], ['closed', 'Closed']];
const stageHelp = {
  available: 'Eligible individual ceilings with current source claims and an open application window.',
  targets: 'Recorded planning amounts; no application or award is implied.',
  submitted: 'Requested amounts for recorded submitted applications.',
  awarded: 'Recorded confirmed award amounts; receipt is separate.',
  received: 'Recorded received cash or credits.',
  closed: 'Requested amounts of closed submitted applications; historical ceilings are excluded.',
};
const humanKey = value => String(value || 'unknown').replaceAll('_', ' ');
const decimalText = value => {
  const [integer, fraction] = String(value).split('.');
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction === undefined ? '' : '.' + fraction);
};

export function fundingGroupText(group) {
  const denomination = group.currency === 'unconfirmed' ? 'Currency not confirmed'
    : group.currency === 'other' ? 'Other currency · unsupported' : String(group.currency);
  const benefit = ({cash: 'Cash', credits: 'Credits', unknown: 'Benefit not confirmed'})[group.benefit_type]
    || 'Benefit not confirmed';
  const known = group.known_total == null ? 'Known subtotal unavailable'
    : denomination + ' ' + decimalText(group.known_total) + ' known subtotal';
  return {label: benefit + ' · ' + denomination, known,
    completeness: group.total == null ? 'Complete total unknown or excluded.' : 'Recorded group total is complete.'};
}

export function renderFundingSummary(summary) {
  const counts = summary.counts || {};
  const stages = stageLabels.map(([key, label]) => {
    const stage = summary.stages?.[key] || {opportunities: 0, groups: [], excluded_rows: 0};
    const groups = stage.groups.map(group => {
      const text = fundingGroupText(group);
      return h('div', {class: 'campaign-funding-group'}, h('strong', {}, text.label),
        h('p', {class: 'campaign-funding-subtotal'}, text.known),
        h('p', {class: 'fine'}, `${group.known_amounts} known · ${group.unknown_amounts} unknown · ${group.excluded_amounts} excluded amounts`),
        h('p', {class: 'fine'}, text.completeness));
    });
    return h('article', {class: 'campaign-funding-stage', 'data-funding-stage': key},
      h('h4', {}, label), h('p', {class: 'campaign-funding-count'},
        h('strong', {}, stage.opportunities), ' rounds / records'),
      h('p', {class: 'fine'}, stageHelp[key]),
      groups.length ? groups : h('p', {class: 'fine'}, 'No amounts included in this stage.'),
      h('p', {class: 'fine'}, `${stage.excluded_rows} excluded rows · see review details below`));
  });
  const duplicates = summary.duplicate_rounds || [], exclusions = summary.exclusions || [];
  const review = h('details', {class: 'campaign-funding-review'},
    h('summary', {}, 'Funding review details'),
    h('p', {class: 'fine'}, 'Each exclusion is calculated by Sinter from the recorded data. It is not a funding decision or independent verification.'),
    duplicates.length ? h('div', {}, h('h4', {}, 'Repeated programme rounds'),
      h('ul', {}, duplicates.map(row => h('li', {}, h('strong', {}, row.round_key),
        ': ', (row.opportunities || []).join(' · '))))) : null,
    exclusions.length ? h('div', {}, h('h4', {}, 'Excluded records'),
      h('ul', {}, exclusions.map(row => h('li', {}, h('strong', {}, row.opportunity),
        ' · ', humanKey(row.stage), ' · ', row.message || humanKey(row.reason)))))
      : h('p', {class: 'fine'}, 'No exclusion records returned.'),
    ...[['applications', 'Application records'], ['awards', 'Award records'], ['receipts', 'Receipt records'],
      ['closed_outcomes', 'Closed outcomes']].map(([key, label]) =>
      h('div', {}, h('h4', {}, label), h('dl', {class: 'campaign-funding-record-counts'},
        Object.entries(counts[key] || {}).map(([state, count]) =>
          h('div', {}, h('dt', {}, humanKey(state)), h('dd', {}, count)))))));
  return h('div', {}, h('p', {class: 'fine'},
    `Current campaign · calculated ${summary.as_of || 'date not returned'} · ${counts.opportunities ?? 'unknown'} opportunity records · ${counts.identified_rounds ?? 'unknown'} identified rounds`),
    h('p', {class: 'fine'}, summary.notice || 'Cash and credits stay separate. No currency conversion or grand total is calculated. Stages can overlap; do not add them together.'),
    counts.missing_round_keys ? h('div', {class: 'notice warning'},
      `${counts.missing_round_keys} routes have no programme round key. Their amounts are excluded until identified; possible repeated rounds cannot be resolved.`) : null,
    duplicates.length ? h('div', {class: 'notice warning'},
      `${counts.duplicate_rounds} repeated round keys · ${counts.duplicate_rows} additional duplicate rows. All amount records for those repeated rounds are excluded pending review.`) : null,
    h('div', {class: 'campaign-funding-stages'}, stages),
    h('p', {class: 'fine'}, 'Unknown and excluded amount counts can overlap when an unknown amount is also excluded.'), review);
}
