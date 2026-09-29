import test from 'node:test';
import assert from 'node:assert/strict';
import * as letters from '../src/sinter/web/campaign-letter.js';

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
  assert.match(draft.notes, /Fictional School Community Association/);
  assert.match(draft.notes, /School-led swimming sessions for 2027/);
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
  assert.match(draft.notes, /NeuroforgeIO Pty Ltd/);
  assert.match(draft.notes, /Possible language-only evaluation/);
  assert.doesNotMatch(draft.notes, /PORTFOLIO_WIDE_PRIVATE_CONTEXT/);
  assert.doesNotMatch(draft.notes, /model-conversion quality and hardware resource use/);
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
    application_window: 'rolling', window_source_quote: 'Accepts applications year round.',
    window_checked_at: '2026-09-29', status: 'open'};
  const campaign = {organisation: 'Warraburra State School P&C',
    objective: 'School swimming participation for local students.', requirements: []};
  const draft = letters.campaignClarificationDraft(campaign, opportunity,
    {id: 'f'.repeat(32), revision: 1, opportunity: opportunity.name, dirty: false},
    '2026-09-30');
  const encoded = JSON.stringify(draft);
  assert.match(encoded, /Warraburra State School P&C/);
  assert.match(encoded, /school swimming safety resources/);
  for (const leaked of ['NeuroforgeIO', 'NeuroForge', 'model-conversion', 'hardware resource use']) {
    assert.equal(encoded.includes(leaked), false, leaked);
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
      application_window: 'rolling', window_source_quote: 'Applications accepted year-round.',
      window_source_id: source.id, window_source_url: source.url,
      window_checked_at: '2026-09-29', url: 'https://example.invalid/fund'}, null, '2026-09-30');
  assert.equal(draft.openCount, 0);
  assert.match(draft.questions, /eligibility, permitted costs and application timetable for this opportunity/);
  assert.match(draft.notes, /No route-specific project context is recorded/);
  assert.doesNotMatch(draft.notes, /Do not include this/);
  assert.equal(draft.organisation, '');
});

test('same-page excerpts and their exact check dates remain separate in a draft', () => {
  const sourceId = 'b'.repeat(32);
  const url = 'https://example.invalid/rules';
  const campaign = {organisation: 'Example Association', sources: [{id: sourceId,
    title: 'Official rules', url, checked_at: '2026-09-29'}], requirements: [
    {opportunity: 'Example route', rule: 'Operating age', status: 'unknown',
      source_id: sourceId, source_url: url, source_quote: 'At least one year of trading.',
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
  assert.match(excerpts[0].notes, /checked 2026-09-28.*now 2026-09-29/);
  assert.match(excerpts[1].notes, /Cash match is required/);
  assert.match(excerpts[1].notes, /checked 2026-09-27.*now 2026-09-29/);
  assert.deepEqual(excerpts.map(link => link.checked_at), ['2026-09-28', '2026-09-27']);
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
