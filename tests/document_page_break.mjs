import assert from 'node:assert/strict';
import test from 'node:test';
import {DOCUMENT_PAGE_BREAK_MARKER as marker, isDocumentPageBreak,
  insertDocumentPageBreak} from '../src/sinter/web/document-page-break.js';
import {documentExportStyles, documentMarkdown} from '../src/sinter/web/documents.js';

test('only exact top-level blank-separated directive lines are admitted', () => {
  assert.equal(isDocumentPageBreak(['Before', '', marker, '', 'After'], 2), true);
  assert.equal(isDocumentPageBreak([marker], 0), true);
  for (const lines of [[` ${marker}`], [`${marker}<script>`],
    ['Before', marker, 'After'], [marker, 'After']]) {
    assert.equal(isDocumentPageBreak(lines, lines.indexOf(marker) < 0 ? 0 : lines.indexOf(marker)), false);
  }
  assert.equal(isDocumentPageBreak([marker], 0, 1), false);
});

test('insertion keeps the full original text and collapses the caret after the marker', () => {
  const result = insertDocumentPageBreak('Front page\n\nEvidence remains.', 12);
  assert.equal(result.text, `Front page\n\n${marker}\n\nEvidence remains.`);
  assert.equal(result.text.slice(result.cursor), 'Evidence remains.');
  assert.equal(insertDocumentPageBreak('AB', 1).text, `A\n\n${marker}\n\nB`);
  assert.equal(insertDocumentPageBreak('AB', -1).text, `${marker}\n\nAB`);
  assert.equal(insertDocumentPageBreak('AB', 999).text, `AB\n\n${marker}`);
  assert.equal(insertDocumentPageBreak('A🌿B', 2).text, `A\n\n${marker}\n\n🌿B`);
});

test('applied and historical Markdown bytes are retained without export rewriting', () => {
  const original = '# Front page\n\nHistorical note.';
  const edited = insertDocumentPageBreak(original, original.length).text;
  const report = {document_markdown: original, document_edits: {markdown: edited}};
  const before = structuredClone(report);
  assert.equal(documentMarkdown(report), edited);
  assert.equal(report.document_markdown, original);
  assert.deepEqual(report, before);
});

test('portable HTML styling requests a real print boundary without hiding source text', () => {
  for (const workflow of ['brief', 'campaign']) {
    const styles = documentExportStyles({workflow});
    assert.match(styles, /\.document-page-break\{/);
    assert.match(styles, /break-after:page;page-break-after:always/);
    assert.doesNotMatch(styles, /\.document-page-break\{[^}]*display:none/);
  }
});
