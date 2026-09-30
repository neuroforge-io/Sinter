import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignSourceSnapshotGuidance, campaignSourceSnapshotIssue}
  from '../src/sinter/web/campaign-source-state.js';

const current = {url: 'https://example.org/rules', checked_at: '2026-09-29'};

test('source snapshot issues distinguish missing metadata from a changed record', () => {
  assert.equal(campaignSourceSnapshotIssue('', '', current), 'url_snapshot_missing');
  assert.equal(campaignSourceSnapshotIssue(current.url, '', current), 'date_snapshot_missing');
  assert.equal(campaignSourceSnapshotIssue('https://example.org/old',
    current.checked_at, current), 'url_mismatch');
  assert.equal(campaignSourceSnapshotIssue(current.url, '2026-09-28', current),
    'date_mismatch');
  assert.equal(campaignSourceSnapshotIssue(current.url, current.checked_at, current), '');
});

test('source guidance never asserts a source changed when a saved snapshot is absent', () => {
  const urlIssue = campaignSourceSnapshotIssue('', '', current);
  const dateIssue = campaignSourceSnapshotIssue(current.url, '', current);
  assert.match(campaignSourceSnapshotGuidance(urlIssue), /No source URL snapshot was saved/);
  assert.match(campaignSourceSnapshotGuidance(dateIssue), /No source check date was saved/);
  assert.doesNotMatch(campaignSourceSnapshotGuidance(urlIssue), /changed/);
  assert.doesNotMatch(campaignSourceSnapshotGuidance(dateIssue), /refreshed/);
});
