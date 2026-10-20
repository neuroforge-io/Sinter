import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';

class Element {
  constructor(tag, text = '') {
    this.tag = tag; this.text = text; this.children = []; this.parentNode = null;
    this.className = ''; this.dataset = {}; this.events = new Map(); this.hidden = false; this.open = false;
  }
  get isConnected() { return this === document.body || Boolean(this.parentNode?.isConnected); }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.replaceChildren(); this.text = String(value); }
  append(...children) {
    for (let child of children) {
      if (!(child instanceof Element)) child = new Element('#text', String(child));
      child.remove(); child.parentNode = this; this.children.push(child);
    }
  }
  replaceChildren(...children) {
    for (const child of this.children) child.parentNode = null;
    this.children = []; this.text = ''; this.append(...children);
  }
  insertBefore(node, before) {
    node.remove(); const index = this.children.indexOf(before); assert.ok(index >= 0);
    node.parentNode = this; this.children.splice(index, 0, node);
  }
  after(node) {
    assert.ok(this.parentNode); node.remove();
    const parent = this.parentNode, index = parent.children.indexOf(this);
    node.parentNode = parent; parent.children.splice(index + 1, 0, node);
  }
  remove() {
    if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }
  contains(node) { return this === node || this.children.some(child => child.contains(node)); }
  setAttribute(name, value) { this[name] = String(value); }
  addEventListener(name, listener) { this.events.set(name, listener); }
  async fire(name = 'click') { this.focus(); return this.events.get(name)?.({currentTarget: this}); }
  focus() { document.activeElement = this; observations.push(['focus', this]); }
  scrollIntoView() { observations.push(['scroll', this]); }
  getClientRects() {
    if (!this.isConnected) return [];
    for (let node = this; node; node = node.parentNode) if (node.hidden) return [];
    return [{}];
  }
  querySelectorAll(selector) {
    return walk(this).slice(1).filter(node => selector[0] === '.'
      ? node.className.split(' ').includes(selector.slice(1)) : node.tag === selector);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
let observations = [];
globalThis.Node = Element;
globalThis.window = new EventTarget();
globalThis.document = {createElement: tag => new Element(tag), createTextNode: text => new Element('#text', text),
  body: new Element('body'), activeElement: null};
const realCrypto = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
const useCrypto = value => Object.defineProperty(globalThis, 'crypto', {value, configurable: true});
useCrypto(webcrypto);
const {reportPassageNavigation} = await import('../src/sinter/web/report-passage-navigation.js');
const {casebookQuestionEvidence} = await import('../src/sinter/web/casebook-question-evidence.js');
const {documentMarkdown} = await import('../src/sinter/web/documents.js');
const drafts = await import('../src/sinter/web/report-drafts.js');
const walk = node => [node, ...node.children.flatMap(walk)];
const node = (tag, text = '', className = '') => {
  const value = new Element(tag, text); value.className = className; return value;
};
const defer = () => {
  let resolve, reject; const promise = new Promise((a, b) => {resolve = a; reject = b;});
  return {promise, resolve, reject};
};
function delayedCrypto() {
  const calls = [];
  useCrypto({subtle: {digest(algorithm, bytes) {
    const gate = defer(); calls.push({...gate,
      async pass() { gate.resolve(await webcrypto.subtle.digest(algorithm, bytes)); }});
    return gate.promise;
  }}});
  return calls;
}
function setup(t, {corruptTail = false, detached = false} = {}) {
  observations = []; document.body.replaceChildren(); drafts.clearReportDrafts(); useCrypto(webcrypto);
  let external = 0;
  const previousFetch = globalThis.fetch, previousBridge = globalThis.sinterBrowser;
  globalThis.fetch = () => {external++; throw new Error('Unexpected network request');};
  globalThis.sinterBrowser = {request: () => {external++; throw new Error('Unexpected app request');}};
  const prefix = '🐝 e\u0301 Start.\n', quote = 'No named owner has accepted.', middle = '\nA different paragraph.\n';
  const content = prefix + quote + middle + quote + '\nEnd.';
  const length = text => Array.from(text).length;
  const ranges = [[length(prefix), length(prefix + quote)],
    [length(prefix + quote + middle), length(prefix + quote + middle + quote)]];
  const sha256 = createHash('sha256').update(content).digest('hex');
  const report = {workflow: 'casebook', model_draft: false, incomplete: false, review_status: 'stale',
    title: 'Historical fictional handover', markdown: 'Historical evidence',
    document_edits: {markdown: 'Human wording: Passage 1 and Passage 2.'},
    sources: [{id: 'S1', title: 'Retained source', sha256, content: content + (corruptTail ? '\nChanged tail.' : '')}],
    source_register: [{id: 'S1', title: 'Retained source', sha256}],
    excerpts: ranges.map(([start, end], i) => ({id: 'E' + (i + 1), source_id: 'S1', start, end, quote})),
    document_references: ranges.map(([start, end], i) => ({
      label: 'Passage ' + (i + 1), excerpt_id: 'E' + (i + 1), source_id: 'S1', start, end})),
    question_index: [{question: 'Who accepted ownership?', excerpt_ids: ['E1', 'E2']}]};
  const root = node('section'), doc = node('section'), evidence = node('section'), sources = node('aside');
  evidence.hidden = true; root.append(doc, evidence); evidence.append(sources);
  if (!detached) document.body.append(root);
  const original = node('details', '', 'source-jump'), originalText = node('pre', report.sources[0].content);
  original.dataset.sourceId = 'S1'; original.append(originalText); sources.append(original);
  const switches = [], fallback = [], heading = node('h2', 'Document heading');
  doc.append(heading);
  let active = true, nav;
  const select = (view, ticket) => {
    assert.equal(nav.owns(ticket), true); switches.push(view);
    doc.hidden = view !== 'document'; evidence.hidden = view !== 'evidence';
  };
  nav = reportPassageNavigation({report, root, sources,
    isActive: () => active && root.isConnected && !root.hidden,
    showEvidence: ticket => select('evidence', ticket),
    showDocument: ticket => select('document', ticket),
    focusReader: reason => {fallback.push(reason); heading.focus();}});
  const projections = casebookQuestionEvidence(report)[0].matches;
  const entries = projections.map((passage, index) => {
    const details = node('details'), pre = node('pre', passage.quote), originalButton = node('button', 'Open original');
    details.append(pre, originalButton); evidence.append(details);
    const target = nav.register({questionIndex: 0, passage, details, quoteNode: pre});
    const citation = node('button', passage.label);
    doc.append(citation);
    nav.bind(citation, report.document_references[index]);
    return {details, pre, originalButton, target, citation};
  });
  const secondInvoker = node('button', 'Passage 1');
  doc.append(secondInvoker); nav.bind(secondInvoker, report.document_references[0]);
  drafts.registerReportDraft(report, documentMarkdown(report), {saved: true});
  const snapshot = () => ({report: structuredClone(report), markdown: documentMarkdown(report),
    state: structuredClone(drafts.reportSaveState(report))});
  t.after(() => {
    nav.dispose(); root.remove(); drafts.clearReportDrafts();
    globalThis.fetch = previousFetch; globalThis.sinterBrowser = previousBridge;
    useCrypto(webcrypto); assert.equal(external, 0);
  });
  const open = invoker => {invoker.focus(); return nav.open({invoker});};
  const full = at => {
    const item = entries[at]; item.details.open = true; item.originalButton.focus();
    return nav.followOriginal({target: item.target, sourceId: 'S1', invoker: item.originalButton});
  };
  const back = () => root.querySelector('.passage-return');
  return {report, root, doc, evidence, sources, original, originalText, entries, secondInvoker,
    nav, snapshot, switches, fallback, open, full, back, setActive: value => {active = value;}};
}

test('two identical quotations in one historical source retain distinct Unicode ranges and exact return origins', async t => {
  const f = setup(t), before = f.snapshot();
  assert.notEqual(f.report.excerpts[0].start, f.report.excerpts[1].start);
  assert.equal(await f.open(f.entries[0].citation), true);
  assert.equal(f.back().parentNode.parentNode, f.entries[0].details);
  assert.match(f.entries[0].details.textContent, /Showing Passage 1 under Question 1/);
  await f.back().fire(); assert.equal(document.activeElement, f.entries[0].citation);
  assert.equal(await f.open(f.entries[1].citation), true);
  assert.equal(f.back().parentNode.parentNode, f.entries[1].details);
  assert.equal(await f.full(1), true); assert.equal(f.back().parentNode.parentNode, f.original);
  assert.equal(f.originalText.textContent, f.report.sources[0].content);
  await f.back().fire(); assert.equal(document.activeElement, f.entries[1].citation);
  assert.deepEqual(f.snapshot(), before);
});

test('same passage uses the latest successful invoker and carries one Return through full original', async t => {
  const f = setup(t), before = f.snapshot();
  await f.open(f.entries[0].citation); await f.back().fire();
  await f.open(f.secondInvoker); await f.full(0);
  assert.equal(f.root.querySelectorAll('.passage-return').length, 1);
  await f.back().fire(); assert.equal(document.activeElement, f.secondInvoker);
  assert.deepEqual(f.snapshot(), before);
});

test('failed new inspection preserves the last successful quote and Return', async t => {
  const f = setup(t), before = f.snapshot(); await f.open(f.entries[0].citation);
  const back = f.back(), calls = delayedCrypto(), pending = f.full(1);
  assert.equal(f.back(), back); assert.equal(back.parentNode.parentNode, f.entries[0].details);
  calls[0].reject(new Error('Local digest refused'));
  assert.equal(await pending, false); assert.equal(f.back(), back);
  assert.match(f.entries[1].details.textContent, /Local digest refused/);
  await back.fire(); assert.equal(document.activeElement, f.entries[0].citation);
  assert.deepEqual(f.snapshot(), before);
});

test('Return cancels pending inspection; late success cannot reopen or move focus', async t => {
  const f = setup(t); await f.open(f.entries[0].citation);
  const calls = delayedCrypto(), pending = f.full(1);
  await f.back().fire();
  const focus = document.activeElement, switched = [...f.switches], events = observations.length;
  await calls[0].pass(); assert.equal(await pending, false);
  assert.equal(f.back(), null); assert.equal(document.activeElement, focus);
  assert.deepEqual(f.switches, switched); assert.equal(observations.length, events);
});

for (const stale of ['success', 'failure']) test('out-of-order ' + stale + ' cannot overwrite a newer landing', async t => {
  const f = setup(t), before = f.snapshot(), calls = delayedCrypto();
  const first = f.open(f.entries[0].citation), second = f.open(f.entries[1].citation);
  await calls[1].pass(); assert.equal(await second, true);
  const content = f.root.textContent, focus = document.activeElement, events = observations.length;
  if (stale === 'success') await calls[0].pass(); else calls[0].reject(new Error('Obsolete failure'));
  assert.equal(await first, false);
  assert.equal(f.root.textContent, content); assert.equal(document.activeElement, focus);
  assert.equal(observations.length, events); assert.deepEqual(f.snapshot(), before);
});

for (const action of ['hidden', 'inactive', 'replaced', 'disposed', 'focus moved']) {
  test('pending validation is fenced when the reader is ' + action, async t => {
    const f = setup(t), before = f.snapshot(), calls = delayedCrypto();
    const pending = f.open(f.entries[0].citation);
    if (action === 'hidden') f.root.hidden = true;
    if (action === 'inactive') f.setActive(false);
    if (action === 'replaced') {f.nav.invalidate(); f.doc.replaceChildren(node('p', 'New document'));}
    if (action === 'disposed') f.nav.dispose();
    if (action === 'focus moved') f.secondInvoker.focus();
    const events = observations.length;
    await calls[0].pass(); assert.equal(await pending, false);
    assert.equal(f.back(), null); assert.deepEqual(f.switches, []);
    assert.equal(observations.length, events); assert.deepEqual(f.snapshot(), before);
  });
}

test('removed invoker and tampered displayed quote cannot gain a landing', async t => {
  const f = setup(t), calls = delayedCrypto(), pending = f.open(f.entries[0].citation);
  f.entries[0].citation.remove(); await calls[0].pass();
  assert.equal(await pending, false); assert.equal(f.back(), null);
  useCrypto(webcrypto); f.entries[1].pre.textContent = 'A substituted quotation';
  assert.equal(await f.open(f.entries[1].citation), false);
  assert.equal(f.back(), null); assert.deepEqual(f.switches, []);
});

test('real local SHA rejects changed surrounding source text even with unchanged quote/range', async t => {
  const f = setup(t, {corruptTail: true}), before = f.snapshot();
  assert.equal(await f.open(f.entries[0].citation), false);
  assert.match(f.doc.textContent, /does not match its recorded source hash/);
  assert.equal(f.back(), null); assert.deepEqual(f.switches, []);
  assert.deepEqual(f.snapshot(), before);
});

test('binding changes, duplicate references and missing original text fail without substituting a source', async t => {
  const f = setup(t);
  f.entries[0].citation.textContent = 'Passage 2';
  assert.equal(await f.open(f.entries[0].citation), false);
  f.report.document_references.push({...f.report.document_references[1]});
  const before = f.snapshot();
  assert.equal(await f.open(f.entries[1].citation), false);
  assert.equal(f.back(), null); assert.deepEqual(f.switches, []);
  assert.deepEqual(f.snapshot(), before);
});

test('removed successful origin returns honestly to the heading; disposal removes ephemeral controls', async t => {
  const f = setup(t), before = f.snapshot();
  await f.open(f.entries[0].citation); f.entries[0].citation.remove();
  await f.back().fire();
  assert.match(f.fallback[0], /reading position is no longer available/);
  assert.equal(document.activeElement.tag, 'h2');
  f.nav.dispose(); assert.equal(f.back(), null); assert.deepEqual(f.snapshot(), before);
});


test('an original text mismatch preserves the verified passage and its Return', async t => {
  const f = setup(t), before = f.snapshot();
  await f.open(f.entries[0].citation);
  const back = f.back(); f.originalText.textContent = 'Different current project text';
  assert.equal(await f.full(0), false); assert.equal(f.back(), back);
  assert.equal(back.parentNode.parentNode, f.entries[0].details);
  assert.deepEqual(f.snapshot(), before);
});

test('changed retained binding during hashing cannot use the earlier successful digest', async t => {
  const f = setup(t), calls = delayedCrypto(), pending = f.open(f.entries[0].citation);
  f.report.sources[0].content += ' A later change.';
  const changed = f.snapshot();
  await calls[0].pass(); assert.equal(await pending, false);
  assert.deepEqual(f.switches, []); assert.equal(f.back(), null);
  assert.deepEqual(f.snapshot(), changed);
});

test('duplicate excerpt identities cannot redirect a retained passage', async t => {
  const f = setup(t);
  f.report.excerpts[1].id = f.report.excerpts[0].id;
  const before = f.snapshot();
  assert.equal(await f.open(f.entries[0].citation), false);
  assert.equal(f.back(), null); assert.deepEqual(f.switches, []);
  assert.deepEqual(f.snapshot(), before);
});


test('a detached report can bind its first-render passages before it is mounted', async t => {
  const f = setup(t, {detached: true}), before = f.snapshot();
  assert.equal(f.root.isConnected, false);
  assert.equal(f.nav.has(f.report.document_references[0]), true);
  document.body.append(f.root);
  assert.equal(await f.open(f.entries[0].citation), true);
  assert.equal(f.back().parentNode.parentNode, f.entries[0].details);
  await f.back().fire(); assert.equal(document.activeElement, f.entries[0].citation);
  assert.deepEqual(f.snapshot(), before);
});

test('displayed source metadata changed during hashing cancels the earlier destination', async t => {
  const f = setup(t), calls = delayedCrypto(), pending = f.open(f.entries[0].citation);
  f.report.sources[0].kind = 'Changed metadata';
  const changed = f.snapshot();
  await calls[0].pass(); assert.equal(await pending, false);
  assert.equal(f.back(), null); assert.deepEqual(f.switches, []);
  assert.deepEqual(f.snapshot(), changed);
});


test('an unbound original button changed during hashing cannot replace a successful Return', async t => {
  const f = setup(t), before = f.snapshot();
  await f.open(f.entries[0].citation);
  const back = f.back(), calls = delayedCrypto(), pending = f.full(0);
  f.entries[0].originalButton.textContent = 'A different original';
  await calls[0].pass(); assert.equal(await pending, false);
  assert.equal(f.back(), back); assert.equal(back.parentNode.parentNode, f.entries[0].details);
  assert.deepEqual(f.switches, ['evidence']); assert.deepEqual(f.snapshot(), before);
});

test('an unbound original return origin with changed wording uses the honest heading fallback', async t => {
  const f = setup(t), before = f.snapshot();
  f.doc.hidden = true; f.evidence.hidden = false;
  assert.equal(await f.full(0), true);
  assert.equal(f.back().textContent, 'Return to evidence');
  f.entries[0].originalButton.textContent = 'A different original';
  await f.back().fire();
  assert.match(f.fallback[0], /reading position is no longer available/);
  assert.equal(document.activeElement.tag, 'h2');
  assert.deepEqual(f.switches, ['evidence', 'evidence', 'document']);
  assert.deepEqual(f.snapshot(), before);
});

test.after(() => {
  if (realCrypto) Object.defineProperty(globalThis, 'crypto', realCrypto);
  else delete globalThis.crypto;
});
