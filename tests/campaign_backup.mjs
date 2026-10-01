import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignBackupText, campaignBackupControls, resetCampaignBackupControls} from '../src/sinter/web/campaign-backup.js';

function fixture() {
  return {schema: 'sinter-campaign/v1', title: 'Fictional 🌱 e\u0301 working copy',
    organisation: '', objective: 'Not agreed.\r\n<keep literally> "quoted" \\ text',
    opportunities: [{name: 'Unconfirmed route', funding_currency: 'unconfirmed'}],
    sources: [{id: '1234567890abcdef1234567890abcdef', title: 'Original', notes: 'Exact source'}],
    assets: [{id: 'abcdef1234567890abcdef1234567890', references: [{source_id: '1234567890abcdef1234567890abcdef'}]}],
    actions: [{task: 'Ask; do not assume', owner: '', due: '', status: 'open'}],
    communications: [{subject: 'New unsaved record', date: '', status: 'draft', content: 'Not sent.'}],
    answers: [{text: '', limit: 0}], budget: [{unit_cost: null}], requirements: []};
}

function environment(t, writeText) {
  const saved = {document: globalThis.document, Node: globalThis.Node,
    navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator')};
  class Element {
    constructor(tag) {
      this.tag = tag; this.children = []; this.handlers = {}; this.attributes = {};
      this.hidden = false; this.disabled = false; this.value = ''; this.readOnly = false;
      this.rows = 0; this.spellcheck = true; this.className = ''; this.textContent = '';
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(key, value) { this.attributes[key] = value; }
    addEventListener(key, action) { this.handlers[key] = action; }
    focus() { env.focused = this; }
    select() { this.selected = this.value; }
  }
  const env = {focused: null};
  globalThis.Node = Element;
  globalThis.document = {createElement: tag => new Element(tag),
    createTextNode: text => Object.assign(new Element('#text'), {textContent: text})};
  Object.defineProperty(globalThis, 'navigator', {configurable: true,
    value: writeText ? {clipboard: {writeText}} : {}});
  t.after(() => {
    if (saved.document === undefined) delete globalThis.document;
    else globalThis.document = saved.document;
    if (saved.Node === undefined) delete globalThis.Node;
    else globalThis.Node = saved.Node;
    if (saved.navigator) Object.defineProperty(globalThis, 'navigator', saved.navigator);
    else delete globalThis.navigator;
  });
  env.nodes = root => [root, ...root.children.flatMap(child => env.nodes(child))];
  env.text = root => root.textContent + root.children.map(env.text).join('');
  env.control = callback => {
    const root = campaignBackupControls(callback), nodes = env.nodes(root);
    return {root, copy: nodes.find(node => node.tag === 'button' && env.text(node) === 'Copy backup text'),
      refresh: nodes.find(node => node.tag === 'button' && env.text(node) === 'Refresh backup text'),
      select: nodes.find(node => node.tag === 'button' && env.text(node) === 'Select backup text'),
      textarea: nodes.find(node => node.tag === 'textarea'),
      manual: nodes.find(node => node.children.some(child => child.tag === 'button' && env.text(child) === 'Select backup text'))};
  };
  return env;
}

test('JSON preserves all unsaved fields, exact Unicode, unknown values and record identities without mutation', () => {
  const document = fixture(), original = structuredClone(document);
  const text = campaignBackupText(document);
  assert.deepEqual(JSON.parse(text), original);
  assert.deepEqual(document, original);
  assert.equal(text, JSON.stringify(original, null, 2));
});

test('recovery does not truncate or apply one-megabyte import or text-save limits', () => {
  const document = fixture();
  document.communications[0].content = 'Fictional 🐝 <unknown> e\u0301\n'.repeat(60000);
  const text = campaignBackupText(document);
  assert.ok(Buffer.byteLength(text, 'utf8') > 1_000_000);
  assert.deepEqual(JSON.parse(text), document);
});

test('nothing copies on construction; explicit copy captures the latest working copy and makes no file-saved claim', async t => {
  const writes = [], env = environment(t, text => { writes.push(text); return Promise.resolve(); });
  let document = fixture(), reads = 0;
  const controls = env.control(() => { reads++; return document; });
  assert.equal(reads, 0); assert.deepEqual(writes, []);
  document = {...document, title: 'Latest unsaved inputs'};
  await controls.copy.handlers.click();
  assert.equal(reads, 1); assert.deepEqual(JSON.parse(writes[0]), document);
  assert.equal(controls.textarea.value, writes[0]); assert.equal(controls.textarea.readOnly, true);
  assert.equal(controls.textarea.attributes.maxlength, undefined);
  assert.match(env.text(controls.root), /does not save the campaign or create a file/);
  assert.equal(controls.copy.disabled, false);
});

for (const mode of ['denied', 'missing']) {
  test(`${mode} clipboard retains complete selectable recovery without exposing the exception`, async t => {
    const env = environment(t, mode === 'denied' ? () => Promise.reject(new Error('PRIVATE exception')) : null);
    const document = fixture(), controls = env.control(() => document);
    await controls.copy.handlers.click();
    assert.deepEqual(JSON.parse(controls.textarea.value), document);
    assert.equal(env.focused, controls.textarea);
    assert.equal(controls.textarea.selected, controls.textarea.value);
    assert.match(env.text(controls.root), /Clipboard unavailable/);
    assert.doesNotMatch(env.text(controls.root), /PRIVATE exception/);
    assert.equal(controls.copy.disabled, false);
  });
}

test('stalled clipboard permits fresh manual recovery, suppresses stale completion and never replays concurrent writes', async t => {
  let resolve;
  const writes = [], env = environment(t, text => {
    writes.push(text); return new Promise(done => { resolve = done; });
  });
  const document = fixture(), controls = env.control(() => document);
  const pending = controls.copy.handlers.click();
  assert.equal(controls.copy.disabled, true);
  await controls.copy.handlers.click(); assert.equal(writes.length, 1);
  controls.select.handlers.click(); assert.equal(controls.textarea.selected, writes[0]);
  document.communications.push({subject: 'Second unsaved record', content: 'Not sent. 🐝'});
  assert.equal(JSON.parse(controls.textarea.value).communications.length, 1);
  controls.refresh.handlers.click();
  assert.equal(JSON.parse(controls.textarea.value).communications.length, 2);
  assert.equal(writes.length, 1); assert.equal(controls.copy.disabled, true);
  const refreshedStatus = env.text(controls.root);
  assert.match(refreshedStatus, /Clipboard may contain an earlier snapshot/);
  resolve(); await pending;
  assert.equal(env.text(controls.root), refreshedStatus);
  assert.equal(controls.copy.disabled, false);
  const next = controls.copy.handlers.click();
  assert.equal(JSON.parse(writes[1]).communications.length, 2);
  resolve(); await next;
});

test('refresh is an explicit clipboard-free snapshot and stale denial cannot replace it or steal focus', async t => {
  let reject;
  const writes = [], env = environment(t, text => {
    writes.push(text); return new Promise((resolve, fail) => { reject = fail; });
  });
  const document = fixture(), controls = env.control(() => document);
  controls.refresh.handlers.click(); assert.deepEqual(writes, []);
  assert.deepEqual(JSON.parse(controls.textarea.value), document);
  const pending = controls.copy.handlers.click();
  document.title = 'Newer current input'; controls.refresh.handlers.click();
  const message = env.text(controls.root);
  reject(new Error('Denied old request')); await pending;
  assert.equal(env.text(controls.root), message); assert.equal(env.focused, null);
  assert.equal(JSON.parse(controls.textarea.value).title, document.title);
  assert.equal(writes.length, 1);
});

test('unserializable inputs fail honestly without changing the working copy or trying clipboard', async t => {
  const writes = [], env = environment(t, text => { writes.push(text); });
  const document = fixture(); document.cycle = document;
  const controls = env.control(() => document);
  await controls.copy.handlers.click();
  assert.equal(document.cycle, document); assert.deepEqual(writes, []);
  assert.match(env.text(controls.root), /Could not prepare backup text/);
  assert.equal(controls.copy.disabled, false);
  assert.throws(() => campaignBackupText(undefined), /working copy/);
});

for (const completion of ['resolve', 'reject']) {
  test(`failed refresh supersedes an older stalled clipboard ${completion} without losing focus`, async t => {
    let resolve, reject, unavailable = false;
    const env = environment(t, () => new Promise((done, fail) => { resolve = done; reject = fail; }));
    const document = fixture();
    const controls = env.control(() => {
      if (unavailable) throw new Error('PRIVATE pending-source details');
      return document;
    });
    const pending = controls.copy.handlers.click();
    unavailable = true; controls.refresh.handlers.click();
    const failedMessage = env.text(controls.root);
    const focused = env.focused;
    assert.match(failedMessage, /Earlier backup text, if shown, has not been refreshed/);
    assert.doesNotMatch(failedMessage, /PRIVATE/);
    assert.deepEqual(JSON.parse(controls.textarea.value), document);
    if (completion === 'resolve') resolve(); else reject(new Error('PRIVATE old denial'));
    await pending;
    assert.equal(env.text(controls.root), failedMessage);
    assert.equal(env.focused, focused);
    assert.equal(controls.copy.disabled, false);
  });
}


test('replacing a campaign clears captured JSON and feedback without reading or copying the new work', t => {
  const writes = [], env = environment(t, text => { writes.push(text); });
  let current = fixture(), reads = 0;
  const original = structuredClone(current);
  const controls = env.control(() => { reads++; return current; });
  resetCampaignBackupControls(controls.root);
  assert.equal(reads, 0); assert.equal(env.text(controls.root).includes('Earlier backup'), false);
  controls.refresh.handlers.click();
  assert.equal(reads, 1); assert.deepEqual(JSON.parse(controls.textarea.value), original);
  current = {...fixture(), title: 'A different unsaved campaign'};
  resetCampaignBackupControls(controls.root);
  assert.equal(reads, 1); assert.deepEqual(writes, []);
  assert.equal(controls.textarea.value, ''); assert.equal(controls.manual.hidden, true);
  assert.match(env.text(controls.root), /Earlier backup text cleared/);
  assert.doesNotMatch(env.text(controls.root), /refreshed from your current inputs/);
  assert.match(env.text(controls.root), /Clipboard may still contain an earlier snapshot/);
  controls.refresh.handlers.click();
  assert.deepEqual(JSON.parse(controls.textarea.value), current);
  assert.equal(controls.manual.hidden, false); assert.equal(reads, 2);
  assert.deepEqual(original, fixture()); assert.deepEqual(writes, []);
});

for (const completion of ['resolve', 'reject']) {
  test(`replacement supersedes a stalled clipboard ${completion} without replay or focus theft`, async t => {
    let resolve, reject, reads = 0;
    const writes = [], env = environment(t, text => {
      writes.push(text); return new Promise((done, fail) => { resolve = done; reject = fail; });
    });
    let current = fixture();
    const original = structuredClone(current);
    const controls = env.control(() => { reads++; return current; });
    const pending = controls.copy.handlers.click();
    current = {...fixture(), title: 'New working copy 🐝'};
    controls.refresh.focus();
    resetCampaignBackupControls(controls.root);
    const resetMessage = env.text(controls.root), focused = env.focused;
    assert.equal(controls.textarea.value, ''); assert.equal(controls.manual.hidden, true);
    assert.equal(controls.copy.disabled, true); assert.equal(reads, 1);
    assert.deepEqual(JSON.parse(writes[0]), original);
    if (completion === 'resolve') resolve(); else reject(new Error('Old denied capture'));
    await pending;
    assert.equal(env.text(controls.root), resetMessage);
    assert.equal(env.focused, focused); assert.equal(controls.copy.disabled, false);
    assert.equal(writes.length, 1); assert.equal(reads, 1);
    controls.refresh.handlers.click();
    assert.deepEqual(JSON.parse(controls.textarea.value), current);
    assert.equal(writes.length, 1); assert.equal(reads, 2);
  });
}
