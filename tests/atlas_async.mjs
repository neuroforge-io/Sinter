import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {atlasPage} from '../src/sinter/web/atlas.js';

const packets = JSON.parse(fs.readFileSync(new URL('./fixtures/rkc_sinter_context_bridge_source_bound.v1.json', import.meta.url), 'utf8')).packets;
const questionLabel = 'What would you like to find out?';
const importLabel = 'Import an RKC atlas or context packet';
const consentLabel = 'Send selected source excerpts and my question to my configured model API for an unverified draft.';

class TestNode {
  constructor(tag = '#text', text = '') {
    this.tag = tag; this.children = []; this.listeners = {}; this.attributes = {};
    this._text = text; this.dataset = {}; this.id = ''; this.value = ''; this.type = '';
    this.disabled = false; this.hidden = false; this.checked = false; this.required = false;
    this.min = ''; this.max = ''; this.htmlFor = ''; this.className = ''; this.textContent = text;
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children.map(child => child instanceof TestNode ? child : new TestNode('#text', String(child)))); }
  replaceChildren(...children) { this._text = ''; this.children = []; this.append(...children); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  async dispatch(type) { for (const listener of this.listeners[type] || []) await listener({type, target: this}); }
  reportValidity() {
    if (this.disabled) return true;
    if (this.required && !String(this.value).trim()) return false;
    if (this.type === 'number') return Number.isFinite(Number(this.value)) &&
      (!this.min || Number(this.value) >= Number(this.min)) && (!this.max || Number(this.value) <= Number(this.max));
    return true;
  }
}
function walk(root) { return [root, ...root.children.flatMap(walk)]; }
function field(root, label) {
  const match = walk(root).find(node => node.tag === 'label' && node.textContent === label);
  assert.ok(match, `Field ${label} is present`);
  return walk(root).find(node => node.id === match.htmlFor);
}
function action(root, label) {
  const match = walk(root).find(node => node.tag === 'button' && node.textContent === label);
  assert.ok(match, `Action ${label} is present`); return match;
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
const inspectInfo = packet => ({item_count: packet.items.length, snapshot_id: packet.snapshot_id,
  producer_integrity: 'fictional test', warnings: []});
const settle = () => new Promise(resolve => setImmediate(resolve));
function fixture(t, {seed = {}, inspect = async packet => Response.json(inspectInfo(packet))} = {}) {
  const priorDocument = globalThis.document, priorNode = globalThis.Node;
  const ids = new Map(['announcements'].map(id => [id, new TestNode('div')]));
  globalThis.Node = TestNode;
  globalThis.document = {documentElement: new TestNode('html'), createElement: tag => new TestNode(tag),
    createTextNode: value => new TestNode('#text', String(value)), getElementById: id => ids.get(id)};
  t.after(() => { globalThis.document = priorDocument; globalThis.Node = priorNode; });
  const calls = [], remembered = [], busy = [];
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    const data = options.body ? JSON.parse(options.body) : null; calls.push({path, data});
    if (path === '/api/session') return Response.json({token: 'fictional-local-session'});
    if (path === '/api/atlas/inspect') return inspect(data.document);
    if (path === '/api/atlas/context') return Response.json({review_status: 'source_review_required',
      markdown: `Fictional packet for ${data.document.snapshot_id}`});
    if (path === '/api/atlas/retrieve') throw new Error('Fictional local read failure');
    throw new Error(`Forbidden model, credential or other request: ${path}`);
  });
  function newPage(seed = {}) {
    const root = atlasPage({seed: {question: 'Lantern lending period', ...seed},
      remember: (kind, value) => { assert.equal(kind, 'atlas'); remembered.push(structuredClone(value)); },
      setBusy: value => busy.push(value)});
    const consent = walk(root).find(node => node.tag === 'input' && node.type === 'checkbox' &&
      walk(root).some(parent => parent.tag === 'label' && parent.children.includes(node) && parent.textContent.includes(consentLabel)));
    assert.ok(consent);
    const result = walk(root).find(node => node.attributes['aria-label'] === 'Knowledge results');
    return {root, calls, remembered, busy, consent, result, newPage,
      async upload(packet) {
        const input = field(root, importLabel);
        input.files = [{size: 1024, text: async () => JSON.stringify(packet)}];
        await input.dispatch('change');
      },
      async find() { await action(root, 'Find supporting material').dispatch('click'); },
    };
  }
  return newPage(seed);
}

for (const outcome of ['success', 'failure']) {
  test(`a delayed remembered packet ${outcome} cannot undo an accepted newer snapshot or its results`, async t => {
    const old = deferred(), started = deferred();
    const f = fixture(t, {seed: {document: packets.before}, inspect: packet => {
      if (packet.snapshot_id === packets.before.snapshot_id) { started.resolve(); return old.promise; }
      return Response.json(inspectInfo(packet));
    }});
    await started.promise;
    await f.upload(packets.after);
    assert.equal(f.remembered.at(-1).document.snapshot_id, packets.after.snapshot_id);
    assert.equal(f.consent.checked, false);
    await f.find();
    const visible = f.root.textContent, result = f.result.textContent;
    f.consent.checked = true;
    if (outcome === 'success') old.resolve(Response.json(inspectInfo(packets.before)));
    else old.resolve(Response.json({error: 'Fictional stale validation failure'}, {status: 400}));
    await settle();
    assert.equal(f.root.textContent, visible);
    assert.equal(f.result.textContent, result);
    assert.equal(f.consent.checked, true);
    assert.equal(f.remembered.at(-1).document.snapshot_id, packets.after.snapshot_id);
    await f.find();
    assert.equal(f.calls.filter(call => call.path === '/api/atlas/context').at(-1).data.document.snapshot_id, packets.after.snapshot_id);
    assert.deepEqual(f.busy, [true, false, true, false, true, false]);
    assert.equal(action(f.root, 'Find supporting material').disabled, false);
  });

  test(`a delayed older import ${outcome} cannot overwrite the latest import`, async t => {
    const old = deferred(), started = deferred();
    const f = fixture(t, {inspect: packet => {
      if (packet.snapshot_id === packets.before.snapshot_id) { started.resolve(); return old.promise; }
      return Response.json(inspectInfo(packet));
    }});
    const earlier = f.upload(packets.before); await started.promise;
    await f.upload(packets.after);
    f.consent.checked = true;
    if (outcome === 'success') old.resolve(Response.json(inspectInfo(packets.before)));
    else old.reject(new Error('Fictional stale import failure'));
    await earlier;
    assert.equal(f.remembered.at(-1).document.snapshot_id, packets.after.snapshot_id);
    assert.equal(f.consent.checked, true);
    assert.doesNotMatch(f.root.textContent, /stale import failure/);
    await f.find();
    assert.equal(f.calls.at(-1).data.document.snapshot_id, packets.after.snapshot_id);
  });
}

test('an unsuperseded remembered packet is accepted', async t => {
  const initial = deferred(), started = deferred();
  const f = fixture(t, {seed: {document: packets.before}, inspect: () => { started.resolve(); return initial.promise; }});
  await started.promise;
  initial.resolve(Response.json(inspectInfo(packets.before))); await settle();
  assert.match(f.root.textContent, new RegExp(packets.before.snapshot_id));
  assert.equal(f.remembered.at(-1).document.snapshot_id, packets.before.snapshot_id);
  await f.find();
  assert.equal(f.calls.at(-1).data.document.snapshot_id, packets.before.snapshot_id);
});

test('an unsuperseded remembered packet failure is reported', async t => {
  const f = fixture(t, {seed: {document: packets.before}, inspect: () => Response.json({error: 'Fictional current validation failure'}, {status: 400})});
  await settle();
  assert.match(f.root.textContent, /Fictional current validation failure/);
  assert.equal(f.remembered.length, 0);
});

for (const outcome of ['success', 'failure']) {
  test(`a late same-snapshot reinspection ${outcome} preserves completed results and the current consent`, async t => {
    const initial = deferred(), started = deferred();
    const f = fixture(t, {seed: {document: packets.before}, inspect: () => {
      started.resolve(); return initial.promise;
    }});
    await started.promise;
    await f.find();
    const completed = f.result.textContent;
    assert.match(completed, /Source packet only/);
    assert.match(completed, /Download context JSON/);
    f.consent.checked = true;
    if (outcome === 'success') initial.resolve(Response.json(inspectInfo(packets.before)));
    else initial.resolve(Response.json({error: 'Fictional current reinspection failure'}, {status: 400}));
    await settle();
    assert.equal(f.result.textContent, completed);
    assert.equal(f.consent.checked, true);
    assert.equal(action(f.root, 'Download context JSON').disabled, false);
    if (outcome === 'failure') assert.match(f.root.textContent, /Fictional current reinspection failure/);
    else assert.doesNotMatch(f.root.textContent, /Fictional current reinspection failure/);
    assert.deepEqual(f.busy, [true, false]);
    await f.find();
    assert.equal(f.calls.filter(call => call.path === '/api/atlas/context').at(-1).data.document.snapshot_id, packets.before.snapshot_id);
  });
}

test('an explicit same-snapshot import still replaces the selection and resets consent and results', async t => {
  const f = fixture(t, {seed: {document: packets.before}});
  await settle(); await f.find(); f.consent.checked = true;
  assert.match(f.result.textContent, /Source packet only/);
  await f.upload(packets.before);
  assert.equal(f.result.textContent, '');
  assert.equal(f.consent.checked, false);
  assert.equal(f.remembered.at(-1).document.snapshot_id, packets.before.snapshot_id);
  await f.find();
  assert.equal(f.calls.filter(call => call.path === '/api/atlas/context').at(-1).data.document.snapshot_id, packets.before.snapshot_id);
});

test('failed replacement preserves a previously accepted document and resets consent', async t => {
  const f = fixture(t, {inspect: packet => packet.snapshot_id === packets.after.snapshot_id
    ? Response.json({error: 'Fictional rejected replacement'}, {status: 400}) : Response.json(inspectInfo(packet))});
  await f.upload(packets.before); f.consent.checked = true;
  await f.upload(packets.after);
  assert.equal(f.consent.checked, false);
  assert.match(f.result.textContent, /Fictional rejected replacement/);
  assert.equal(f.remembered.at(-1).document.snapshot_id, packets.before.snapshot_id);
  await f.find();
  assert.equal(f.calls.at(-1).data.document.snapshot_id, packets.before.snapshot_id);
});

test('question edits, invalid JSON, missing files and failed local reads still reset consent', async t => {
  const f = fixture(t); await f.upload(packets.before);
  f.consent.checked = true;
  const question = field(f.root, questionLabel); question.value = 'Fictional opening hours'; await question.dispatch('input');
  assert.equal(f.consent.checked, false);
  for (const file of [{size: 2, text: async () => '{'}, undefined]) {
    f.consent.checked = true; field(f.root, importLabel).files = file ? [file] : [];
    await field(f.root, importLabel).dispatch('change');
    assert.equal(f.consent.checked, false);
    assert.equal(f.remembered.at(-1).document.snapshot_id, packets.before.snapshot_id);
  }
  f.consent.checked = true; await action(f.root, 'Read context from local RKC').dispatch('click');
  assert.equal(f.consent.checked, false);
  assert.equal(f.remembered.at(-1).document.snapshot_id, packets.before.snapshot_id);
  assert.ok(f.calls.every(call => ['/api/session', '/api/atlas/inspect', '/api/atlas/context', '/api/atlas/retrieve'].includes(call.path)));
});

for (const outcome of ['success', 'failure']) {
  test(`a disposed page's delayed remembered validation ${outcome} cannot replace shared current state`, async t => {
    const old = deferred(), started = deferred(); let inspectedOld = false;
    const f = fixture(t, {seed: {document: packets.before}, inspect: packet => {
      if (packet.snapshot_id === packets.before.snapshot_id && !inspectedOld) {
        inspectedOld = true; started.resolve(); return old.promise;
      }
      return Response.json(inspectInfo(packet));
    }});
    await started.promise;
    f.root.dispose?.();
    const current = f.newPage({document: packets.before}); await settle();
    await current.upload(packets.after); await current.find(); current.consent.checked = true;
    const visible = current.root.textContent, priorRemembered = current.remembered.length;
    if (outcome === 'success') old.resolve(Response.json(inspectInfo(packets.before)));
    else old.resolve(Response.json({error: 'Fictional disposed validation failure'}, {status: 400}));
    await settle();
    assert.equal(current.root.textContent, visible);
    assert.equal(current.remembered.length, priorRemembered);
    assert.equal(current.remembered.at(-1).document.snapshot_id, packets.after.snapshot_id);
    assert.equal(current.consent.checked, true);
    assert.doesNotMatch(f.root.textContent, /disposed validation failure/);
    await current.find(); assert.equal(current.calls.at(-1).data.document.snapshot_id, packets.after.snapshot_id);
    current.root.dispose?.();
    const reopened = current.newPage(current.remembered.at(-1)); await settle(); await reopened.find();
    assert.equal(reopened.calls.at(-1).data.document.snapshot_id, packets.after.snapshot_id);
  });
}

test('a disposed page cannot start inspection after delayed file reading or remember later input', async t => {
  const file = deferred(), started = deferred();
  const f = fixture(t);
  const input = field(f.root, importLabel);
  input.files = [{size: 1024, text: () => { started.resolve(); return file.promise; }}];
  const pending = input.dispatch('change'); await started.promise; f.root.dispose?.();
  const current = f.newPage(); await current.upload(packets.after);
  const priorRemembered = current.remembered.length;
  file.resolve(JSON.stringify(packets.before)); await pending;
  assert.equal(f.calls.filter(call => call.path === '/api/atlas/inspect' && call.data.document.snapshot_id === packets.before.snapshot_id).length, 0);
  assert.equal(current.remembered.length, priorRemembered);
  field(f.root, questionLabel).value = 'Fictional old-page edit'; await field(f.root, questionLabel).dispatch('input');
  assert.equal(current.remembered.length, priorRemembered);
  assert.equal(current.remembered.at(-1).document.snapshot_id, packets.after.snapshot_id);
  const count = f.calls.length; await f.find(); assert.equal(f.calls.length, count);
});
