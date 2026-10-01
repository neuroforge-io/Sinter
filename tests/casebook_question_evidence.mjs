import test from 'node:test';
import assert from 'node:assert/strict';
import {casebookQuestionEvidence} from '../src/sinter/web/casebook-question-evidence.js';

function fixture() {
  const content = '🐝 e\u0301 Event proposed for 8 August. No closing date is recorded.';
  const start = 5, end = Array.from(content).length;
  const sources = [{id: 'Sfirst', title: '<script>not markup</script> [same title](javascript:evil)', content},
    {id: 'Ssecond', title: '<script>not markup</script> [same title](javascript:evil)', content: 'No procurement quote is confirmed.'}];
  const excerpts = [{id: 'Efirst', source_id: 'Sfirst', start, end,
    quote: Array.from(content).slice(start, end).join('')}];
  return {workflow: 'casebook', document_type: 'handover', document_markdown: 'ORIGINAL HANDOVER',
    document_edits: {markdown: 'REVIEWED HANDOVER'}, markdown: 'ORIGINAL DOSSIER', sources, excerpts,
    document_references: [{label: 'Passage 1', excerpt_id: 'Efirst', source_id: 'Sfirst', start, end}],
    source_register: sources.map(({id, title}) => ({id, title, date: '', url: '', sha256: 'retained'})),
    question_index: [{question: 'What is the closing deadline?', excerpt_ids: ['Efirst']},
      {question: 'What insurance is confirmed?', excerpt_ids: []},
      {question: 'Which supplier agreed?', excerpt_ids: []},
      {question: 'What costs are evidenced?', excerpt_ids: []}],
    question_scopes: [{question_index: 1, question: 'What insurance is confirmed?', source_ids: []},
      {question_index: 2, question: 'Which supplier agreed?', source_ids: ['Ssecond']}]};
}
function frozen(value) {
  if (value && typeof value === 'object') { Object.freeze(value); Object.values(value).forEach(frozen); }
  return value;
}

test('a misleading date lexical hit remains review required, with exact historical question and readable validated passage', () => {
  const report = frozen(fixture()), before = JSON.stringify(report);
  const rows = casebookQuestionEvidence(report);
  assert.deepEqual(rows.map(row => [row.position, row.question, row.scopeLabel, row.status]), [
    [1, 'What is the closing deadline?', 'All supplied sources', 'Review required'],
    [2, 'What insurance is confirmed?', 'No sources selected', 'No sources selected'],
    [3, 'Which supplier agreed?', '1 selected source', 'No wording match'],
    [4, 'What costs are evidenced?', 'All supplied sources', 'No wording match']]);
  assert.equal(rows[0].matches[0].label, 'Passage 1');
  assert.equal(rows[0].matches[0].quote, report.excerpts[0].quote);
  assert.equal(rows[0].matches[0].sourceTitle, report.source_register[0].title);
  assert.equal(rows[0].matches[0].sourceId, 'Sfirst');
  assert.equal(JSON.stringify(report), before);
});

test('supplementary and combining Unicode offsets resolve code points, never UTF-16 or normalized substitutes', () => {
  const report = fixture(), passage = casebookQuestionEvidence(report)[0].matches[0];
  assert.equal(passage.start, 5); assert.equal(passage.end, Array.from(report.sources[0].content).length);
  assert.equal(passage.available, true);
  report.excerpts[0].quote = report.sources[0].content.slice(5, report.excerpts[0].end);
  assert.equal(casebookQuestionEvidence(report)[0].matches[0].available, false);
  assert.equal(casebookQuestionEvidence(report)[0].matches[0].quote, null);
});

test('missing or duplicate excerpt/original/register identities are unavailable despite matching titles', () => {
  for (const change of [r => r.excerpts.splice(0), r => r.sources.splice(0, 1),
    r => r.sources.push({...r.sources[0]}), r => r.excerpts.push({...r.excerpts[0]}),
    r => r.source_register.push({...r.source_register[0]}),
    r => r.source_register.push(null), r => r.source_register.push({id: ''})]) {
    const report = fixture(); change(report);
    const row = casebookQuestionEvidence(report)[0];
    assert.equal(row.status, 'Review required'); assert.equal(row.matches[0].available, false);
    assert.equal(row.matches[0].quote, null);
  }
});

test('unknown, duplicate and malformed recorded passage IDs never become a false no-match result', () => {
  for (const ids of [['missing'], ['Efirst', 'Efirst'], [null], 'Efirst']) {
    const report = fixture(); report.question_index[0].excerpt_ids = ids;
    const row = casebookQuestionEvidence(report)[0]; assert.equal(row.status, 'Review required');
    assert.ok(row.gaps.length || row.matches.some(match => !match.available));
  }
});

test('explicit scopes require exact anchors/known identities and cannot present a passage outside the recorded selection', () => {
  const original = {question_index: 0, question: 'What is the closing deadline?', source_ids: ['Ssecond']};
  for (const scope of [original, {...original, source_ids: []}, {...original, source_ids: ['unknown']},
    {...original, question: 'Changed question'}, {...original, source_ids: ['Sfirst', 'Sfirst']},
    {...original, unknown: true}]) {
    const report = fixture(); report.question_scopes.unshift(scope);
    const row = casebookQuestionEvidence(report)[0];
    assert.equal(row.status, 'Review required'); assert.equal(row.matches[0].available, false);
  }
});

test('malformed or duplicate scope snapshots refuse to infer the all-sources boundary', () => {
  for (const scopes of [{}, [null], [{question_index: 99}], [{question_index: false}],
    [{question_index: 1, question: 'What insurance is confirmed?', source_ids: []},
      {question_index: 1, question: 'What insurance is confirmed?', source_ids: ['Sfirst']}]]) {
    const report = fixture(); report.question_scopes = scopes;
    const row = casebookQuestionEvidence(report)[scopes.length === 2 ? 1 : 0];
    assert.equal(row.scopeLabel, 'Recorded source choice unavailable'); assert.equal(row.status, 'Review required');
  }
});

test('inconsistent recorded per-question scope metadata is explicit, not substituted', () => {
  const report = fixture(); report.question_index[0].source_scope = {mode: 'selected', source_ids: ['Sfirst'], sources_searched: 1};
  const row = casebookQuestionEvidence(report)[0];
  assert.equal(row.scopeLabel, 'Recorded source choice unavailable'); assert.equal(row.matches[0].available, false);
});

test('legacy source-only reports use their retained register and do not invent a new passage numbering scheme', () => {
  const report = fixture(); delete report.question_scopes; delete report.document_references;
  const row = casebookQuestionEvidence(report)[0];
  assert.equal(row.scopeLabel, 'All supplied sources'); assert.deepEqual(row.sourceIds, ['Sfirst', 'Ssecond']);
  assert.equal(row.matches[0].label, 'Recorded excerpt'); assert.equal(row.matches[0].excerptId, 'Efirst');
});

test('missing questions/register/passages expose gaps, and returned rows do not alias mutable inputs', () => {
  const report = fixture(); report.question_index[0].question = null; delete report.source_register;
  const row = casebookQuestionEvidence(report)[0]; assert.equal(row.question, null); assert.ok(row.gaps.length >= 2);
  const valid = fixture(), rows = casebookQuestionEvidence(valid);
  rows[2].sourceIds.push('changed'); assert.deepEqual(valid.question_scopes[1].source_ids, ['Ssecond']);
});

test('model drafts, incomplete recoveries and unrelated reports do not acquire a source-only view', () => {
  for (const fields of [{model_draft: true}, {incomplete: true}, {workflow: 'campaign'}, {question_index: {}}]) {
    assert.equal(casebookQuestionEvidence({...fixture(), ...fields}), null);
  }
});


test('missing and blank historical question wording is explicitly unavailable without replacing its literal input or evidence', () => {
  for (const question of [null, '', ' ', '\t\n', '\u0085\u001c', '\u00a0\u2003']) {
    const report = fixture(); report.question_index[0].question = question;
    const before = JSON.stringify(report), row = casebookQuestionEvidence(frozen(report))[0];
    assert.equal(row.question, question); assert.equal(row.questionAvailable, false);
    assert.equal(row.status, 'Review required');
    assert.ok(row.gaps.some(gap => gap.includes('question wording is unavailable')));
    assert.equal(row.matches[0].excerptId, 'Efirst');
    assert.equal(row.matches[0].quote, report.excerpts[0].quote);
    assert.equal(JSON.stringify(report), before);
  }
  const report = fixture(); report.question_index[0].question = '  Exact original question?  ';
  const row = casebookQuestionEvidence(report)[0];
  assert.equal(row.question, '  Exact original question?  '); assert.equal(row.questionAvailable, true);
});


test('a later inspection validates its own original text even when an earlier report used the same source identity', () => {
  const report = fixture();
  assert.equal(casebookQuestionEvidence(report)[0].matches[0].available, true);
  report.sources[0].content = report.sources[0].content.replace('Event proposed', 'Event deferred');
  const changed = casebookQuestionEvidence(report)[0];
  assert.equal(changed.status, 'Review required');
  assert.equal(changed.matches[0].available, false);
  assert.equal(changed.matches[0].quote, null);
});
