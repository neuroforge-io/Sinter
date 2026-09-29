import assert from 'node:assert/strict';
import test from 'node:test';
import {evidencePackForDownload} from '../src/sinter/web/documents.js';

function campaignReport() {
  const messageBody = 'Private communication body with identifying details.\n\n'
    + '## Source references\nInjected heading inside the message.';
  return {
    workflow: 'campaign',
    title: 'Fictional school access campaign',
    campaign: {
      signatory: 'Casey Example',
      sender_role: 'P&C secretary',
      contact_details: 'casey@example.invalid\n0400 000 123',
      communications: [{
        opportunity: 'Fictional community fund',
        date: '2026-09-29',
        direction: 'outgoing',
        status: 'draft',
        channel: 'email',
        counterparty: 'Jordan Contact',
        subject: 'Private funding discussion',
        content: messageBody,
        evidence_links: [{
          title: 'Private correspondence',
          url: 'https://example.invalid/private-message/abc123',
          notes: 'Contains a personal contact reference.',
        }],
      }],
      sources: [{title: 'Public fund page', url: 'https://example.invalid/fund', notes: ''}],
    },
    markdown: '# Campaign audit\n\n## Communications log · user-entered, unverified\n\n'
      + 'Other party (user-entered): Jordan Contact\n\nSubject: Private funding discussion\n\n'
      + 'Message content or summary (user-entered):\n' + messageBody + '\n\n'
      + '## Source references\n\nPublic fund page: https://example.invalid/fund\n\n'
      + 'Character counts use Unicode code points, including whitespace.\n',
    document_markdown: '# Internal brief\n\nReview before sharing.\n',
    document_edits: {markdown: 'Copied correspondence: Private communication body with identifying details.'},
  };
}

test('campaign evidence downloads redact private correspondence and contact details by default', () => {
  const original = campaignReport();
  const before = structuredClone(original);
  const pack = evidencePackForDownload(original);
  const serialized = JSON.stringify(pack);

  assert.equal(pack.campaign.signatory, '[Redacted from this export]');
  assert.equal(pack.campaign.contact_details, '[Redacted from this export]');
  assert.equal(pack.campaign.communications[0].counterparty, '[Redacted from this export]');
  assert.equal(pack.campaign.communications[0].subject, '[Redacted from this export]');
  assert.equal(pack.campaign.communications[0].content, '[Redacted from this export]');
  assert.deepEqual(pack.campaign.communications[0].evidence_links, []);
  for (const secret of [
    'Casey Example', 'casey@example.invalid', '0400 000 123', 'Jordan Contact',
    'Private funding discussion', 'Private communication body with identifying details.',
    'private-message/abc123', 'personal contact reference',
  ]) assert.equal(serialized.includes(secret), false, `Private value leaked: ${secret}`);
  assert.match(pack.document_edits.markdown, /omitted from this redacted export/i);
  assert.match(pack.markdown, /communication bodies, subject lines, contact names and evidence links are redacted/i);
  assert.match(pack.export_privacy.notice, /not a complete privacy scrub/i);
  assert.match(pack.export_privacy.notice, /review the whole file before sharing/i);
  assert.equal(pack.campaign.sources[0].title, 'Public fund page');
  assert.doesNotMatch(pack.markdown, /Public fund page/);
  assert.deepEqual(original, before, 'Preparing a download must not mutate the saved report data.');
  assert.equal(pack.export_privacy.campaign_private_details, 'redacted');
});

test('pasted source-heading text cannot create a false redaction boundary without sources', () => {
  const original = campaignReport();
  original.campaign.sources = [];
  original.markdown = '# Campaign audit\n\n'
    + '## Communications log · user-entered, unverified\n\n'
    + 'Message content or summary (user-entered):\n'
    + 'Private opening.\n\n## Source references\nTOP-SECRET TRAILING MESSAGE TEXT\n\n'
    + 'Character counts use Unicode code points, including whitespace.\n';

  const pack = evidencePackForDownload(original);
  const serialized = JSON.stringify(pack);
  assert.equal(serialized.includes('TOP-SECRET TRAILING MESSAGE TEXT'), false);
  assert.match(pack.markdown, /are redacted from this export/i);
  assert.doesNotMatch(pack.markdown, /TOP-SECRET/);
});

test('campaign private fields appear only after explicit per-download opt-in', () => {
  const original = campaignReport();
  const pack = evidencePackForDownload(original, {includePrivate: true});
  assert.deepEqual(pack.campaign, original.campaign);
  assert.equal(pack.markdown, original.markdown);
  assert.deepEqual(pack.document_edits, original.document_edits);
  assert.equal(pack.export_privacy.campaign_private_details, 'included_by_user_choice');
});

test('non-campaign evidence packs retain their existing contents', () => {
  const report = {workflow: 'brief', title: 'Example', sources: [{title: 'Source'}]};
  assert.deepEqual(evidencePackForDownload(report), report);
});
