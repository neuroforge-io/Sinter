import assert from 'node:assert/strict';
import test from 'node:test';
import {savedReportMatches, savedReportReference, savedReportWording, savedReportPreview} from '../src/sinter/web/saved-report-list.js';

import {registerReportDraft, markReportSaved, observeReportSaveState, rememberReportSavedCopy, reportSavedCopyId, clearReportDrafts} from '../src/sinter/web/report-drafts.js';

const a = {id: '01234567aaaa'.padEnd(32, 'a'), title: 'Café 🐝 funding letter', created_at: 42};
const b = {id: '01234567bbbb'.padEnd(32, 'b'), title: a.title, created_at: 42};

test('filter searches only saved title and full reference without changing metadata', () => {
  const before = structuredClone(a);
  assert.equal(savedReportMatches(a, 'CAFÉ 🐝'), true);
  assert.equal(savedReportMatches(a, 'Cafe\u0301'), true);
  assert.equal(savedReportMatches(a, a.id.slice(-12)), true);
  assert.equal(savedReportMatches(a, 'unrelated'), false);
  assert.equal(savedReportMatches(a, '  '), true);
  assert.deepEqual(a, before);
});

test('display references expand collisions but preserve full identities', () => {
  assert.equal(savedReportReference(a.id, [a]), a.id.slice(0, 8));
  assert.equal(savedReportReference(a.id, [a, b]), a.id.slice(0, 12));
  assert.equal(savedReportReference(b.id, [a, b]), b.id.slice(0, 12));
  assert.notEqual(savedReportReference(a.id, [a, b]), savedReportReference(b.id, [a, b]));
});

test('preview selects applied edits and keeps incomplete warnings and originals', () => {
  const report = {document_markdown: '# Original\n\nUntouched evidence.', document_edits: {markdown: '# Edited 🐝\n\nHuman wording.'}, incomplete: true};
  const original = structuredClone(report);
  const value = savedReportWording(report);
  assert.match(value.markdown, /^\*\*INCOMPLETE MODEL DRAFT/);
  assert.match(value.markdown, /Human wording/);
  assert.doesNotMatch(value.markdown, /Untouched evidence/);
  assert.equal(value.edited, true);
  assert.equal(value.truncated, false);
  assert.deepEqual(report, original);
});

test('bounded sections cover Unicode, markup and closing wording exactly once', () => {
  const text = '# Café e\u0301 🐝\n\n' + '🐝[literal](https://example.invalid/) <script>never()</script>\n'.repeat(120)
    + '\nClosing: this application is NOT approved.';
  const report = {document_markdown: text};
  let joined = '', start = 0, count = 0, value;
  do {
    value = savedReportWording(report, 37, start);
    assert.ok(value.characters <= 37);
    assert.equal([...value.markdown].length, value.characters);
    assert.equal(value.start, start);
    assert.equal(value.end, start + value.markdown.length);
    joined += value.markdown; start = value.end; count++;
    assert.ok(count < 500);
  } while (value.truncated);
  assert.equal(joined, text);
  assert.match(joined, /NOT approved/);
});

test('malformed and empty saved wording fails explicitly', () => {
  for (const value of [null, [], {}, {document_markdown: '  '}, {document_markdown: 42}]) {
    assert.throws(() => savedReportWording(value), /readable|trimStart/);
  }
});

function harness() {
  const pending = [], states = [];
  let connected = true;
  const preview = savedReportPreview({
    load(id, signal) {
      return new Promise((resolve, reject) => pending.push({id, signal, resolve, reject}));
    },
    active: () => connected,
    changed: value => states.push(value),
  });
  return {pending, states, preview, disconnect() { connected = false; }};
}

test('listing creates no document reads; reverse-order response cannot replace selection', async () => {
  const h = harness();
  assert.equal(h.pending.length, 0);
  const first = h.preview.open(a), second = h.preview.open(b);
  assert.deepEqual(h.pending.map(value => value.id), [a.id, b.id]);
  assert.equal(h.pending[0].signal.aborted, true);
  h.pending[1].resolve({document_markdown: 'Second saved wording'});
  await second;
  h.pending[0].resolve({document_markdown: 'Late first wording'});
  await first;
  assert.deepEqual(h.states.filter(state => state.kind === 'ready').map(state => state.metadata.id), [b.id]);
  assert.equal(h.states.at(-1).wording.markdown, 'Second saved wording');
});

test('close and disposal invalidate even a loader which ignores cancellation', async () => {
  for (const operation of ['close', 'dispose', 'disconnect']) {
    const h = harness(), run = h.preview.open(a);
    if (operation === 'disconnect') h.disconnect(); else h.preview[operation]();
    h.pending[0].resolve({document_markdown: 'Obsolete wording'});
    await run;
    assert.equal(h.states.filter(state => state.kind === 'ready').length, 0);
    if (operation === 'dispose') {
      await h.preview.open(b);
      assert.equal(h.pending.length, 1);
    }
  }
});

test('errors remain explicit, never replay, and stale errors remain invisible', async () => {
  const h = harness(), first = h.preview.open(a), second = h.preview.open(b);
  h.pending[0].reject(new Error('Old missing copy'));
  await first;
  assert.equal(h.states.filter(state => state.kind === 'error').length, 0);
  h.pending[1].reject(new Error('Selected copy unavailable'));
  await second;
  assert.equal(h.states.at(-1).message, 'Selected copy unavailable');
  assert.equal(h.pending.length, 2);
});

test('section navigation reads the selected copy once and reveals closing differences', async () => {
  const h = harness(), run = h.preview.open(a);
  const text = 'Shared wording. '.repeat(350) + 'Different closing: no approval.';
  h.pending[0].resolve({document_edits: {markdown: text}});
  await run;
  assert.doesNotMatch(h.states.at(-1).wording.markdown, /Different closing/);
  const sections = [h.states.at(-1).wording.markdown];
  while (h.preview.next()) sections.push(h.states.at(-1).wording.markdown);
  assert.equal(sections.join(''), text);
  assert.equal(h.pending.length, 1);
  assert.equal(h.preview.previous(), true);
  assert.equal(h.states.at(-1).previous, true);
  h.preview.close();
  assert.equal(h.preview.next(), false);
});

test('copy identity belongs to its originating registered report across view failures', () => {
  clearReportDrafts();
  const first = {markdown: 'First original'}, second = {markdown: 'Second original'};
  registerReportDraft(first, first.markdown, {saved: true});
  registerReportDraft(second, second.markdown, {saved: true});
  rememberReportSavedCopy(first, a.id);
  rememberReportSavedCopy(second, b.id);
  assert.equal(reportSavedCopyId(first), a.id);
  assert.equal(reportSavedCopyId(second), b.id);
  observeReportSaveState(first, () => { throw new Error('Detached view failed'); });
  const saved = 'c'.repeat(32);
  const failures = markReportSaved(first, first.markdown, first, saved);
  assert.equal(failures.length, 1);
  assert.equal(reportSavedCopyId(first), saved);
  assert.equal(reportSavedCopyId(second), b.id);
  assert.deepEqual(first, {markdown: 'First original'});
  assert.throws(() => rememberReportSavedCopy(first, 'short-id'), /complete saved-copy/);
  assert.equal(reportSavedCopyId(first), saved);
  assert.throws(() => rememberReportSavedCopy({}, saved), /registered draft/);
  clearReportDrafts();
  assert.equal(reportSavedCopyId(first), null);
});
