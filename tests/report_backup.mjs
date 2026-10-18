import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeReportBackup, checkReportBackupSize, REPORT_BACKUP_MAX_BYTES} from '../src/sinter/web/report-backup.js';

const bytes = text => new TextEncoder().encode(text);
const decode = text => decodeReportBackup(bytes(text));
const report = extra => JSON.stringify({title: 'Garden 🐝 handover', markdown: 'Original\r\nwording', ...extra});

test('complete edited wording, historical evidence and unknown fields survive unchanged', () => {
  const original = JSON.parse(report({
    document_edits: {markdown: 'Edited e\u0301 wording', author: {confirmed: false}},
    sources: [{id: 'source-original', hash: 'old-snapshot', text: 'The quote is pending.'}],
    review_status: {state: 'stale', original_revision: 2}, incomplete: true,
    input_snapshot: {schema: 'sinter-casebook/v1'}, future: {flags: [null, false, 0.1]},
  }));
  assert.deepEqual(decode(JSON.stringify(original)), original);
});

test('exact byte boundary is admitted; oversized files rejected before decoding', () => {
  const prefix = '{"title":"x","markdown":"', suffix = '"}';
  const exact = prefix + 'x'.repeat(REPORT_BACKUP_MAX_BYTES - prefix.length - suffix.length) + suffix;
  assert.equal(bytes(exact).length, REPORT_BACKUP_MAX_BYTES);
  assert.equal(decode(exact).markdown.length, REPORT_BACKUP_MAX_BYTES - prefix.length - suffix.length);
  for (const size of [0, -1, 1.5, NaN, REPORT_BACKUP_MAX_BYTES + 1]) assert.throws(() => checkReportBackupSize(size));
  assert.throws(() => decodeReportBackup(new Uint8Array(REPORT_BACKUP_MAX_BYTES + 1)), /2,000,000/);
});

test('malformed UTF-8, encoded surrogate and a BOM cannot be silently repaired', () => {
  for (const value of [[0xc0, 0xaf], [0xed, 0xa0, 0x80], [0xef, 0xbb, 0xbf, ...bytes(report())]]) {
    assert.throws(() => decodeReportBackup(new Uint8Array(value)));
  }
  assert.throws(() => decodeReportBackup(report()), /original.*bytes/);
});

test('title length counts Unicode code points without trimming original inputs', () => {
  const title = '🐝'.repeat(200);
  assert.equal(decode(report({title})).title, title);
  assert.throws(() => decode(report({title: title + '🐝'})));
  for (const title of ['', ' \r\n\t', '\u001c\u0085\u3000']) assert.throws(() => decode(report({title})));
  assert.equal(decode(report({title: '  Keep these spaces  '})).title, '  Keep these spaces  ');
});

test('wrong backup kinds or malformed document fields never lose their fields', () => {
  for (const text of ['null', '[]', '{}', '{"title":"x","markdown":null}',
    report({schema: 'sinter-casebook/v1'}), report({document_edits: []}),
    report({document_edits: {}}), report({document_markdown: 4})]) assert.throws(() => decode(text));
  assert.equal(decode(report({document_edits: null})).document_edits, null);
});

test('duplicate decoded keys at any depth are rejected, including astral escapes', () => {
  for (const extra of ['"same":1,"s\\u0061me":2', '"nested":{"x":1,"x":2}',
    '"🐝":1,"\\ud83d\\udc1d":2']) {
    assert.throws(() => decode('{"title":"x","markdown":"","future":{' + extra + '}}'), /repeats.*key/);
  }
  assert.deepEqual(decode(report({a: {x: 1}, b: {x: 2}})).b, {x: 2});
});

test('escaped incomplete Unicode keys and values are rejected; complete pairs retained', () => {
  for (const extra of ['"x":"\\ud800"', '"\\udfff":"x"']) {
    assert.throws(() => decode('{"title":"x","markdown":"","future":{' + extra + '}}'), /Unicode/);
  }
  assert.equal(decode('{"title":"x","markdown":"\\ud83d\\udc1d"}').markdown, '🐝');
});

test('ordinary exact numbers survive; rounding, overflow, underflow and negative zero do not', () => {
  for (const token of ['0', '0.1', '1.2300', '1e-7', '5e-324', '0.30000000000000004', '9007199254740991']) {
    assert.equal(decode('{"title":"x","markdown":"","n":' + token + '}').n, Number(token));
  }
  for (const token of ['1e400', '9007199254740992', '9007199254740993', '1e20',
    '0.10000000000000001', '1.0000000000000001', '1e-400', '-0', '-0.0']) {
    assert.throws(() => decode('{"title":"x","markdown":"","n":' + token + '}'), /number/);
  }
});

test('nesting is bounded and punctuation in strings does not affect the scanner', () => {
  const nesting = depth => '{"title":"x","markdown":"","nested":' + '['.repeat(depth) + '0' + ']'.repeat(depth) + '}';
  assert.equal(decode(nesting(63)).title, 'x');
  assert.throws(() => decode(nesting(64)), /nested too deeply/);
  const wording = 'quoted \\" [ ] { } -1.0000000000001, "key": "key"';
  assert.equal(decode(report({future: wording})).future, wording);
  assert.throws(() => decode('{"title":"x","markdown":"unfinished}'));
});

test('prototype-looking keys remain own evidence, without changing object prototypes', () => {
  const restored = decode('{"title":"x","markdown":"","__proto__":{"polluted":true},"constructor":{"prototype":3}}');
  assert.equal(Object.hasOwn(restored, '__proto__'), true);
  assert.deepEqual(restored.__proto__, {polluted: true});
  assert.equal({}.polluted, undefined);
});
