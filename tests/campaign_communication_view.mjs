import test from 'node:test';
import assert from 'node:assert/strict';
import {campaignCommunicationView, campaignCommunicationPreview,
  communicationHasDate, COMMUNICATION_STATUSES}
  from '../src/sinter/web/campaign-communication-view.js';

const rows = () => [
  {date: '2026-09-30', opportunity: 'Fictional route', subject: 'Meeting invitation',
    content: 'Timing needs confirmation.', evidence_links: []},
  {date: '2026-09-20', opportunity: 'Other route', subject: 'Earlier offer',
    content: 'Historical cash wording.', evidence_links: []},
  {date: '2026-09-28', opportunity: 'Fictional route', subject: 'Submission hold',
    content: 'Cash unavailable, no commitment.', evidence_links: [
      {title: 'Earlier saved wording', url: 'https://example.invalid/old',
        notes: 'Überprüfung 🌱', checked_at: '2026-09-28'}]},
  {date: '', opportunity: '', subject: 'Unsent draft', status: 'draft', evidence_links: []},
  {date: '2026-09-28', opportunity: 'Fictional route', subject: 'Same-day note', evidence_links: []},
];
const indexes = view => view.map(entry => entry.index);

test('record order remains explicit and is the fallback', () => {
  const original = rows();
  assert.deepEqual(indexes(campaignCommunicationView(original)), [0, 1, 2, 3, 4]);
  assert.deepEqual(indexes(campaignCommunicationView(original, {order: 'unknown'})), [0, 1, 2, 3, 4]);
});
test('dated order is stable, with undated records last in either direction', () => {
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {order: 'newest'})), [0, 2, 4, 1, 3]);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {order: 'oldest'})), [1, 2, 4, 0, 3]);
});
test('sorting and filtering preserve original array, values and row identities', () => {
  const original = rows();
  const before = structuredClone(original);
  const view = campaignCommunicationView(original, {order: 'oldest', query: 'cash'});
  assert.deepEqual(original, before);
  assert.deepEqual(indexes(view), [1, 2]);
  for (const entry of view) assert.equal(entry.row, original[entry.index]);
  view[1].row.subject = 'Edited canonical hold';
  assert.equal(original[2].subject, 'Edited canonical hold');
  assert.equal(original[1].subject, 'Earlier offer');
});
test('route filter distinguishes all records, exact route names and campaign-wide', () => {
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {route: 'Fictional route'})), [0, 2, 4]);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {route: ''})), [3]);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {route: 'Missing route'})), []);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {route: null})), [0, 1, 2, 3, 4]);
});
test('literal case-insensitive search covers message and saved evidence wording', () => {
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {query: ' CASH '})), [1, 2]);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {query: 'überprüfung 🌱'})), [2]);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {query: 'example.invalid/old'})), [2]);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {query: 'Other route'})), [1]);
  assert.deepEqual(indexes(campaignCommunicationView(rows(), {query: 'no match'})), []);
});
test('same URL/date source changes do not replace searched saved evidence', () => {
  const original = rows();
  const currentSource = {title: 'Current different wording', notes: 'New cash statement'};
  assert.deepEqual(indexes(campaignCommunicationView(original, {query: currentSource.title})), []);
  assert.deepEqual(indexes(campaignCommunicationView(original, {query: 'Earlier saved wording'})), [2]);
});
test('invalid dates remain undated, without timezone or guessed date ordering', () => {
  for (const value of ['', '2026-09-31', '2026-02-29', '0000-01-01', 'yesterday', null]) {
    assert.equal(communicationHasDate(value), false);
  }
  assert.equal(communicationHasDate('2024-02-29'), true);
  const original = [{date: '2026-09-31'}, {date: '2026-09-28'}, {}, {date: '2026-09-29'}];
  assert.deepEqual(indexes(campaignCommunicationView(original, {order: 'newest'})), [3, 1, 0, 2]);
});
test('empty and legacy communications are harmless', () => {
  assert.deepEqual(campaignCommunicationView(), []);
  assert.deepEqual(indexes(campaignCommunicationView([{}], {route: ''})), [0]);
});

test('status filtering is explicit, combined with scope and search, and never rewrites rows', () => {
  const original = rows();
  original[0].status = 'received';
  original[1].status = 'sent';
  original[2].status = 'draft';
  const before = structuredClone(original);
  assert.deepEqual(COMMUNICATION_STATUSES.map(([value]) => value),
    ['all', 'draft', 'sent', 'received']);
  assert.deepEqual(indexes(campaignCommunicationView(original, {status: 'draft'})), [2, 3]);
  assert.deepEqual(indexes(campaignCommunicationView(original, {status: 'sent'})), [1]);
  assert.deepEqual(indexes(campaignCommunicationView(original, {status: 'received'})), [0]);
  assert.deepEqual(indexes(campaignCommunicationView(original,
    {status: 'draft', query: 'cash', route: 'Fictional route'})), [2]);
  assert.deepEqual(indexes(campaignCommunicationView(original, {status: 'invalid'})), [0, 1, 2, 3, 4]);
  assert.deepEqual(original, before);
});

test('previews show literal saved message wording and retain Unicode characters', () => {
  const row = {content: 'Saved <script>alert(1)</script> 🌱 text.', evidence_links: [{}, {}]};
  const before = structuredClone(row);
  const preview = campaignCommunicationPreview(row);
  assert.equal(preview.kind, 'message');
  assert.equal(preview.text, row.content);
  assert.equal(preview.evidenceCount, 2);
  assert.equal(preview.matchesQuery, false);
  assert.deepEqual(row, before);
  assert.equal(campaignCommunicationPreview({content: '🌱'.repeat(8)}, {limit: 3}).text,
    '🌱🌱🌱…');
});

test('search previews identify historical evidence rather than substituting current source text', () => {
  const row = rows()[2];
  const before = structuredClone(row);
  const preview = campaignCommunicationPreview(row, {query: 'überprüfung 🌱'});
  assert.equal(preview.kind, 'evidence');
  assert.equal(preview.label, 'Saved evidence');
  assert.equal(preview.text, 'Überprüfung 🌱');
  assert.equal(preview.matchesQuery, true);
  assert.equal(preview.evidenceCount, 1);
  assert.deepEqual(row, before);
  assert.equal(campaignCommunicationPreview(row, {query: 'Current different wording'}).matchesQuery,
    false);
});

test('matching saved text is brought into the excerpt without shortening the underlying record', () => {
  const row = {content: 'Before 🌱 '.repeat(80) + 'MATCHED wording' + ' After'.repeat(80)};
  const before = row.content;
  const preview = campaignCommunicationPreview(row, {query: 'matched wording', limit: 120});
  assert.equal(preview.kind, 'message');
  assert.equal(preview.matchesQuery, true);
  assert.match(preview.text, /MATCHED wording/);
  assert.equal([...preview.text].length <= 122, true);
  assert.equal(row.content, before);
});

test('expanded lowercase search offsets still preview the matching original Unicode wording', () => {
  const row = {content: 'İ'.repeat(200) + ' MATCHED wording ' + 'After '.repeat(20)};
  const preview = campaignCommunicationPreview(row, {query: 'matched wording', limit: 80});
  assert.match(preview.text, /MATCHED wording/);
  assert.equal([...preview.text].length <= 82, true);
  assert.equal(preview.matchesQuery, true);
  const longQuery = 'Q'.repeat(180);
  const longMatch = campaignCommunicationPreview(
    {content: 'Prefix '.repeat(40) + longQuery + ' suffix'},
    {query: longQuery, limit: 200});
  assert.equal(longMatch.text.includes(longQuery), true);
  assert.equal([...longMatch.text].length <= 202, true);
});

test('blank and metadata-only previews do not invent message text or evidence', () => {
  assert.deepEqual(campaignCommunicationPreview(), {
    kind: 'empty', label: '', text: '', matchesQuery: false, evidenceCount: 0,
  });
  const preview = campaignCommunicationPreview({subject: 'Saved title only'}, {query: 'title'});
  assert.equal(preview.kind, 'metadata');
  assert.equal(preview.label, 'Saved record');
  assert.equal(preview.text, 'Saved title only');
  assert.equal(preview.evidenceCount, 0);
});
