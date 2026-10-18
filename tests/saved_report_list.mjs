import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {savedReportMatches, savedReportReference, savedReportWording, savedReportPreview, renderSavedReportWording} from '../src/sinter/web/saved-report-list.js';
import {createMarkdownIndex, markdownWindow, markdown} from '../src/sinter/web/markdown.js';

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

class PreviewNode {
  constructor(tag, value = '') {
    this.tagName = tag === '#text' ? tag : tag.toUpperCase();
    this.value = value;
    this.children = [];
    this.attributes = {};
    this.style = {};
    this.className = '';
  }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  get textContent() {
    if (this.tagName === 'BR') return '\n';
    return this.value + this.children.map(child => child.textContent).join('');
  }
}

function previewElements(nodes) {
  const found = [];
  const visit = node => {
    if (!node?.tagName) return;
    found.push(node);
    for (const child of node.children) visit(child);
  };
  nodes.forEach(visit);
  return found;
}

function withPreviewDom(run) {
  const priorNode = globalThis.Node, priorDocument = globalThis.document;
  globalThis.Node = PreviewNode;
  globalThis.document = {
    createElement: tag => new PreviewNode(tag),
    createTextNode: value => new PreviewNode('#text', String(value)),
  };
  try { return run(); }
  finally {
    if (priorNode === undefined) delete globalThis.Node; else globalThis.Node = priorNode;
    if (priorDocument === undefined) delete globalThis.document; else globalThis.document = priorDocument;
  }
}


test('full renderer preserves 38 frozen pre-refactor semantic DOM cases', () => {
  const fixture = JSON.parse(readFileSync(new URL('./fixtures/markdown_legacy_rendering.v1.json', import.meta.url), 'utf8'));
  const snapshot = node => ({
    tag: node.tagName, value: node.value, className: node.className,
    attributes: Object.fromEntries(Object.entries(node.attributes).sort()),
    children: node.children.map(snapshot),
  });
  assert.equal(fixture.cases.length, 38);
  withPreviewDom(() => {
    for (const item of fixture.cases) {
      assert.deepEqual(snapshot(markdown(item.source)), item.expected, item.source);
    }
  });
});

test('oversized fence continuation stays literal through its real close, then renders fitting prose richly', () => {
  const ticks = String.fromCharCode(96).repeat(3);
  const source = ticks + 'text\n' + 'x'.repeat(2392) + '\n# Not an approval\n' + ticks
    + '\n\nClosing: no application has been submitted.';
  const report = {document_markdown: source};
  const first = savedReportWording(report);
  assert.equal(first.characters, 2400);
  assert.equal(first.literal, true);
  assert.equal(first.end, 2400);
  const second = savedReportWording(report, 2400, first.end);
  const closeEnd = source.indexOf(ticks + '\n\nClosing') + ticks.length + 1;
  assert.equal(second.literal, true);
  assert.equal(second.truncated, false);
  assert.equal(second.end, source.length);
  assert.deepEqual(second.segments.map(segment => segment.literal), [true, false]);
  assert.equal(second.segments[0].end, closeEnd - second.start);
  assert.equal(first.markdown + second.markdown, source);
  withPreviewDom(() => {
    const nodes = renderSavedReportWording(second), elements = previewElements(nodes);
    const literal = elements.find(node => node.tagName === 'PRE');
    assert.equal(literal.textContent, source.slice(second.start, closeEnd));
    assert.equal(literal.style.whiteSpace, 'pre-wrap');
    assert.equal(elements.some(node => node.tagName === 'H1'), false);
    assert.ok(elements.some(node => node.tagName === 'P'
      && node.textContent.includes('Closing: no application has been submitted.')));
  });
});


test('oversized blocks fill the remaining section after a fitting prefix', () => {
  const source = '# Garden letter\n\n' + 'Shared garden context. '.repeat(150) + '\n\nClosing A: no approval.';
  const report = {document_markdown: source}, index = createMarkdownIndex(source);
  const first = savedReportWording(report, 2400, 0, index);
  const second = savedReportWording(report, 2400, first.end, index);
  assert.equal(first.characters, 2400);
  assert.deepEqual(first.segments.map(segment => segment.literal), [false, true]);
  assert.equal(first.markdown + second.markdown, source);
  assert.equal(second.truncated, false);
  assert.ok(second.markdown.includes('Closing A: no approval.'));
  withPreviewDom(() => {
    assert.ok(previewElements(renderSavedReportWording(first)).some(node => node.tagName === 'H1'));
    const elements = previewElements(renderSavedReportWording(second));
    assert.ok(elements.some(node => node.tagName === 'P' && node.textContent === 'Closing A: no approval.'));
  });
});

test('a fitting complete block moves whole instead of being cut after a prefix', () => {
  const prefix = '# Garden letter\n\n';
  for (const body of ['p'.repeat(2395) + '\n', 'p'.repeat(2399) + '\n', '🐝'.repeat(2399) + '\n']) {
  const source = prefix + body, report = {document_markdown: source}, index = createMarkdownIndex(source);
  const first = savedReportWording(report, 2400, 0, index);
  const second = savedReportWording(report, 2400, first.end, index);
  assert.equal(first.markdown, prefix);
  assert.equal(second.markdown, body);
  assert.equal(first.literal, false); assert.equal(second.literal, false);
  assert.equal(second.truncated, false);
  }
});

test('ordinary block rendering keeps safe links, hostile text, lists, tables, quotes and hard breaks', () => {
  const source = '# Fund **title**\n\n'
    + '[safe](https://example.invalid/path) [unsafe](javascript:alert(1)) <script>no()</script>\n\n'
    + '- first item\n- second item\n\n'
    + '| Source | Amount |\n| --- | --- |\n| Local | 25 |\n\n'
    + '> quoted wording\n\nfirst line  \nsecond line';
  const wording = savedReportWording({document_markdown: source});
  assert.equal(wording.literal, false);
  withPreviewDom(() => {
    const elements = previewElements(renderSavedReportWording(wording));
    assert.ok(elements.some(node => node.tagName === 'H1'));
    assert.ok(elements.some(node => node.tagName === 'STRONG'));
    assert.ok(elements.some(node => node.tagName === 'UL'));
    assert.ok(elements.some(node => node.tagName === 'LI'));
    assert.ok(elements.some(node => node.tagName === 'TABLE'));
    assert.ok(elements.some(node => node.tagName === 'BLOCKQUOTE'));
    assert.ok(elements.some(node => node.tagName === 'BR'));
    assert.equal(elements.some(node => node.tagName === 'SCRIPT'), false);
    assert.equal(elements.some(node => node.tagName === 'A'
      && node.attributes.href === 'https://example.invalid/path'), true);
    assert.equal(elements.some(node => node.tagName === 'A'
      && node.attributes.href?.startsWith('javascript:')), false);
    assert.ok(elements.some(node => node.tagName === '#text'
      && node.textContent.includes('<script>no()</script>')));
  });
});

test('matching fence marker and length are respected in top-level, list and quote contexts', () => {
  const tick = String.fromCharCode(96), three = tick.repeat(3);
  const source = 'Intro\n\n' + tick.repeat(4) + 'text\n# hidden heading\n~~~\n'
    + three + '\nstill code\n' + tick.repeat(5) + '\n\nClosing **rich**.\n\n'
    + '- nested code\n  ' + three + 'text\n  # list code\n  ' + three + '\n\n'
    + '> quote code\n> ' + three + 'text\n> # quote code\n> ' + three + '\n';
  const wording = savedReportWording({document_markdown: source});
  assert.equal(wording.literal, false);
  withPreviewDom(() => {
    const elements = previewElements(renderSavedReportWording(wording));
    assert.equal(elements.filter(node => node.tagName === 'PRE').length, 3);
    assert.equal(elements.some(node => node.tagName === 'H1' && node.textContent.includes('hidden heading')), false);
    assert.ok(elements.some(node => node.tagName === 'UL'));
    assert.ok(elements.some(node => node.tagName === 'BLOCKQUOTE'));
    assert.ok(elements.some(node => node.tagName === 'STRONG'));
  });
});

test('long paragraph continuations never reinterpret block-looking prefixes', () => {
  const markers = ['# heading', '> quote', '- list', '1. ordered', '| A | B | ---',
    '<!-- PAGE BREAK -->', String.fromCharCode(96).repeat(3) + 'text'];
  for (const marker of markers) {
    const source = 'x'.repeat(2400) + marker;
    const report = {document_markdown: source};
    const first = savedReportWording(report);
    const second = savedReportWording(report, 2400, first.end);
    assert.equal(first.literal, true);
    assert.equal(second.literal, true, marker);
    assert.equal(second.markdown, marker);
    withPreviewDom(() => {
      const elements = previewElements(renderSavedReportWording(second));
      assert.equal(elements[0].tagName, 'PRE', marker);
      assert.equal(elements.some(node => ['H1', 'BLOCKQUOTE', 'UL', 'OL', 'TABLE'].includes(node.tagName)), false, marker);
    });
  }
});

test('CRLF, bare CR, combining marks, emoji and trailing whitespace retain exact codepoint-bounded coverage', () => {
  const source = '# Saved 🐝\r\n\r\n' + ('e\u0301 🐝 body\rbare CR\r\n').repeat(260) + '\r\n  \r\n';
  const report = {document_markdown: source}, index = createMarkdownIndex(source);
  let start = 0, joined = '', sections = 0, part;
  do {
    part = savedReportWording(report, 41, start, index);
    assert.ok(part.characters <= 41);
    assert.equal([...part.markdown].length, part.characters);
    assert.equal(part.start, start);
    assert.equal(part.end, start + part.markdown.length);
    for (const at of [part.start, part.end]) {
      if (at > 0 && at < source.length) {
        const before = source.charCodeAt(at - 1), after = source.charCodeAt(at);
        assert.equal(before >= 0xd800 && before <= 0xdbff && after >= 0xdc00 && after <= 0xdfff, false);
      }
    }
    joined += part.markdown;
    start = part.end;
    assert.ok(++sections < 1000);
  } while (part.truncated);
  assert.equal(joined, source);
  const bee = source.indexOf('🐝');
  assert.throws(() => markdownWindow(source, bee + 1, 41, index), RangeError);
  assert.throws(() => markdownWindow(source, 0, 2401, index), RangeError);
});

test('unterminated fences remain literal across every bounded section to EOF', () => {
  const source = String.fromCharCode(96).repeat(3) + 'text\n# still code\n' + ('x🐝'.repeat(1400));
  const report = {document_markdown: source}, index = createMarkdownIndex(source);
  let start = 0, joined = '', sections = 0, part;
  do {
    part = savedReportWording(report, 503, start, index);
    assert.equal(part.literal, true);
    assert.ok(part.segments.every(segment => segment.literal));
    assert.ok(part.characters <= 503);
    joined += part.markdown; start = part.end;
    assert.ok(++sections < 100);
  } while (part.truncated);
  assert.equal(joined, source);
  assert.equal(start, source.length);
});


test('list numbering never overwrites original source offsets', () => {
  const source = 'Intro\n\n- first\n- second\n\n3. third\n4. fourth\n\nClosing.';
  const index = createMarkdownIndex(source);
  assert.ok(index.blocks.every(block => Number.isInteger(block.start) && block.start >= 0));
  for (let at = 1; at < index.blocks.length; at++) assert.equal(index.blocks[at].start, index.blocks[at - 1].end);
  assert.equal(savedReportWording({document_markdown: source}, 2400, 0, index).markdown, source);
});
test('single escaped paragraph breaks keep legacy wording semantics', () => {
  const slash = String.fromCharCode(92);
  withPreviewDom(() => {
    for (const count of [1, 2, 3]) {
      const text = 'first' + slash.repeat(count) + '\nsecond';
      const elements = previewElements(renderSavedReportWording(savedReportWording({document_markdown: text})));
      assert.equal(elements.find(node => node.tagName === 'P').textContent, 'first' + slash.repeat(Math.floor(count / 2)) + '\nsecond');
    }
  });
});
test('section lookup searches the index without rescanning prior blocks', () => {
  const source = '# Heading\n\nword\n\n'.repeat(10000), index = createMarkdownIndex(source);
  let reads = 0;
  index.blocks = new Proxy(index.blocks, {get(target, key, receiver) {
    if (typeof key === 'string' && /^\d+$/.test(key)) reads++;
    return Reflect.get(target, key, receiver);
  }});
  const part = markdownWindow(source, source.length - 2, 2, index);
  assert.equal(part.markdown, source.slice(-2));
  assert.ok(reads < 100, 'index reads: ' + reads);
});
test('one cached source index serves navigation without rereading original wording', async () => {
  let builds = 0, reads = 0;
  const source = ('Saved source 🐝\n\n').repeat(700);
  const document = {get document_markdown() { reads++; return source; }};
  const h = harness(value => { builds++; return createMarkdownIndex(value); });
  const opening = h.preview.open(a);
  h.pending[0].resolve(document); await opening;
  const loadedReads = reads; let count = 0;
  while (h.preview.next()) assert.ok(++count < 100);
  while (h.preview.previous()) {}
  assert.equal(builds, 1); assert.equal(reads, loadedReads);
  h.preview.close(); assert.equal(h.preview.next(), false); assert.equal(h.preview.previous(), false);
});


test('section edges cannot invent page breaks from originally literal marker lines', () => {
  const marker = '<!-- sinter-page-break -->';
  const cases = [
    marker + '\n# ' + 'x'.repeat(2400),
    '# ' + 'h'.repeat(2397) + '\n' + marker + '\n\nClosing.',
  ];
  for (const source of cases) {
    const report = {document_markdown: source}, index = createMarkdownIndex(source);
    let start = 0, joined = '', markerSeen = false, count = 0;
    do {
      const part = savedReportWording(report, 2400, start, index);
      joined += part.markdown; start = part.end;
      withPreviewDom(() => {
        const elements = previewElements(renderSavedReportWording(part));
        assert.equal(elements.some(node => node.className === 'document-page-break'), false);
        if (part.markdown.includes(marker)) {
          markerSeen = true;
          assert.ok(elements.some(node => node.textContent.includes(marker)));
        }
      });
      assert.ok(++count < 10);
    } while (start < source.length);
    assert.equal(joined, source); assert.equal(markerSeen, true);
  }
});
test('genuine original page breaks remain dividers at a section edge', () => {
  const marker = '<!-- sinter-page-break -->';
  const source = '# ' + 'h'.repeat(2396) + '\n\n' + marker + '\n\nClosing.';
  const report = {document_markdown: source}, index = createMarkdownIndex(source);
  const first = savedReportWording(report, 2400, 0, index);
  assert.equal(first.end, 2400);
  const second = savedReportWording(report, 2400, first.end, index);
  assert.equal(second.markdown.startsWith(marker), true);
  withPreviewDom(() => {
    const elements = previewElements(renderSavedReportWording(second));
    assert.equal(elements.filter(node => node.className === 'document-page-break').length, 1);
    assert.ok(elements.some(node => node.tagName === 'P' && node.textContent.includes('Closing.')));
  });
  assert.equal(first.markdown + second.markdown, source);
});

test('malformed and empty saved wording fails explicitly', () => {
  for (const value of [null, [], {}, {document_markdown: '  '}, {document_markdown: 42}]) {
    assert.throws(() => savedReportWording(value), /readable|trimStart/);
  }
});

function harness(indexFactory = createMarkdownIndex) {
  const pending = [], states = [];
  let connected = true;
  const preview = savedReportPreview({
    load(id, signal) {
      return new Promise((resolve, reject) => pending.push({id, signal, resolve, reject}));
    },
    active: () => connected,
    changed: value => states.push(value), indexFactory,
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

test('incomplete and recorded stale status remain on every saved section', () => {
  const report = {document_markdown: 'Partial model wording. '.repeat(250), incomplete: true, review_status: 'stale'};
  const original = structuredClone(report);
  let start = 0, sections = 0, part;
  do {
    part = savedReportWording(report, 2400, start);
    assert.equal(part.incomplete, true); assert.equal(part.stale, true);
    start = part.end; sections++;
  } while (part.truncated);
  assert.ok(sections > 1);
  assert.deepEqual(report, original);
  assert.equal(savedReportWording({markdown: 'Ordinary draft'}).stale, false);
  assert.equal(savedReportWording({markdown: 'Ordinary draft'}).incomplete, false);
});
