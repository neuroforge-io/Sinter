import assert from 'node:assert/strict';
import test from 'node:test';
import {casebookSchema, explicitScopeClear, questionLines, questionScopeIssue,
  casebookDraftContext, sourceChoiceLabel} from '../src/sinter/web/casebook-scope.js';

const id = (prefix, digit) => prefix + String(digit).repeat(24);
const documents = [{id: id('S', 1), title: 'Fictional supplier enquiry'},
  {id: id('S', 2), title: 'Fictional governing rule'}];
const text = 'Which applicants are eligible?\nWhat production costs need checking?';
const choice = changes => ({question_index: 0, question: questionLines(text)[0],
  source_ids: [documents[1].id], ...changes});

test('duplicate source titles still have distinct stable accessible source choices', () => {
  const first = {...documents[0], title: 'Same supplied title'};
  const second = {...documents[1], title: 'Same supplied title'};
  assert.notEqual(sourceChoiceLabel(1, first, 0), sourceChoiceLabel(1, second, 1));
  assert.ok(sourceChoiceLabel(1, first, 0).includes(first.id));
  assert.ok(sourceChoiceLabel(1, second, 1).includes(second.id));
  const newSource = {title: 'Same supplied title'};
  assert.notEqual(sourceChoiceLabel(1, newSource, 0), sourceChoiceLabel(1, newSource, 1));
});

test('scope schema is v2 only for explicit choices including an explicit empty choice', () => {
  assert.equal(casebookSchema([]), 'sinter-casebook/v1');
  assert.equal(casebookSchema([choice()]), 'sinter-casebook/v2');
  assert.equal(casebookSchema([choice({source_ids: []})]), 'sinter-casebook/v2');
});

test('clear intent requires an own typed empty list, never the initial empty state', () => {
  for (const book of [null, {}, {question_scopes: null}, {question_scopes: false},
    {question_scopes: ''}, {question_scopes: {}}, {question_scopes: [choice()]},
    Object.create({question_scopes: []})]) assert.equal(explicitScopeClear(book), false);
  assert.equal(explicitScopeClear({question_scopes: []}), true);
  assert.equal(explicitScopeClear(JSON.parse(JSON.stringify({question_scopes: []}))), true);
});

test('new shared API helper grants no capability to an old caller by path', async () => {
  const {request} = await import('../src/sinter/web/api.js?casebook-schema-proof');
  const calls = [], originalFetch = globalThis.fetch;
  globalThis.fetch = async (path, options) => {
    calls.push({path, headers: options.headers});
    return {ok: true, json: async () => path === '/api/session' ? {token: 'fictional'} : {ok: true}};
  };
  try {
    await request('/api/casebooks/fictional');
    await request('/api/casebooks/validate', {data: {document: {schema: 'sinter-casebook/v1'}}});
    await request('/api/casebooks/fictional', {headers: {'X-Sinter-Casebook-Schema': 'sinter-casebook/v2'}});
    const bookCalls = calls.filter(row => row.path !== '/api/session');
    assert.equal(bookCalls[0].headers['X-Sinter-Casebook-Schema'], undefined);
    assert.equal(bookCalls[1].headers['X-Sinter-Casebook-Schema'], undefined);
    assert.equal(bookCalls[1].headers['X-Sinter-Token'], 'fictional');
    assert.equal(bookCalls[2].headers['X-Sinter-Casebook-Schema'], 'sinter-casebook/v2');
  } finally { globalThis.fetch = originalFetch; }
});

test('question splitting and trimming matches the Python anchors without changing wording', () => {
  assert.deepEqual(questionLines(' \tFirst 🐝 e\u0301\u00a0\r\n\u2000Second\u2000\u0085Third\u2029\u001cFourth\u001f'),
    ['First 🐝 e\u0301', 'Second', 'Third', 'Fourth']);
  assert.deepEqual(questionLines('\n\n \r\n'), []);
  assert.deepEqual(questionLines('\uFEFFliteral\uFEFF'), ['\uFEFFliteral\uFEFF']);
});

test('explicit none remains admitted while unknown, removed and duplicated sources block saving', () => {
  assert.equal(questionScopeIssue(text, [choice()], documents), '');
  assert.equal(questionScopeIssue(text, [choice({source_ids: []})], documents), '');
  for (const source_ids of [[id('S', 3)], [true], [documents[1].id, documents[1].id], null, 'all']) {
    assert.match(questionScopeIssue(text, [choice({source_ids})], documents), /Review source choices/i);
  }
  assert.match(questionScopeIssue(text, [choice()], documents.slice(0, 1)), /no longer available/);
});

test('changed, reordered, removed, malformed and duplicate question anchors block broadened preparation', () => {
  for (const changes of [{question: 'Changed question'}, {question_index: true},
    {question_index: -1}, {question_index: 1.5}, {question_index: 2}, {extra: true}]) {
    assert.ok(questionScopeIssue(text, [choice(changes)], documents));
  }
  assert.ok(questionScopeIssue(questionLines(text).reverse().join('\n'), [choice()], documents));
  assert.ok(questionScopeIssue('', [choice()], documents));
  assert.ok(questionScopeIssue(text, [choice(), choice()], documents));
  assert.ok(questionScopeIssue(text, null, documents));
});

const legacy = {question_index: Array.from({length: 10}, (_, n) => ({question: `Question ${n}`})),
  excerpts: Array.from({length: 10}, (_, n) => ({id: id('E', n), quote: `Exact text ${n}`}))};

test('unscoped exact preview keeps the original first-eight prose contract', () => {
  const expected = {questions: legacy.question_index.slice(0, 8).map(row => row.question),
    excerpts: legacy.excerpts.slice(0, 8).map(row => ({id: row.id, text: row.quote}))};
  assert.equal(JSON.stringify(casebookDraftContext(legacy)), JSON.stringify(expected));
  assert.equal(JSON.stringify(casebookDraftContext({...legacy, question_scopes: []})), JSON.stringify(expected));
});

test('scoped preview preserves each question boundary and the explicit zero-evidence question', () => {
  const first = id('E', 1), second = id('E', 2);
  const report = {source_register: documents,
    question_scopes: [choice({source_ids: []})],
    question_index: [{question: questionLines(text)[0], excerpt_ids: []},
      {question: questionLines(text)[1], excerpt_ids: [first, second]}],
    excerpts: [{id: first, source_id: documents[0].id, quote: 'Exact unapproved enquiry 🐝'},
      {id: second, source_id: documents[1].id, quote: 'Exact conditional rule e\u0301'}]};
  const before = JSON.stringify(report);
  assert.deepEqual(casebookDraftContext(report), {
    questions: [{question_index: 0, question: questionLines(text)[0], source_ids: [], excerpt_ids: []},
      {question_index: 1, question: questionLines(text)[1], source_ids: documents.map(row => row.id), excerpt_ids: [first, second]}],
    excerpts: report.excerpts.map(row => ({id: row.id, source_id: row.source_id, text: row.quote})),
  });
  assert.equal(JSON.stringify(report), before);
  const tampered = structuredClone(report);
  tampered.question_index[0].excerpt_ids = [first];
  assert.throws(() => casebookDraftContext(tampered), /outside/);
  for (const alter of [
    copy => { copy.question_scopes.push({...copy.question_scopes[0]}); },
    copy => { copy.question_scopes[0].question = 'Changed question'; },
    copy => { copy.question_scopes[0].source_ids = [id('S', 3)]; },
  ]) {
    const copy = structuredClone(report); alter(copy);
    assert.throws(() => casebookDraftContext(copy));
  }
});

test('scoped bounded preview never cites an excerpt omitted by its actual eight-excerpt limit', () => {
  const report = {...legacy, source_register: documents,
    question_scopes: [choice({question: 'Question 0', source_ids: [documents[0].id]})],
    excerpts: legacy.excerpts.map(row => ({...row, source_id: documents[0].id})),
    question_index: legacy.question_index.map((row, index) => ({...row,
      excerpt_ids: [legacy.excerpts[index].id]}))};
  const packet = casebookDraftContext(report), sent = new Set(packet.excerpts.map(row => row.id));
  assert.equal(packet.questions.length, 8);
  assert.equal(packet.excerpts.length, 8);
  assert.equal(packet.questions.every(row => row.excerpt_ids.every(reference => sent.has(reference))), true);
  assert.equal(packet.questions[0].source_ids.length, 1);
});
