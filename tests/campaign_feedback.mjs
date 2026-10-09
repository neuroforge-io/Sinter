import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignFeedback, campaignFeedbackPresentation} from '../src/sinter/web/campaign-feedback.js';

class Element {
  constructor(tag = '#text', text = '') {
    this.tag = tag; this._text = text; this.children = []; this.parentElement = null;
    this.attributes = {}; this.listeners = {}; this.dataset = {}; this.className = '';
    this.hidden = false; this.open = false; this.isRoot = false;
  }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  get isConnected() { return this.isRoot || Boolean(this.parentElement?.isConnected); }
  append(...children) {
    for (const child of children) {
      const node = child instanceof Element ? child : new Element('#text', String(child));
      this.children.push(node); node.parentElement = this;
    }
  }
  replaceChildren(...children) { this._text = ''; this.children = []; this.append(...children); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(type, listener, options = {}) {
    (this.listeners[type] ||= []).push({listener, once: options.once});
  }
  dispatch(type) {
    for (const {listener} of this.listeners[type] || []) listener({type, target: this});
    this.listeners[type] = (this.listeners[type] || []).filter(entry => !entry.once);
  }
  querySelector(selector) {
    const matches = node => selector.startsWith('.')
      && selector.slice(1).split('.').every(value => node.className.split(' ').includes(value));
    const visit = node => {
      for (const child of node.children) { if (matches(child)) return child; const found = visit(child); if (found) return found; }
      return null;
    };
    return visit(this);
  }
  focus() {
    for (let node = this; node; node = node.parentElement) if (node.hidden) return;
    document.activeElement = this;
  }
  showModal() { if (document.dialogUnavailable) throw new Error('No dialog API'); this.open = true; }
  close() { this.open = false; this.dispatch('close'); }
  remove() {
    if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this);
    this.parentElement = null;
  }
}

function fixture(t, {resize = true, dialogUnavailable = false} = {}) {
  const keys = ['document', 'Node', 'window', 'MutationObserver', 'ResizeObserver'];
  const before = Object.fromEntries(keys.map(key => [key, globalThis[key]]));
  const observers = [], listeners = new Map();
  class Observer {
    constructor(callback) { this.callback = callback; this.closed = false; observers.push(this); }
    observe() {}
    disconnect() { this.closed = true; }
  }
  globalThis.Node = Element;
  globalThis.MutationObserver = Observer;
  globalThis.ResizeObserver = resize ? Observer : undefined;
  globalThis.window = {addEventListener: (key, callback) => listeners.set(key, callback),
    removeEventListener: key => listeners.delete(key)};
  const body = new Element('body'); body.isRoot = true;
  globalThis.document = {body, dialogUnavailable, activeElement: null,
    createElement: tag => new Element(tag), createTextNode: text => new Element('#text', String(text))};
  t.after(() => {
    for (const key of keys) {
      if (before[key] === undefined) delete globalThis[key]; else globalThis[key] = before[key];
    }
  });
  const fallback = new Element('button'); body.append(fallback);
  const component = campaignFeedback(() => fallback); body.append(component.panel);
  const flush = () => observers.filter(observer => !observer.closed).forEach(observer => observer.callback());
  const setMessage = (text, kind = '') => {
    const message = new Element('div', text); message.className = `notice ${kind}`;
    component.feedback.replaceChildren(message); flush();
  };
  const expand = component.panel.querySelector('.campaign-message-expand');
  return {component, fallback, setMessage, expand, flush, observers, listeners, body};
}

test('empty feedback has no invented message or severity', () => {
  for (const text of ['', ' \n\t', null]) {
    assert.deepEqual(campaignFeedbackPresentation(text, 'error'), {kind: 'empty', summary: ''});
  }
});

test('routine acknowledgements do not create another saved-status assertion', () => {
  for (const text of ['Campaign saved.', 'Campaign imported locally. Save to keep this copy.', 'New local information']) {
    assert.deepEqual(campaignFeedbackPresentation(text, 'success'), {kind: 'routine', summary: ''});
  }
});

test('known errors and warnings remain visible regardless of message length', () => {
  assert.equal(campaignFeedbackPresentation('No', 'error').kind, 'error');
  assert.equal(campaignFeedbackPresentation('Check', 'warning').kind, 'warning');
  assert.match(campaignFeedbackPresentation('No', 'error').summary, /Needs attention/);
});

test('uncertain saves cannot be collapsed into routine acknowledgement', () => {
  const text = 'Connection interrupted. The save may have finished, but Sinter did not receive confirmation.';
  const state = campaignFeedbackPresentation(text, 'success');
  assert.equal(state.kind, 'warning');
  assert.match(state.summary, /Outcome unconfirmed/);
  assert.doesNotMatch(state.summary, /failed|saved|retry/i);
});

test('partial-work messages stay visible without claiming a complete result', () => {
  for (const text of ['INCOMPLETE MODEL DRAFT', 'Keep the partial result for review.']) {
    const state = campaignFeedbackPresentation(text);
    assert.equal(state.kind, 'warning');
    assert.match(state.summary, /recovery details/);
    assert.doesNotMatch(state.summary, /complete|ready|successful/i);
  }
});

test('short routine text remains exact, announced and reachable explicitly', t => {
  const f = fixture(t);
  f.setMessage('Campaign imported locally. Save campaign to keep this copy.', 'success');
  assert.equal(f.component.feedback.hidden, true);
  assert.equal(f.expand.hidden, false);
  assert.equal(f.component.panel.dataset.kind, 'routine');
  assert.equal(f.component.panel.querySelector('.campaign-message-announcement').textContent,
    f.component.feedback.textContent);
  f.expand.dispatch('click');
  const message = f.body.querySelector('.campaign-message-text');
  assert.equal(message.textContent, f.component.feedback.textContent);
  assert.equal(document.activeElement, message);
  f.body.querySelector('.campaign-message-dialog').close();
  assert.equal(document.activeElement, f.expand);
  f.component.dispose();
});

test('Unicode and literal markup are retained in an immutable full-message snapshot', t => {
  const f = fixture(t);
  const original = 'Fictional café 中文 🧭 e\u0301\n<img onerror="send()">\n' + 'Exact evidence '.repeat(200);
  f.setMessage(original, 'error');
  assert.equal(f.component.feedback.hidden, false);
  f.expand.dispatch('click');
  const message = f.body.querySelector('.campaign-message-text');
  assert.equal(message.textContent, original);
  assert.equal(message.children.length, 1);
  assert.equal(message.children[0].tag, '#text');
  f.setMessage('New short acknowledgement', 'success');
  assert.equal(message.textContent, original);
  f.body.querySelector('.campaign-message-dialog').close();
  assert.equal(document.activeElement, f.expand);
  f.component.dispose();
});

test('recovery details cannot disappear merely because they fit without scrolling', t => {
  const f = fixture(t);
  f.setMessage('The save may have finished. Check the saved campaign before choosing Save again.', 'error');
  assert.equal(f.component.feedback.hidden, false);
  assert.equal(f.expand.hidden, false);
  const summary = f.component.panel.querySelector('.campaign-message-summary');
  assert.equal(summary.hidden, false);
  assert.match(summary.textContent, /Outcome unconfirmed/);
  assert.equal(f.component.panel.dataset.kind, 'error');
  f.component.dispose();
});

test('missing modal API leaves the original routine message visible and keyboard reachable', t => {
  const f = fixture(t, {dialogUnavailable: true});
  f.setMessage('Exact routine message with no dialog support.', 'success');
  f.expand.dispatch('click');
  assert.equal(f.body.querySelector('.campaign-message-dialog'), null);
  assert.equal(f.component.feedback.hidden, false);
  assert.equal(document.activeElement, f.component.feedback);
  assert.equal(f.component.panel.dataset.inlineExpanded, 'true');
  f.setMessage('A different message', 'success');
  assert.equal(f.component.feedback.hidden, true);
  f.component.dispose();
});

test('cleared messages return focus to the caller without restoring old feedback', t => {
  const f = fixture(t, {resize: false});
  f.setMessage('Read this local message', 'success');
  f.expand.dispatch('click');
  const dialog = f.body.querySelector('.campaign-message-dialog');
  f.setMessage('');
  assert.equal(f.component.panel.hidden, true);
  assert.equal(dialog.querySelector('.campaign-message-text').textContent, 'Read this local message');
  dialog.close();
  assert.equal(document.activeElement, f.fallback);
  assert.equal(f.component.feedback.textContent, '');
  f.component.dispose();
});

test('disposal closes the viewer, disconnects observers and performs no caller action', t => {
  const f = fixture(t);
  let callerActions = 0;
  f.fallback.addEventListener('click', () => callerActions++);
  f.setMessage('Retain the exact original message.', 'error');
  f.expand.dispatch('click');
  f.component.dispose();
  assert.equal(f.body.querySelector('.campaign-message-dialog'), null);
  assert.equal(f.observers.every(observer => observer.closed), true);
  assert.equal(f.listeners.size, 0);
  assert.equal(callerActions, 0);
  assert.equal(f.component.feedback.textContent, 'Retain the exact original message.');
});
