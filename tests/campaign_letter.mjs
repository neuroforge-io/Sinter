import test from 'node:test';
import assert from 'node:assert/strict';
import * as letters from '../src/sinter/web/campaign-letter.js';

test('explicit discussion and research drafts retain checks without grant boilerplate', () => {
  for (const purpose of ['discussion', 'research']) {
    const route = {name: 'nbn Grants Program — exploratory conversation',
      purpose, application_mode: 'unknown', funder: 'Recorded counterpart'};
    const campaign = {objective: 'PRIVATE OBJECTIVE', requirements: [
      {opportunity: route.name, rule: 'Who can review the proposed scope?', status: 'unknown'},
      {opportunity: route.name, rule: 'Background IP permission', status: 'not_met'},
    ]};
    const before = structuredClone(campaign);
    const draft = letters.campaignClarificationDraft(campaign, route);
    assert.equal(draft.recipient, 'Recorded counterpart');
    assert.match(draft.questions, /Who can review the proposed scope\?/);
    assert.match(draft.questions, /Background IP permission/);
    assert.doesNotMatch(draft.questions, /applicant|application|registration|intake|permitted costs|We will obtain/);
    assert.doesNotMatch(JSON.stringify(draft), /PRIVATE OBJECTIVE/);
    assert.deepEqual(campaign, before);
    const empty = letters.campaignClarificationDraft({requirements: []},
      {...route, funder: ''});
    assert.equal(empty.recipient, '');
    assert.doesNotMatch(empty.questions, /eligibility|application timetable/);
    assert.match(empty.questions, purpose === 'research' ? /sources and scope/ : /useful next step/);
  }
});

test('required workflow retains formal clarification despite a planning purpose', () => {
  for (const purpose of ['discussion', 'research']) {
    const route = {name: 'Formal programme', purpose, application_mode: 'required'};
    const draft = letters.campaignClarificationDraft({requirements: []}, route);
    assert.match(draft.questions, /legal entity types may apply/);
    assert.match(draft.questions, /fixed or rolling intake/);
    assert.match(draft.questions, /official programme guidance/);
  }
});

test('missing purpose does not infer discussion from no formal application recorded', () => {
  const route = {name: 'Customer conversation', application_mode: 'not_required'};
  const draft = letters.campaignClarificationDraft({requirements: []}, route);
  assert.match(draft.questions, /fixed or rolling intake/);
  assert.equal(Object.hasOwn(route, 'purpose'), false);
});

test('private and store-only checks remain local for every route purpose', () => {
  for (const purpose of [undefined, 'application', 'discussion', 'research']) {
    const route = {name: 'Fictional route', application_mode: 'unknown',
      ...(purpose ? {purpose} : {})};
    const rule = 'PRIVATE INTERNAL CHECK — do not include: confidential pricing floor with our lawyer';
    const campaign = {requirements: [{opportunity: route.name, rule, status: 'unknown'},
      {opportunity: route.name, rule: 'Background IP permission',
        evidence: 'Store only; confidential agreement discussion', status: 'not_met'},
      {opportunity: route.name, rule: 'Privately confirm director authority with counsel', status: 'unknown'},
      {opportunity: route.name, rule: 'PRIVATE: keep this pricing ceiling local', status: 'unknown'},
      {opportunity: route.name, rule: 'INTERNAL ONLY: do not send this negotiation floor', status: 'unknown'}]};
    const before = structuredClone(campaign);
    const draft = letters.campaignClarificationDraft(campaign, route);
    assert.equal(draft.openCount, 5);
    assert.doesNotMatch(draft.questions, /pricing|confidential|PRIVATE|Background IP|licence|Privately|negotiation floor/);
    assert.deepEqual(campaign, before);
  }
});

test('clarification drafts contain only the selected opportunity and its open checks', () => {
  const campaign = {
    objective: 'CAMPAIGN_WIDE_SECRET_CONTEXT',
    organisation: 'Fictional School Community Association',
    signatory: '', sender_role: '', contact_details: '',
    opportunities: [],
    requirements: [
      {opportunity: 'School-led swimming 2027', rule: 'Registered school and portal access confirmed', status: 'unknown'},
      {opportunity: 'School-led swimming 2027', rule: 'Eligible costs and supporting quotes', status: 'met'},
      {opportunity: 'School-led swimming 2027', rule: 'Already fully checked', status: 'met',
        evidence: 'Reviewed', source_url: 'https://example.invalid/current', source_quote: 'Exact wording', checked_at: '2026-09-29'},
      {opportunity: 'Unrelated venue grant', rule: 'OTHER_OPPORTUNITY_RULE', status: 'unknown'},
    ],
  };
  const opportunity = {name: 'School-led swimming 2027', funder: 'Example Schools Programme',
    fit: 'School-led swimming sessions for 2027.'};
  const draft = letters.campaignClarificationDraft(campaign, opportunity);
  assert.equal(draft.openCount, 2);
  assert.equal(draft.recipient, 'Example Schools Programme');
  assert.equal(draft.title, 'Clarification: School-led swimming 2027');
  assert.equal(draft.notes, '');
  assert.match(draft.questions, /Could you confirm the current requirement for “Registered school and portal access confirmed” and what evidence we should provide\?/);
  assert.match(draft.questions, /Could you confirm the current requirement for “Eligible costs and supporting quotes” and what evidence we should provide\?/);
  for (const excluded of ['CAMPAIGN_WIDE_SECRET_CONTEXT', 'OTHER_OPPORTUNITY_RULE', 'Unrelated venue grant', 'Already fully checked']) {
    assert.equal(JSON.stringify(draft).includes(excluded), false, excluded);
  }
});

test('question titles are grammatical, bounded and sanitized', () => {
  assert.equal(letters.clarificationQuestion('What counts as an eligible applicant'), 'What counts as an eligible applicant?');
  assert.equal(letters.clarificationQuestion(''), '');
  assert.match(letters.clarificationQuestion('Operating age: six months on the SME page; one year in the FAQ'),
    /saved source notes differ.*Which current rule applies/);
  const long = letters.clarificationQuestion('A'.repeat(500));
  assert.ok(long.length < 350);
  assert.equal(long.includes('\n'), false);
});

test('RUIC clarification drafts use only current campaign facts and attach stable route evidence', () => {
  const opportunity = {name: 'CSIRO RUIC — matched Digital Tech & AI research voucher',
    funder: 'CSIRO / Queensland Government',
    url: 'https://www.csiro.au/en/work-with-us/funding-programs/SME/RUIC/SMEs',
    fit: 'Possible language-only evaluation; partner, budget and scope remain unconfirmed.'};
  const campaign = {organisation: 'NeuroforgeIO Pty Ltd', objective: 'PORTFOLIO_WIDE_PRIVATE_CONTEXT', requirements: [
    {opportunity: opportunity.name,
      rule: 'Queensland company eligibility: ABN, GST, operating age and financial threshold',
      evidence: 'The SME page and October 2025 guidelines say six months; the FAQ and programme comparison page say one year.',
      status: 'unknown'},
    {opportunity: opportunity.name,
      rule: 'Cash match: secure 1:1 company cash contribution for proposed RUIC amount',
      evidence: 'The voucher requires a 1:1 cash match.', source_id: 'b'.repeat(32), status: 'unknown'},
    {opportunity: opportunity.name,
      rule: 'Eligible research project, university partner and negotiated IP terms',
      evidence: 'A Queensland university partner and IP terms are not confirmed.', source_id: 'c'.repeat(32), status: 'unknown'},
    {opportunity: opportunity.name,
      rule: 'Public disclosure and publicity conditions',
      evidence: 'Publication obligations need review before applying.', source_id: 'c'.repeat(32), status: 'unknown'},
  ],
  sources: [
    {id: 'a'.repeat(32), title: 'CSIRO RUIC FAQ',
      url: 'https://www.csiro.au/en/work-with-us/funding-programs/SME/RUIC/Frequently-Asked-Questions', notes: 'Official FAQ.'},
    {id: 'b'.repeat(32), title: 'CSIRO SME Connect programme comparison',
      url: 'https://www.csiro.au/en/work-with-us/funding-programs/sme/sme-connect-programs'},
    {id: 'c'.repeat(32), title: 'RUIC Program & Eligibility Guidelines v1.2',
      url: 'https://www.csiro.au/-/media/SME-Connect/RUIC/RUIC-Program-Eligibility-Guidelines.pdf'},
    {id: 'd'.repeat(32), title: 'Unrelated source', url: 'https://example.invalid/other'},
  ]};
  campaign.requirements[0].source_id = 'a'.repeat(32);
  campaign.requirements[0].source_quote = 'At least six months operating; special conditions may apply.';
  const draft = letters.campaignClarificationDraft(campaign, opportunity,
    {id: 'c'.repeat(32), revision: 7, opportunity: opportunity.name, dirty: false});
  assert.equal(draft.recipient, 'CSIRO RUIC programme team');
  assert.equal(draft.title, 'Clarification: CSIRO RUIC — matched Digital Tech & AI research voucher');
  assert.equal(draft.notes, '');
  assert.match(draft.questions, /saved source notes differ.*operating or trading period/);
  assert.match(draft.questions, /financial thresholds or periods.*financial test and period.*regional status/);
  assert.match(draft.questions, /cash contribution is required.*matching ratio.*which costs qualify/);
  assert.match(draft.questions, /which project types and durations are eligible.*background IP, project IP and confidentiality/);
  assert.match(draft.questions, /publication or publicity conditions.*approval process/);
  assert.equal(draft.campaign_link.evidence_links.length, 4);
  assert.deepEqual(draft.campaign_link.evidence_links.map(link => link.url), [
    opportunity.url,
    'https://www.csiro.au/en/work-with-us/funding-programs/SME/RUIC/Frequently-Asked-Questions',
    'https://www.csiro.au/en/work-with-us/funding-programs/sme/sme-connect-programs',
    'https://www.csiro.au/-/media/SME-Connect/RUIC/RUIC-Program-Eligibility-Guidelines.pdf',
  ]);
  assert.match(draft.campaign_link.evidence_links[1].notes, /user-entered, unverified/);
  assert.equal(draft.campaign_link.evidence_links[1].source_id, 'a'.repeat(32));
  assert.equal(JSON.stringify(draft).includes('Unrelated source'), false);
});

test('a P&C route cannot receive NeuroForge names, products or campaign context', () => {
  const opportunity = {name: 'CSIRO RUIC community education route', funder: 'CSIRO',
    url: 'https://example.invalid/route', fit: 'Explore school swimming safety resources.',
    application_mode: 'required', applicant: 'Warraburra State School P&C',
    applicant_confirmed: true,
    application_window: 'rolling', window_source_quote: 'Accepts applications year round.',
    window_checked_at: '2026-09-29', status: 'open'};
  const campaign = {organisation: 'Warraburra State School P&C',
    objective: 'School swimming participation for local students.', requirements: []};
  const draft = letters.campaignClarificationDraft(campaign, opportunity,
    {id: 'f'.repeat(32), revision: 1, opportunity: opportunity.name, dirty: false},
    '2026-09-30');
  const encoded = JSON.stringify(draft);
  assert.match(encoded, /Warraburra State School P&C/);
  for (const leaked of ['school swimming safety resources', 'NeuroforgeIO', 'NeuroForge',
    'model-conversion', 'hardware resource use']) {
    assert.equal(encoded.includes(leaked), false, leaked);
  }
});

test('nbn clarification groups related checks and excludes internal campaign notes', () => {
  const name = 'nbn Grants Program — closing 12 Oct 2026';
  const campaign = {organisation: 'NeuroforgeIO Pty Ltd', requirements: [
    ['Applicant location is regional or remote for this programme', 'Public information identifies Queensland only.'],
    ['Applicant is connected to the nbn', 'No current service/address evidence is confirmed.'],
    ['Applicant holds an Australian business number (ABN)', 'ABN evidence is not independently checked.'],
    ['Business holds an Australian bank account corresponding to its ABN', 'No approved confirmation is recorded.'],
    ['Confirm registered business address is eligible regional/remote and nbn-connected.', 'Address intentionally not stored.'],
    ['Confirm ABN-linked Australian bank account and company authority privately before any application.', 'Bank account and signatory authority are not recorded.'],
    ['Director and lawyer review warranties, data sharing and the broad licence for application/reporting material.', 'No terms accepted or application submitted.'],
  ].map(([rule, evidence]) => ({opportunity: name, rule, evidence, status: 'unknown'}))};
  // The official excerpt also discusses regional service eligibility. That
  // language must not swallow a separate unresolved licence/IP requirement.
  campaign.requirements.at(-1).source_quote = 'Businesses must be located in regional or remote Australia and connected to nbn. The programme receives an exclusive, perpetual licence to use application and reporting material.';
  const opportunity = {name, funder: 'nbn Grants Program (administrator to confirm)',
    url: 'https://business.gov.au/grants-and-programs/nbn-grants-program',
    application_mode: 'required', applicant: '', application_window: 'fixed',
    status: 'clarification'};
  const draft = letters.campaignClarificationDraft(campaign, opportunity, null, '2026-09-30');
  const questions = draft.questions.split('\n');

  assert.equal(draft.title, 'Clarification: nbn Grants Program');
  assert.equal(draft.recipient, 'nbn Grants Program team');
  assert.equal(draft.notes, '');
  assert.equal(questions.length, 4);
  assert.match(questions[0], /which address must meet the regional or remote test/);
  assert.match(questions[1], /which legal entity types may apply/);
  assert.match(questions[2], /how pre-existing or independently created project IP is treated/);
  assert.match(questions[3], /current closing date/);
  for (const internal of ['address intentionally not stored', 'accountant',
    'director and lawyer', 'outstanding programme point recorded in our notes',
    'we will not include an address']) {
    assert.equal(JSON.stringify(draft).toLowerCase().includes(internal), false, internal);
  }
});

test('clarification generation fails clearly rather than silently dropping source links', () => {
  const opportunity = {name: 'Example route', url: 'https://example.invalid/main'};
  const sources = Array.from({length: 11}, (_, index) => ({
    id: index.toString(16).padStart(32, '0'), title: `Source ${index + 1}`,
    url: `https://example.invalid/source-${index + 1}`,
  }));
  const campaign = {organisation: 'Example Association', sources,
    requirements: sources.map((source, index) => ({
      opportunity: opportunity.name, rule: `Check ${index + 1}`, status: 'unknown',
      source_id: source.id, source_quote: 'Saved wording',
    }))};
  assert.throws(() => letters.campaignClarificationDraft(campaign, opportunity,
    {id: 'f'.repeat(32), revision: 1, opportunity: opportunity.name, dirty: false}),
  /more than 10 source excerpts.*every excerpt stays attached/);
});

test('campaign letter copy says the draft is unsent and names missing sign-off', () => {
  const missingBoth = letters.campaignLetterReviewCopy({campaign_sender_review: true});
  assert.equal(missingBoth.title, 'Prepare a campaign letter for review.');
  assert.match(missingBoth.description, /No authorised signatory or reply contact/);
  assert.match(missingBoth.status, /has not been sent/);
  assert.match(missingBoth.announcement, /Not sent/);
  assert.doesNotMatch(missingBoth.title, /ready to use/i);

  const approvedIdentity = letters.campaignLetterReviewCopy({
    signatory: 'Director', contact_details: 'approved@example.invalid',
  });
  assert.match(approvedIdentity.description, /Review the recipient, factual claims/);
  assert.doesNotMatch(approvedIdentity.description, /No authorised signatory/);
});

test('a fully source-linked opportunity gets a selected-opportunity-only fallback question', () => {
  const source = {id: 'a'.repeat(32), title: 'Official window',
    url: 'https://example.invalid/window', checked_at: '2026-09-29'};
  const draft = letters.campaignClarificationDraft({objective: 'Do not include this.', requirements: [],
    sources: [source]},
    {name: 'Example access grant', funder: 'Example Foundation',
      application_mode: 'required', applicant: 'Community Association',
      applicant_confirmed: true,
      application_window: 'rolling', window_source_quote: 'Applications accepted year-round.',
      window_source_id: source.id, window_source_url: source.url,
      window_checked_at: '2026-09-29', url: 'https://example.invalid/fund'}, null, '2026-09-30');
  assert.equal(draft.openCount, 0);
  assert.match(draft.questions, /eligibility, permitted costs and application timetable for this opportunity/);
  assert.equal(draft.notes, '');
  assert.doesNotMatch(JSON.stringify(draft), /Do not include this/);
  assert.equal(draft.organisation, '');
});

test('clarification asks the funder to confirm a named but unconfirmed applicant', () => {
  const draft = letters.campaignClarificationDraft({requirements: []}, {
    name: 'Example local grant', funder: 'Example Foundation',
    application_mode: 'required', applicant: 'Proposed Community Association',
    applicant_confirmed: false, status: 'clarification',
  }, null, '2026-09-30');
  assert.match(draft.questions, /which legal entity types may apply/);
  assert.equal(draft.recipient, 'Example Foundation');
});

test('same-page excerpts and their exact check dates remain separate in a draft', () => {
  const sourceId = 'b'.repeat(32);
  const url = 'https://example.invalid/rules';
  const campaign = {organisation: 'Example Association', sources: [{id: sourceId,
    title: 'Official rules', url, checked_at: '2026-09-29'}], requirements: [
    {opportunity: 'Example route', rule: 'Operating age', status: 'unknown',
      source_id: sourceId, source_url: url, source_quote: 'At least one year of trading.',
      checked_at: '2026-09-28'},
    {opportunity: 'Example route', rule: 'Financial proof', status: 'unknown',
      source_id: sourceId, source_url: url, source_quote: 'Cash contribution rates vary by project.',
      checked_at: '2026-09-28'},
    {opportunity: 'Example route', rule: 'Match', status: 'unknown',
      source_id: sourceId, source_url: url, source_quote: 'Cash match is required.',
      checked_at: '2026-09-27'},
  ]};
  const opportunity = {name: 'Example route', application_window: 'unknown',
    url: 'https://example.invalid/programme'};
  const draft = letters.campaignClarificationDraft(campaign, opportunity,
    {id: 'f'.repeat(32), revision: 1, opportunity: opportunity.name, dirty: false},
    '2026-09-30');
  const excerpts = draft.campaign_link.evidence_links.filter(link => link.source_id === sourceId);
  assert.equal(excerpts.length, 2);
  assert.match(excerpts[0].notes, /At least one year of trading/);
  assert.match(excerpts[0].notes, /Cash contribution rates vary by project/);
  assert.match(excerpts[0].notes, /checked 2026-09-28.*now 2026-09-29/);
  assert.match(excerpts[1].notes, /Cash match is required/);
  assert.match(excerpts[1].notes, /checked 2026-09-27.*now 2026-09-29/);
  assert.deepEqual(excerpts.map(link => link.checked_at), ['2026-09-28', '2026-09-27']);
});

test('same-source citation merging respects the campaign note limit without wasting links', () => {
  const sourceId = 'c'.repeat(32);
  const url = 'https://example.invalid/long-guidance';
  const quotes = ['A'.repeat(1750), 'B'.repeat(500), 'C'.repeat(150)];
  const campaign = {sources: [{id: sourceId, title: 'Long guidance', url,
    checked_at: '2026-09-29'}], requirements: quotes.map((source_quote, index) => ({
    opportunity: 'Example route', rule: `Requirement ${index + 1}`, status: 'unknown',
    source_id: sourceId, source_url: url, source_quote, checked_at: '2026-09-29',
  }))};
  const draft = letters.campaignClarificationDraft(campaign,
    {name: 'Example route', url: 'https://example.invalid/programme'},
    {id: 'f'.repeat(32), revision: 1, opportunity: 'Example route', dirty: false},
    '2026-09-30');
  const excerpts = draft.campaign_link.evidence_links.filter(link => link.source_id === sourceId);
  assert.equal(excerpts.length, 2);
  assert.ok(excerpts.every(link => link.notes.length <= 2000));
  assert.match(excerpts[0].notes, /A{100}$/);
  assert.match(excerpts[1].notes, /B{100}/);
  assert.match(excerpts[1].notes, /C{100}$/);
});

test('long evidence excerpts are preserved instead of truncated in the campaign draft', () => {
  const excerpt = 'Quoted source detail. '.repeat(160);
  const sourceId = 'd'.repeat(32);
  const sourceUrl = 'https://example.invalid/guidance';
  const draft = letters.campaignClarificationDraft({sources: [{id: sourceId,
    title: 'Official guidance', url: sourceUrl, checked_at: '2026-09-29'}],
  requirements: [{opportunity: 'Example route', rule: 'Cost eligibility', status: 'unknown',
    source_id: sourceId, source_url: sourceUrl, source_quote: excerpt,
    checked_at: '2026-09-29'}]},
  {name: 'Example route', url: 'https://example.invalid/programme'},
  {id: 'f'.repeat(32), revision: 1, opportunity: 'Example route', dirty: false},
  '2026-09-30');
  assert.equal(draft.campaign_link.evidence_links[1].notes.endsWith(excerpt), true);
});

test('clarification drafts carry a local campaign revision reference when supplied', () => {
  const link = {id: 'a'.repeat(32), revision: 7,
    opportunity: 'Example access grant', dirty: false};
  const draft = letters.campaignClarificationDraft({objective: 'No', requirements: []},
    {name: 'Example access grant', funder: 'Example Foundation'}, link);
  assert.deepEqual(draft.campaign_link, {...link, evidence_links: []});
});

test('campaign correspondence helper records a local outgoing draft and no sent claim', () => {
  const row = letters.campaignCommunicationFromDraft({
    report: {title: 'Clarification: Example opportunity', input_snapshot: {recipient: 'Example funder'},
      campaign_link: {id: 'a'.repeat(32), revision: 7, opportunity: 'Example opportunity', dirty: false,
        evidence_links: [{title: 'Official guidance', url: 'https://example.invalid/rules', notes: 'Relevant wording.',
          source_id: 'b'.repeat(32), checked_at: '2026-09-29'}] }},
    content: 'Dear programme team,\n\nCould you clarify the deadline?\n\nRegards',
    channel: 'email', date: '2026-09-29',
  });
  assert.deepEqual(row, {
    opportunity: 'Example opportunity', date: '2026-09-29', direction: 'outgoing', status: 'draft',
    channel: 'email', counterparty: 'Example funder', subject: 'Clarification: Example opportunity',
    content: 'Dear programme team,\n\nCould you clarify the deadline?\n\nRegards',
    evidence_links: [{title: 'Official guidance', url: 'https://example.invalid/rules', notes: 'Relevant wording.',
      source_id: 'b'.repeat(32), checked_at: '2026-09-29'}],
  });
  assert.equal(row.status, 'draft');
  const undated = letters.campaignCommunicationFromDraft({
    report: {title: 'Clarification: Example opportunity',
      campaign_link: {id: 'a'.repeat(32), revision: 7,
        opportunity: 'Example opportunity', dirty: false}},
    content: 'Could you confirm the closing date?', channel: 'email', date: '',
  });
  assert.equal(undated.date, '');
  assert.equal(undated.status, 'draft');
});

test('campaign draft logging fails closed for missing or stale campaign identity and invalid content', () => {
  assert.match(letters.campaignDraftLogBlockReason({id: null, revision: null, dirty: true}), /Save the campaign/);
  assert.match(letters.campaignDraftLogBlockReason({id: 'a'.repeat(32), revision: 7, dirty: true}), /unsaved campaign changes/);
  const base = {report: {title: 'Draft', campaign_link: {id: 'a'.repeat(32), revision: 7,
    opportunity: 'Example', dirty: false}}, channel: 'letter', date: '2026-09-29'};
  assert.throws(() => letters.campaignCommunicationFromDraft({...base, content: '  '}), /draft is empty/);
  assert.throws(() => letters.campaignCommunicationFromDraft({...base, content: 'x'.repeat(20001)}), /20,000-character/);
  assert.throws(() => letters.campaignCommunicationFromDraft({...base, content: 'A', channel: 'sent'}), /Choose a draft channel/);
  assert.throws(() => letters.campaignCommunicationFromDraft({...base, content: 'A', date: 'today'}), /valid YYYY-MM-DD date/);
  assert.throws(() => letters.campaignCommunicationFromDraft({...base, content: 'A', date: '2026-02-30'}), /valid YYYY-MM-DD date/);
  assert.throws(() => letters.campaignCommunicationFromDraft({...base, report: {...base.report,
    campaign_link: {...base.report.campaign_link, evidence_links: [{title: 'unsafe', url: 'javascript:alert(1)'}]}},
    content: 'A'}), /HTTP or HTTPS/);
});
