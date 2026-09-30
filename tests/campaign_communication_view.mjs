import test from 'node:test';
import assert from 'node:assert/strict';
import {campaignCommunicationView, communicationHasDate}
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
