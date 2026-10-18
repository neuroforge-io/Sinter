import test from 'node:test';
import assert from 'node:assert/strict';

// A small event/DOM boundary keeps race tests deterministic; actual rendering and
// service persistence are separately exercised through report_recovery_browser.py.
class Element {
  constructor(tag, text = '') {
    this.tag = tag; this.children = []; this.parent = null; this.text = text; this.events = new Map();
    this.value = ''; this.id = ''; this.type = ''; this.disabled = false; this.hidden = false;
    this.readOnly = false; this.rows = 0; this.spellcheck = true; this.open = false;
  }
  get isConnected() { return this === document.body || Boolean(this.parent?.isConnected); }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.replaceChildren(); this.text = String(value); }
  append(...children) {
    for (let child of children) {
      if (!(child instanceof Element)) child = new Element('#text', String(child));
      child.parent = this; this.children.push(child);
    }
  }
  replaceChildren(...children) {
    for (const child of this.children) child.parent = null;
    this.children = []; this.text = ''; this.append(...children);
  }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, listener) {
    const listeners = this.events.get(name) || []; listeners.push(listener); this.events.set(name, listeners);
  }
  async fire(name) { for (const listener of this.events.get(name) || []) await listener({preventDefault() {}}); }
  focus() { document.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; void this.fire('close'); }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    this.parent = null;
  }
}
globalThis.Node = Element;
globalThis.document = {createElement: tag => new Element(tag), createTextNode: text => new Element('#text', text),
  body: new Element('body'), activeElement: null};
globalThis.window = new EventTarget();
const {savedReportRestore} = await import('../src/sinter/web/saved-report-restore.js');
const drafts = await import('../src/sinter/web/report-drafts.js');
const {documentMarkdown} = await import('../src/sinter/web/documents.js');
const walk = node => [node, ...node.children.flatMap(walk)];
const find = (root, predicate) => {
  const found = walk(root).find(predicate); assert.ok(found, 'Expected control exists'); return found;
};
const button = (root, name) => find(root, node => node.tag === 'button' && node.textContent === name);
const file = (title, extras = {}) => {
  const data = new TextEncoder().encode(JSON.stringify({title, markdown: 'Original evidence', ...extras}));
  return {name: title + '.json', size: data.length, arrayBuffer: async () => data.buffer};
};
const defer = () => { let resolve, reject; const promise = new Promise((a, b) => {resolve = a; reject = b;}); return {promise, resolve, reject}; };

function setup(t, options = {}) {
  drafts.clearReportDrafts(); document.body.replaceChildren();
  const writes = [], busy = [];
  globalThis.sinterBrowser = {request: async (path, request) => {
    assert.equal(path, '/api/reports'); writes.push(structuredClone(request.data.report));
    return options.respond ? options.respond(path, request) : {id: 'a'.repeat(32)};
  }};
  const view = savedReportRestore({setBusy: value => busy.push(value), onCheckSaved: async () => true, ...options});
  document.body.append(view.element);
  t.after(() => { view.dispose(); view.element.remove(); delete globalThis.sinterBrowser; drafts.clearReportDrafts(); });
  const input = find(view.element, node => node.tag === 'input' && node.type === 'file');
  return {view, input, writes, busy, async choose(value) { input.files = [value]; await input.fire('change'); }};
}

test('selection is local; oversize clears previous selection before reading and retains an attempted draft', async t => {
  const {view, choose, writes} = setup(t, {respond: async () => {throw new TypeError('Lost acknowledgement');}});
  await choose(file('A'));
  assert.equal(drafts.unsavedReportDrafts().length, 0); assert.equal(writes.length, 0);
  await button(view.element, 'Restore as a new saved copy').fire('click');
  assert.equal(writes.length, 1); assert.equal(drafts.unsavedReportDrafts().length, 1);
  let read = false;
  await choose({name: 'oversize.json', size: 2_000_001, arrayBuffer: async () => {read = true;}});
  assert.equal(read, false); assert.equal(writes.length, 1);
  assert.equal(button(view.element, 'Restore as a new saved copy').disabled, true);
  assert.equal(drafts.unsavedReportDrafts()[0].report.title, 'A');
  assert.match(view.element.textContent, /2,000,000/);
});

test('stale reads and errors cannot replace newer selection or a disposed view', async t => {
  const {view, input, choose} = setup(t), old = defer();
  input.files = [{name: 'old.json', size: 80, arrayBuffer: () => old.promise}];
  const previous = input.fire('change');
  await choose(file('B')); old.reject(new Error('Old failed read')); await previous;
  assert.match(view.element.textContent, /B\.json/); assert.doesNotMatch(view.element.textContent, /Old failed read/);
  const late = defer(); input.files = [{name: 'late.json', size: 80, arrayBuffer: () => late.promise}];
  const disposed = input.fire('change'); view.dispose();
  const before = view.element.textContent; late.resolve(await file('Late').arrayBuffer()); await disposed;
  assert.equal(view.element.textContent, before);
});

test('double clicks send one complete copy; refresh failure and later edits cannot re-enable restore', async t => {
  const response = defer();
  const {view, choose, writes, busy} = setup(t, {respond: () => response.promise,
    onSaved: async () => {throw new Error('List refresh failed');}});
  const original = {sources: [{id: 'source-A', text: 'Unknown owner.'}],
    incomplete: true, review_status: 'stale', document_edits: {markdown: 'Edited wording'}};
  await choose(file('A', original));
  const restore = button(view.element, 'Restore as a new saved copy');
  const first = restore.fire('click'); await restore.fire('click');
  assert.equal(writes.length, 1); assert.equal(restore.disabled, true);
  const candidate = drafts.unsavedReportDrafts()[0].report;
  assert.deepEqual(writes[0], {title: 'A', markdown: 'Original evidence', ...original});
  response.resolve({id: 'b'.repeat(32)}); await first;
  assert.equal(drafts.reportSaveState(candidate).kind, 'saved'); assert.deepEqual(busy, [true, false]);
  assert.match(view.element.textContent, /acknowledged.*bbbb/); assert.match(view.element.textContent, /List refresh failed/);
  candidate.document_edits.markdown = 'Later applied edit';
  drafts.trackReportEdits(candidate, documentMarkdown(candidate));
  assert.equal(drafts.reportSaveState(candidate).kind, 'pending');
  assert.equal(restore.disabled, true); await restore.fire('click'); assert.equal(writes.length, 1);
});

test('uncertain writes require a list check, cancellation and fresh explicit approval; arbitrary forms block retry', async t => {
  let calls = 0, checks = 0;
  const {view, choose, writes} = setup(t, {
    respond: async () => ++calls === 1 ? null : {id: 'c'.repeat(32)},
    onCheckSaved: async () => {checks++; return true;},
  });
  await choose(file('A')); await button(view.element, 'Restore as a new saved copy').fire('click');
  const candidate = drafts.unsavedReportDrafts()[0].report;
  assert.equal(drafts.reportSaveState(candidate).kind, 'unconfirmed');
  const retry = button(view.element, 'Restore an additional copy'), check = button(view.element, 'Check saved list before retrying');
  assert.equal(retry.disabled, true);
  await check.fire('click'); assert.equal(checks, 1); assert.equal(writes.length, 1); assert.equal(retry.disabled, false);
  const cancelled = retry.fire('click'); await button(document.body, 'Cancel').fire('click'); await cancelled;
  assert.equal(writes.length, 1);
  const changed = retry.fire('click');
  drafts.trackReportForm(candidate, 'future-owner-form', {owner: 'unknown'});
  await button(document.body, 'Restore additional copy').fire('click'); await changed;
  assert.equal(writes.length, 1); assert.equal(retry.disabled, true);
  drafts.clearReportForm(candidate, 'future-owner-form');
  drafts.trackReportEditor(candidate, 'Unapplied input');
  await check.fire('click'); assert.equal(retry.disabled, true);
  drafts.trackReportEditor(candidate, '', false);
  await check.fire('click'); const approved = retry.fire('click');
  await button(document.body, 'Restore additional copy').fire('click'); await approved;
  assert.equal(writes.length, 2); assert.equal(drafts.reportSaveState(candidate).kind, 'saved');
  assert.equal(retry.disabled, true);
});

test('a later rejected retry cannot erase the first uncertain attempt or bypass list-check consent', async t => {
  let calls = 0;
  const {view, choose, writes} = setup(t, {respond: async () => {
    const error = new Error('Rejected retry'); error.status = 400;
    if (++calls === 1) throw new TypeError('Lost acknowledgement');
    throw error;
  }});
  await choose(file('A')); await button(view.element, 'Restore as a new saved copy').fire('click');
  await button(view.element, 'Check saved list before retrying').fire('click');
  const retry = button(view.element, 'Restore an additional copy'), approved = retry.fire('click');
  await button(document.body, 'Restore additional copy').fire('click'); await approved;
  assert.equal(writes.length, 2); assert.equal(retry.disabled, true);
  assert.match(view.element.textContent, /earlier save remains unconfirmed/);
  assert.equal(button(view.element, 'Check saved list before retrying').hidden, false);
});

test('disposal after dispatch cannot lose acknowledgement or skip busy release', async t => {
  const response = defer(), {view, choose, busy} = setup(t, {respond: () => response.promise});
  await choose(file('A')); const pending = button(view.element, 'Restore as a new saved copy').fire('click');
  const candidate = drafts.unsavedReportDrafts()[0].report; view.dispose(); view.element.remove();
  response.resolve({id: 'd'.repeat(32)}); await pending;
  assert.equal(drafts.reportSaveState(candidate).kind, 'saved');
  assert.equal(drafts.reportSavedCopyId(candidate), 'd'.repeat(32)); assert.deepEqual(busy, [true, false]);
});

test('pre-dispatch callback failure remains not-sent and cleanup failures cannot escape', async t => {
  let notified = 0;
  const {view, choose, writes} = setup(t, {
    onChanged: () => {if (++notified >= 1) throw new Error('Broken pending view');},
    setBusy: value => {if (!value) throw new Error('Broken busy view');},
  });
  await choose(file('A')); await button(view.element, 'Restore as a new saved copy').fire('click');
  assert.equal(writes.length, 0);
  assert.equal(drafts.reportSaveState(drafts.unsavedReportDrafts()[0].report).kind, 'not-sent');
  assert.equal(button(view.element, 'Restore as a new saved copy').disabled, false);
});

test('an acknowledgement survives the first status-render exception without a false pending warning', async t => {
  const {view, choose, writes, busy} = setup(t);
  await choose(file('A'));
  const feedback = find(view.element, node => node['aria-live'] === 'polite');
  const original = feedback.replaceChildren.bind(feedback); let failed = false;
  feedback.replaceChildren = (...children) => {
    if (!failed && children.some(node => node.textContent.startsWith('Restored as a new saved copy.'))) {
      failed = true; throw new Error('First acknowledged view failed');
    }
    original(...children);
  };
  await button(view.element, 'Restore as a new saved copy').fire('click');
  assert.equal(writes.length, 1); assert.deepEqual(busy, [true, false]);
  assert.match(view.element.textContent, /acknowledged.*aaaa/);
  assert.doesNotMatch(feedback.textContent, /kept in Pending work/);
  assert.equal(button(view.element, 'Restored to My workspace').disabled, true);
});

test('a saved-list result cannot authorise a changed candidate', async t => {
  const checked = defer();
  const {view, choose, writes} = setup(t, {
    respond: async () => {throw new TypeError('Lost acknowledgement');},
    onCheckSaved: () => checked.promise,
  });
  await choose(file('A')); await button(view.element, 'Restore as a new saved copy').fire('click');
  const candidate = drafts.unsavedReportDrafts()[0].report;
  const checking = button(view.element, 'Check saved list before retrying').fire('click');
  candidate.review_status = 'stale after a new source snapshot';
  drafts.trackReportEdits(candidate, documentMarkdown(candidate));
  checked.resolve(true); await checking;
  assert.equal(button(view.element, 'Restore an additional copy').disabled, true);
  assert.equal(writes.length, 1); assert.doesNotMatch(view.element.textContent, /Saved list refreshed/);
});

test('a normal backup preview renders complete controls without a null placeholder or hidden view error', async t => {
  const {view, choose, writes} = setup(t);
  await choose(file('A'));
  const preview = find(view.element, node => node.tag === 'textarea' && node.readOnly);
  assert.equal(preview.value, 'Original evidence');
  assert.equal(walk(view.element).some(node => node.tag === '#text' && node.text === 'null'), false);
  assert.equal(walk(view.element).some(node => node.role === 'alert'), false);
  assert.equal(button(view.element, 'Restore as a new saved copy').disabled, false);
  assert.equal(writes.length, 0);
});
