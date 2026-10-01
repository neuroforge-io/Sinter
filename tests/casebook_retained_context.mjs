import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import {casebookQuestionEvidence} from '../src/sinter/web/casebook-question-evidence.js';
import {retainedCasebookSource, retainedQuestionContext} from '../src/sinter/web/casebook-retained-context.js';
if (!globalThis.crypto) Object.defineProperty(globalThis, 'crypto', {configurable: true, value: webcrypto});
const sha = text => createHash('sha256').update(text).digest('hex');
function fixture() {
  const content = '🐝 e\u0301 Before.\nTable 1: closing dates\nSubmission | 31 January 2030\nAfter 🐝.';
  const characters = Array.from(content), start = characters.indexOf('T');
  const end = start + Array.from('Table 1: closing dates\n').length;
  const sources = [{id: 'Sfirst', title: '<script>literal duplicate</script>', content, sha256: sha(content)},
    {id: 'Ssecond', title: '<script>literal duplicate</script>', content: 'Other wording.', sha256: sha('Other wording.')}];
  const register = [...sources.map(({id, title, sha256}) => ({id, title, sha256, date: ''})),
    {id: 'Shistory', title: '<script>literal duplicate</script>', sha256: sha('Historical record only.'), date: '2020-01-01'}];
  return {workflow: 'casebook', sources, source_register: register,
    question_index: [{question: 'What closing date is supported?', excerpt_ids: ['Efirst']},
      {question: 'What reply was received?', excerpt_ids: []}],
    question_scopes: [{question_index: 0, question: 'What closing date is supported?', source_ids: register.map(row => row.id)},
      {question_index: 1, question: 'What reply was received?', source_ids: []}],
    excerpts: [{id: 'Efirst', source_id: 'Sfirst', start, end, quote: characters.slice(start, end).join('')}],
    document_markdown: 'OPERATOR WORDING', document_edits: {markdown: 'EXACT APPLIED WORDING'}, casebook_fingerprint: 'unchanged'};
}

test('coverage distinguishes three chosen identities, one exact quoted original, two unquoted originals with identical titles', () => {
  const report = fixture(), before = JSON.stringify(report), row = casebookQuestionEvidence(report)[0];
  assert.deepEqual(row.coverage, {sourceCount: 3, excerptedSourceCount: 1,
    unexcerptedSources: [{id: 'Ssecond', title: '<script>literal duplicate</script>', date: '', originalRetained: true},
      {id: 'Shistory', title: '<script>literal duplicate</script>', date: '2020-01-01', originalRetained: false}]});
  assert.equal(row.status, 'Review required'); assert.equal(JSON.stringify(report), before);
});

test('another question’s passage cannot hide a source omitted from this question', () => {
  const report = fixture(); report.question_index[1].excerpt_ids = ['Esecond'];
  report.question_scopes[1].source_ids = ['Ssecond'];
  report.excerpts.push({id: 'Esecond', source_id: 'Ssecond', start: 0, end: 14, quote: 'Other wording.'});
  const rows = casebookQuestionEvidence(report);
  assert.equal(rows[0].coverage.excerptedSourceCount, 1);
  assert.equal(rows[1].coverage.excerptedSourceCount, 1);
  assert.ok(rows[0].coverage.unexcerptedSources.some(row => row.id === 'Ssecond'));
});

test('all, explicit none and unavailable choices retain distinct coverage meanings', () => {
  const report = fixture(); assert.deepEqual(casebookQuestionEvidence(report)[1].coverage,
    {sourceCount: 0, excerptedSourceCount: 0, unexcerptedSources: []});
  delete report.question_scopes; assert.equal(casebookQuestionEvidence(report)[0].coverage.sourceCount, 3);
  report.question_scopes = [{question_index: 0, question: 'Changed anchor', source_ids: ['Sfirst']}];
  assert.equal(casebookQuestionEvidence(report)[0].coverage, null);
  const emptyRegister = fixture(); delete emptyRegister.question_scopes; emptyRegister.source_register = [];
  assert.equal(casebookQuestionEvidence(emptyRegister)[0].coverage, null);
});

test('unresolved or duplicate quotations make coverage unavailable rather than an asserted zero', () => {
  for (const change of [r => {r.excerpts[0].quote += '!';}, r => r.excerpts.push({...r.excerpts[0]}),
    r => {r.question_index[0].excerpt_ids = ['unknown'];}, r => {r.excerpts[0].start = true;}]) {
    const report = fixture(); change(report);
    assert.equal(casebookQuestionEvidence(report)[0].coverage, null);
  }
});

test('an unavailable passage list is not an explicit empty list; original malformed values remain intact', () => {
  for (const value of [undefined, null, false, 0, '[]', {}]) {
    const report = fixture(); report.question_index[0].excerpt_ids = value;
    const before = JSON.stringify(report), row = casebookQuestionEvidence(report)[0];
    assert.equal(row.coverage, null); assert.equal(row.status, 'Review required');
    assert.ok(row.gaps.includes('The recorded passage list is unavailable.'));
    assert.equal(JSON.stringify(report), before);
  }
  const report = fixture(); report.question_index[0].excerpt_ids = [];
  assert.equal(casebookQuestionEvidence(report)[0].coverage.excerptedSourceCount, 0);
  assert.equal(casebookQuestionEvidence(report)[0].coverage.sourceCount, 3);
});

test('local adjacent context exposes table cells beyond the quoted heading without altering any stored/applied/draft material', async () => {
  const report = fixture(), before = JSON.stringify(report), result = await retainedQuestionContext(report, 0, 'Efirst');
  assert.equal(result.quote, 'Table 1: closing dates\n');
  assert.ok(result.before.startsWith('🐝 e\u0301 Before.'));
  assert.ok(result.after.includes('Submission | 31 January 2030'));
  assert.equal(result.start, report.excerpts[0].start); assert.equal(result.end, report.excerpts[0].end);
  assert.equal(result.originalCharacters, Array.from(report.sources[0].content).length);
  assert.equal(JSON.stringify(report), before);
});

test('surrounding windows remain bounded at600 Unicode code points each, preserving supplementary and combining characters', async () => {
  const report = fixture(); const before = '🐝e\u0301'.repeat(250), quote = 'Table heading\n', after = '🦋o\u0308'.repeat(250);
  const source = report.sources[0]; source.content = before + quote + after; source.sha256 = report.source_register[0].sha256 = sha(source.content);
  report.excerpts[0] = {id: 'Efirst', source_id: source.id, start: Array.from(before).length,
    end: Array.from(before + quote).length, quote};
  const result = await retainedQuestionContext(report, 0, 'Efirst');
  assert.equal(Array.from(result.before).length, 600); assert.equal(Array.from(result.after).length, 600);
  assert.equal(result.before, Array.from(before).slice(-600).join(''));
  assert.equal(result.after, Array.from(after).slice(0, 600).join(''));
});

test('changed surrounding original is refused even when the quoted heading still matches its exact offsets', async () => {
  const report = fixture(); report.sources[0].content = report.sources[0].content.replace('31 January', '99 January');
  assert.equal(casebookQuestionEvidence(report)[0].matches[0].available, true);
  await assert.rejects(retainedQuestionContext(report, 0, 'Efirst'), /does not match its recorded source hash/);
});

test('missing/ambiguous originals and inconsistent hashes never use a current source or identical-title substitute', async () => {
  for (const change of [r => r.sources.splice(0, 1), r => r.sources.push({...r.sources[0]}),
    r => r.source_register.push({...r.source_register[0]}), r => {r.sources[0].sha256 = '0'.repeat(64);},
    r => {delete r.source_register[0].sha256;}]) {
    const report = fixture(); change(report); const before = JSON.stringify(report);
    await assert.rejects(retainedCasebookSource(report, 'Sfirst')); assert.equal(JSON.stringify(report), before);
  }
  await assert.rejects(retainedCasebookSource(fixture(), 'Shistory'), /not retained unambiguously/);
  await assert.rejects(retainedCasebookSource(fixture(), 'unknown'), /not retained unambiguously/);
});

test('question scope and exact anchors restrict context; no source from another question is borrowed', async () => {
  for (const fields of [{source_ids: []}, {source_ids: ['Ssecond']}, {question: 'Replaced question'}]) {
    const report = fixture(); Object.assign(report.question_scopes[0], fields);
    await assert.rejects(retainedQuestionContext(report, 0, 'Efirst'), /passage is unavailable/);
  }
  await assert.rejects(retainedQuestionContext(fixture(), true, 'Efirst'), /question is unavailable/);
  await assert.rejects(retainedQuestionContext(fixture(), 1, 'Efirst'), /passage is unavailable/);
  for (const question of ['', '\u2003\u0085']) {
    const report = fixture(); report.question_index[0].question = question; report.question_scopes[0].question = question;
    assert.equal(casebookQuestionEvidence(report)[0].coverage, null);
    await assert.rejects(retainedQuestionContext(report, 0, 'Efirst'), /question is unavailable/);
  }
});

test('unsupported reports/invalid scalars refuse local context instead of normalizing originals', async () => {
  for (const fields of [{model_draft: true}, {incomplete: true}, {workflow: 'campaign'}]) {
    await assert.rejects(retainedCasebookSource({...fixture(), ...fields}, 'Sfirst'), /complete source-only/);
  }
  for (const value of ['original\ud800', 'original\0']) {
    const report = fixture(); report.sources[0].content = value; report.sources[0].sha256 = report.source_register[0].sha256 = sha(value);
    await assert.rejects(retainedCasebookSource(report, 'Sfirst'), /unsupported text/);
  }
});

test('missing local digest capability refuses, and asynchronous inspection snapshots exact strings without mutating the report', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  try {
    Object.defineProperty(globalThis, 'crypto', {configurable: true, value: undefined});
    await assert.rejects(retainedCasebookSource(fixture(), 'Sfirst'), /cannot check/);
  } finally {Object.defineProperty(globalThis, 'crypto', descriptor);}
  const report = fixture(), original = report.sources[0].content;
  const pending = retainedCasebookSource(report, 'Sfirst'); report.sources[0].content = 'Deliberate later replacement';
  assert.equal((await pending).content, original); assert.equal(report.sources[0].content, 'Deliberate later replacement');
});
