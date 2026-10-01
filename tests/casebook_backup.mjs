import assert from 'node:assert/strict';
import test from 'node:test';
import {casebookBackupText} from '../src/sinter/web/casebook-backup.js';

const workingCopy = () => ({schema: 'sinter-casebook/v2', title: 'Fictional 🐝 e\u0301',
  questions: 'Changed question — needs explicit scope review\nUnanswered?',
  recipient: '', signatory: '', document_type: 'handover', handover_evidence: 'selected_appendix',
  documents: [{id: '1234567890abcdef1234567890abcdef', title: 'Original', date: '', url: '',
    content: 'Exact first line.\r\n<original> "quote" \\ literal e\u0301 🌱'}],
  question_scopes: [{question_index: 0, question: 'Earlier unchanged anchor',
    source_ids: ['1234567890abcdef1234567890abcdef']},
  {question_index: 1, question: 'Unanswered?', source_ids: []}]});

test('backup retains stale choices, explicit none, exact originals and unknown fields without normalization', () => {
  const book = workingCopy(), original = structuredClone(book);
  const text = casebookBackupText(book);
  assert.equal(text, JSON.stringify(original, null, 2));
  assert.deepEqual(JSON.parse(text), original);
  assert.deepEqual(book, original);
});

test('recovery keeps over-limit work for deliberate splitting instead of truncating it', () => {
  const book = workingCopy(); book.documents[0].content = 'Fictional 🐝 <unknown> e\u0301\n'.repeat(100000);
  const text = casebookBackupText(book);
  assert.ok(Buffer.byteLength(text, 'utf8') > 2_000_000);
  assert.deepEqual(JSON.parse(text), book);
});

test('v1 backup stays v1 and does not invent source choices', () => {
  const book = workingCopy(); book.schema = 'sinter-casebook/v1'; delete book.question_scopes;
  assert.deepEqual(JSON.parse(casebookBackupText(book)), book);
  assert.ok(!casebookBackupText(book).includes('question_scopes'));
});

test('unserializable work fails without changing the original', () => {
  const book = workingCopy(); book.cycle = book;
  assert.throws(() => casebookBackupText(book), TypeError);
  assert.equal(book.cycle, book);
  assert.throws(() => casebookBackupText(undefined), /project working copy/);
});
