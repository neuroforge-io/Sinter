import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import test from 'node:test';
import {validWordCopyResult, wordCopySnapshotHash} from '../src/sinter/web/documents.js';

globalThis.crypto ??= webcrypto;

const snapshot = {title: 'Fictional 🐝 e\u0301', markdown: '# Exact wording\n\nNo approval — 🐝 e\u0301.'};
const hash = createHash('sha256').update(JSON.stringify({markdown: snapshot.markdown, title: snapshot.title})).digest('hex');
const filename = 'sinter-Fictional-DRAFT-' + 'a'.repeat(32) + '.docx';
const result = {path: '/private/workspace/exports/' + filename, filename, bytes: 4096,
  content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  verification: 'Word ZIP integrity and exact byte readback', title: snapshot.title,
  sha256: 'b'.repeat(64), markdown_sha256: 'c'.repeat(64), snapshot_sha256: hash};

test('snapshot hash binds exact Unicode, whitespace, title and applied text without mutation', async () => {
  const original = structuredClone(snapshot);
  assert.equal(await wordCopySnapshotHash(snapshot), hash);
  for (const other of [{...snapshot, title: snapshot.title + ' '},
    {...snapshot, markdown: snapshot.markdown + '\n'},
    {...snapshot, markdown: snapshot.markdown.normalize('NFC')}]) {
    assert.notEqual(await wordCopySnapshotHash(other), hash);
  }
  assert.deepEqual(snapshot, original);
});

test('confirmation needs this exact snapshot and bounded verified file metadata', () => {
  assert.equal(validWordCopyResult(result, snapshot, hash), true);
  const attacks = [null, [], false, {},
    {...result, title: 'Another document'},
    {...result, snapshot_sha256: 'f'.repeat(64)},
    {...result, bytes: 0}, {...result, bytes: Infinity}, {...result, bytes: 8388609},
    {...result, sha256: 'unverified'}, {...result, sha256: 'B'.repeat(64)},
    {...result, content_type: 'text/html'},
    {...result, verification: 'Request accepted'},
    {...result, path: 'https://example.invalid/' + filename},
    {...result, path: '/private/workspace/exports/other.docx'},
    {...result, filename: '../' + filename},
  ];
  for (const value of attacks) assert.equal(validWordCopyResult(value, snapshot, hash), false);
  assert.equal(validWordCopyResult(result, snapshot, undefined), false);
  assert.equal(validWordCopyResult(result, snapshot, 'f'.repeat(64)), false);
});
