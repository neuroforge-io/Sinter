import assert from 'node:assert/strict';
import test from 'node:test';
import {reportCitationIndex, reportCitationReferences, reportCitationMatches, reportCitationMatcher} from '../src/sinter/web/report-citations.js';

test('casebook 24-character and legacy identities resolve to exact original sources', () => {
  const source = 'S' + 'a'.repeat(24), excerpt = 'E' + 'b'.repeat(24);
  const legacy = 'S' + 'c'.repeat(16);
  const references = reportCitationReferences({sources: [{id: source}, {id: legacy}],
    excerpts: [{id: excerpt, source_id: source}],
    question_index: [{matches: [{excerpt_id: 'e123', source_id: legacy}]}]});
  const text = `Related passages: ${excerpt}, ${legacy}. [e123] ${source}`;
  const matches = reportCitationMatches(text, references);
  assert.deepEqual(matches.map(row => [row.id, row.sourceId]),
    [[excerpt, source], [legacy, legacy], ['e123', legacy], [source, source]]);
  for (const row of matches) assert.equal(text.slice(row.index, row.index + row.id.length), row.id);
});

test('unknown identities and excerpt links to absent originals remain plain text', () => {
  const references = reportCitationReferences({sources: [{id: 'S1'}],
    excerpts: [{id: 'E1', source_id: 'missing'}],
    question_index: [{matches: [{excerpt_id: 'e2', source_id: 'missing'}]}]});
  assert.deepEqual(reportCitationMatches('E1 e2 S999', references), []);
  assert.equal(references.has('E1'), false);
});

test('known identity matching escapes punctuation and rejects partial or embedded IDs', () => {
  const references = reportCitationReferences({sources: [{id: 'source.a+1'}, {id: 'S1'}, {id: 'S12'}]});
  const text = 'sourceXa+1 source.a+1 | S12 S1 S123 XS1 S1_suffix S1-extra 文S1 S1文';
  assert.deepEqual(reportCitationMatches(text, references).map(row => row.id), ['source.a+1', 'S12', 'S1']);
});

test('missing and malformed optional reference collections do not create links', () => {
  for (const report of [{}, {sources: {}, excerpts: {}, question_index: {}},
    {sources: [null, {}, {id: ''}], excerpts: [null], question_index: [null]}]) {
    assert.deepEqual(reportCitationMatches('S1', reportCitationReferences(report)), []);
  }
});

test('a compiled report matcher resolves each paragraph independently', () => {
  const matcher = reportCitationMatcher(reportCitationReferences({sources: [{id: 'S1'}]}));
  assert.deepEqual(matcher('S1').map(row => row.index), [0]);
  assert.deepEqual(matcher('See S1, S1.').map(row => row.index), [4, 8]);
  assert.deepEqual(matcher('S1').map(row => row.index), [0]);
});

function passageReport() {
  const quote = '😀e\u0301';
  const excerpt = {id: 'E1', source_id: 'S1', start: 5, end: 8, quote};
  return {sources: [{id: 'S1', title: 'Retained original', content: `Lead ${quote} end`}],
    excerpts: [excerpt], document_references: [{label: 'Passage 1', excerpt_id: 'E1',
      source_id: 'S1', start: 5, end: 8}]};
}

test('registered passage aliases use exact Unicode code-point offsets', () => {
  const report = passageReport(), before = JSON.stringify(report);
  const {references, passages} = reportCitationIndex(report);
  assert.equal(passages.get('Passage 1').excerpt_id, 'E1');
  assert.equal(references.get('Passage 1'), 'S1');
  assert.deepEqual(reportCitationMatches('[Passage 1], E1. S1', references).map(row => row.sourceId), ['S1', 'S1', 'S1']);
  assert.equal(JSON.stringify(report), before);
});

test('legacy reports do not gain guessed passage aliases', () => {
  const report = passageReport();
  delete report.document_references;
  const {references, passages} = reportCitationIndex(report);
  assert.equal(passages.size, 0);
  assert.deepEqual(reportCitationMatches('[Passage 1] E1', references).map(row => row.id), ['E1']);
});

test('historical audit wording can explicitly exclude presentation aliases', () => {
  const {references, passages} = reportCitationIndex(passageReport(), {includePassages: false});
  assert.equal(passages.size, 0);
  assert.deepEqual(reportCitationMatches('Passage 1 E1 S1', references).map(row => row.id), ['E1', 'S1']);
});

test('stale or unresolved alias identities and offsets are not linked', () => {
  for (const change of [{label: 'Passage 2'}, {label: 'passage 1'}, {excerpt_id: 'missing'},
    {source_id: 'missing'}, {start: 4}, {end: 9}, {start: '5'}, {end: '8'},
    {start: -1}, {start: 8}, {end: 99}, {end: Infinity}]) {
    const report = passageReport();
    Object.assign(report.document_references[0], change);
    const {references, passages} = reportCitationIndex(report);
    assert.equal(passages.size, 0, JSON.stringify(change));
    assert.equal(references.has('Passage 1'), false);
  }
});

test('aliases require exact retained wording and not just an ID match', () => {
  for (const mutate of [report => {report.excerpts[0].quote = 'Approved';},
    report => {report.sources[0].content = 'Changed original';},
    report => {delete report.sources[0].content;},
    report => {report.excerpts[0].quote = '';},
    report => {report.excerpts[0].source_id = 'different';}]) {
    const report = passageReport(); mutate(report);
    assert.equal(reportCitationIndex(report).passages.size, 0);
  }
});

test('ambiguous original or excerpt identities cannot acquire an alias', () => {
  const original = passageReport();
  original.sources.push({...original.sources[0]});
  assert.equal(reportCitationIndex(original).passages.size, 0);
  const excerpt = passageReport();
  excerpt.excerpts.push({...excerpt.excerpts[0]});
  assert.equal(reportCitationIndex(excerpt).passages.size, 0);
});

test('new passage registrations reject blank identities without changing legacy mappings', () => {
  for (const id of ['', ' ', '\t\n', null, 12]) {
    for (const field of ['source', 'excerpt']) {
      const report = passageReport();
      if (field === 'source') {
        report.sources[0].id = id;
        report.excerpts[0].source_id = id;
        report.document_references[0].source_id = id;
      } else {
        report.excerpts[0].id = id;
        report.document_references[0].excerpt_id = id;
      }
      const {references, passages} = reportCitationIndex(report);
      assert.equal(passages.size, 0, `${field}: ${JSON.stringify(id)}`);
      assert.equal(references.has('Passage 1'), false);
      assert.deepEqual(references,
        reportCitationIndex(report, {includePassages: false}).references);
    }
  }
});

test('registry order and size bind labels to the recorded passage sequence', () => {
  const report = passageReport();
  report.excerpts.push({...report.excerpts[0], id: 'E2'});
  report.document_references.push({...report.document_references[0], label: 'Passage 2', excerpt_id: 'E2'});
  const swapped = structuredClone(report);
  swapped.document_references[0].excerpt_id = 'E2';
  swapped.document_references[1].excerpt_id = 'E1';
  assert.equal(reportCitationIndex(swapped).passages.size, 0);
  report.document_references.push({...report.document_references[0], label: 'Passage 3'});
  assert.equal(reportCitationIndex(report).passages.size, 0);
});

test('Evidence-only passages and multiple passages from one source remain distinct', () => {
  const excerpts = Array.from({length: 5}, (_, index) => ({id: `E${index + 1}`,
    source_id: 'S1', start: index * 2, end: index * 2 + 1, quote: String(index + 1)}));
  const report = {sources: [{id: 'S1', content: '1 2 3 4 5'}], excerpts,
    document_references: excerpts.map((row, index) => ({label: `Passage ${index + 1}`,
      excerpt_id: row.id, source_id: row.source_id, start: row.start, end: row.end}))};
  const {references, passages} = reportCitationIndex(report);
  assert.equal(passages.size, 5);
  assert.equal(passages.get('Passage 5').excerpt_id, 'E5');
  assert.deepEqual(reportCitationMatches('Passage 1 and Passage 5', references).map(row => row.id), ['Passage 1', 'Passage 5']);
});

test('malformed optional alias collections stay unresolved without changing legacy IDs', () => {
  for (const registry of [null, {}, 'Passage 1', [null], [{}]]) {
    const report = passageReport(); report.document_references = registry;
    const {references, passages} = reportCitationIndex(report);
    assert.equal(passages.size, 0);
    assert.equal(references.get('E1'), 'S1');
  }
});

test('alias labels cannot override a canonical source identity', () => {
  const report = passageReport();
  report.sources[0].id = 'Passage 1';
  report.excerpts[0].source_id = 'Passage 1';
  report.document_references[0].source_id = 'Passage 1';
  const {references, passages} = reportCitationIndex(report);
  assert.equal(passages.size, 0);
  assert.equal(references.get('Passage 1'), 'Passage 1');
});
