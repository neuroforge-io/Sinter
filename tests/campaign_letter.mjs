import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../src/sinter/web/campaign-letter.js', import.meta.url), 'utf8');
const letters = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

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
    fit: 'SELECTED_FIT_NOT_NEEDED'};
  const draft = letters.campaignClarificationDraft(campaign, opportunity);
  assert.equal(draft.openCount, 2);
  assert.equal(draft.recipient, 'Example Schools Programme');
  assert.equal(draft.title, 'Clarification: School-led swimming 2027');
  assert.equal(draft.notes, '');
  assert.match(draft.questions, /Could you confirm the current requirement for “Registered school and portal access confirmed” and what evidence we should provide\?/);
  assert.match(draft.questions, /Could you confirm the current requirement for “Eligible costs and supporting quotes” and what evidence we should provide\?/);
  for (const excluded of ['CAMPAIGN_WIDE_SECRET_CONTEXT', 'OTHER_OPPORTUNITY_RULE', 'Unrelated venue grant', 'SELECTED_FIT_NOT_NEEDED', 'Already fully checked']) {
    assert.equal(JSON.stringify(draft).includes(excluded), false, excluded);
  }
});

test('question titles are grammatical, bounded and sanitized', () => {
  assert.equal(letters.clarificationQuestion('What counts as an eligible applicant'), 'What counts as an eligible applicant?');
  assert.equal(letters.clarificationQuestion(''), '');
  const long = letters.clarificationQuestion('A'.repeat(500));
  assert.ok(long.length < 350);
  assert.equal(long.includes('\n'), false);
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

test('a completed opportunity gets a selected-opportunity-only fallback question', () => {
  const draft = letters.campaignClarificationDraft({objective: 'Do not include this.', requirements: []},
    {name: 'Example access grant', funder: 'Example Foundation'});
  assert.equal(draft.openCount, 0);
  assert.match(draft.questions, /eligibility, permitted costs and application timetable for this opportunity/);
  assert.equal(draft.notes, '');
  assert.equal(draft.organisation, '');
});

test('clarification drafts carry a local campaign revision reference when supplied', () => {
  const link = {id: 'a'.repeat(32), revision: 7,
    opportunity: 'Example access grant', dirty: false};
  const draft = letters.campaignClarificationDraft({objective: 'No', requirements: []},
    {name: 'Example access grant', funder: 'Example Foundation'}, link);
  assert.deepEqual(draft.campaign_link, link);
});

test('campaign correspondence helper records a local outgoing draft and no sent claim', () => {
  const row = letters.campaignCommunicationFromDraft({
    report: {title: 'Clarification: Example opportunity', input_snapshot: {recipient: 'Example funder'},
      campaign_link: {id: 'a'.repeat(32), revision: 7, opportunity: 'Example opportunity', dirty: false}},
    content: 'Dear programme team,\n\nCould you clarify the deadline?\n\nRegards',
    channel: 'email', date: '2026-09-29',
  });
  assert.deepEqual(row, {
    opportunity: 'Example opportunity', date: '2026-09-29', direction: 'outgoing', status: 'draft',
    channel: 'email', counterparty: 'Example funder', subject: 'Clarification: Example opportunity',
    content: 'Dear programme team,\n\nCould you clarify the deadline?\n\nRegards', evidence_links: [],
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
});
