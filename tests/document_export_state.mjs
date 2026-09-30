import assert from 'node:assert/strict';
import test from 'node:test';
import {documentMarkdown, hasUnappliedDocumentEdits} from '../src/sinter/web/documents.js';

test('changed editor wording requires Apply or Cancel while hidden text and an unchanged open editor export normally', () => {
  for (const current of ['', 'No order has been approved.', 'Exact 🌱 e\u0301\nwording']) {
    assert.equal(hasUnappliedDocumentEdits(current, current, true), false);
    for (const text of [current + ' ', current + '\n', 'Different 🐝 text', '']) {
      assert.equal(hasUnappliedDocumentEdits(current, text, true), text !== current);
      assert.equal(hasUnappliedDocumentEdits(current, text, false), false);
    }
  }
});

test('pending comparison follows the currently applied document and retains incomplete-draft markers', () => {
  const report = {incomplete: true, document_markdown: 'Original partial text.',
    document_edits: {markdown: 'User-applied partial text.'},
    sources: [{content: 'Exact original — no permission has been granted.'}]};
  const original = structuredClone(report);
  const current = documentMarkdown(report);
  assert.match(current, /INCOMPLETE MODEL DRAFT/);
  assert.equal(hasUnappliedDocumentEdits(current, current, true), false);
  assert.equal(hasUnappliedDocumentEdits(current, report.document_edits.markdown, true), true);
  assert.deepEqual(report, original);
});
