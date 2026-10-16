import assert from 'node:assert/strict';
import test from 'node:test';
import {library} from '../src/sinter/web/library.js';
import {clearReportDrafts} from '../src/sinter/web/report-drafts.js';

class TestNode {
  constructor(tag = '#text', text = '') {
    this.tag = tag; this.children = []; this.attributes = {}; this._text = text;
    this.parentNode = null; this.value = '';
  }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) {
    for (const child of this.children) child.parentNode = null;
    this._text = String(value); this.children = [];
  }
  get firstElementChild() { return this.children.find(child => child.tag !== '#text') ?? null; }
  get nextElementSibling() {
    if (!this.parentNode) return null;
    const elements = this.parentNode.children.filter(child => child.tag !== '#text');
    return elements[elements.indexOf(this) + 1] ?? null;
  }
  remove() {
    if (!this.parentNode) return;
    const parent = this.parentNode, index = parent.children.indexOf(this);
    if (index !== -1) parent.children.splice(index, 1);
    this.parentNode = null;
  }
  append(...children) {
    for (const child of children) { child.remove(); child.parentNode = this; this.children.push(child); }
  }
  insertBefore(child, reference) {
    if (reference === null) { this.append(child); return child; }
    if (reference.parentNode !== this) throw new Error('Insertion reference is not a child.');
    if (child === reference) return child;
    child.remove(); child.parentNode = this;
    this.children.splice(this.children.indexOf(reference), 0, child); return child;
  }
  replaceChildren(...children) { this.textContent = ''; this.append(...children); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener() {}
}

function replaceGlobal(t, name, value) {
  const prior = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, {configurable: true, writable: true, value});
  t.after(() => {
    if (prior) Object.defineProperty(globalThis, name, prior);
    else delete globalThis[name];
  });
}

function fixture(t, browser) {
  replaceGlobal(t, 'Node', TestNode);
  replaceGlobal(t, 'document', {createElement: tag => new TestNode(tag),
    createTextNode: value => new TestNode('#text', String(value))});
  // Both editions use a browser UI. Its user agent and IndexedDB availability
  // cannot distinguish the installed app from the WebAssembly backend.
  replaceGlobal(t, 'navigator', {userAgent: 'Mozilla/5.0 Chrome/123.0'});
  replaceGlobal(t, 'indexedDB', {});
  const calls = [];
  const reports = [{id: 'fictional-saved-report', title: 'Saved garden handover', created_at: 1}];
  replaceGlobal(t, 'sinterBrowser', browser ? {request: async (path, options) => {
    calls.push({backend: 'browser', path, options}); return {reports};
  }} : undefined);
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({backend: 'installed', path, options}); return Response.json({reports});
  });
  clearReportDrafts(); t.after(clearReportDrafts);
  return calls;
}

test('browser workspace explains device storage, possible clearing and an independent export', async t => {
  const calls = fixture(t, true), page = await library();
  assert.match(page.textContent, /Saved reports stay in this browser on this device/);
  assert.match(page.textContent, /not encrypted/);
  assert.match(page.textContent, /clearing browser storage.*erase/i);
  assert.match(page.textContent, /Export saved workspace.*backup/);
  assert.doesNotMatch(page.textContent, /local Sinter folder/);
  assert.match(page.textContent, /Saved garden handover/);
  assert.deepEqual(calls.map(({backend, path}) => ({backend, path})),
    [{backend: 'browser', path: '/api/reports'}]);
});

test('installed workspace keeps the actual folder notice even with a browser UI', async t => {
  const calls = fixture(t, false), page = await library();
  assert.match(page.textContent, /Saved reports stay in your local Sinter folder, not a cloud account\. They are not encrypted\. Export important work and protect access to this computer\./);
  assert.doesNotMatch(page.textContent, /stay in this browser on this device|Export saved workspace/);
  assert.match(page.textContent, /Saved garden handover/);
  assert.deepEqual(calls.map(({backend, path}) => ({backend, path})),
    [{backend: 'installed', path: '/api/reports'}]);
});
