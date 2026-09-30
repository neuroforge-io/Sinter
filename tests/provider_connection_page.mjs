import assert from 'node:assert/strict';
import test from 'node:test';
import {settingsPage} from '../src/sinter/web/settings.js';

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
function fixture(t, initial = {}) {
  const priorDocument = globalThis.document, priorNode = globalThis.Node;
  const ids = new Map(['theme-toggle', 'announcements'].map(id => [id, new TestNode('div')]));
  globalThis.Node = TestNode;
  globalThis.document = {documentElement: new TestNode('html'), createElement: tag => new TestNode(tag),
    createTextNode: value => new TestNode('#text', String(value)), getElementById: id => ids.get(id)};
  t.after(() => { globalThis.document = priorDocument; globalThis.Node = priorNode; });
  let settings = {api_url: 'https://neuroforge.io/v1', provider: 'openai-compatible', model: 'auto', max_tokens: 64,
    organisation: '', theme: 'dark', text_size: 'normal', density: 'comfortable', reduce_motion: false,
    rkc_port: 8787, rkc_executable: '', ...initial};
  let account = {connected: false, pending: null, profiles: []};
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    const data = options.body ? JSON.parse(options.body) : null; calls.push({path, data});
    if (path === '/api/session') return Response.json({token: 'test-local-token'});
    if (path === '/api/settings') { if (data) settings = {...data.settings}; return Response.json({settings, has_session_key: !!data?.api_key}); }
    if (path === '/api/account/connect') return Response.json({...account, pending: {status: 'awaiting'}, auth_url: 'https://auth.openai.com/test'});
    if (path === '/api/account') return Response.json(account);
    if (path === '/api/account/cancel') { account = {...account, pending: null}; return Response.json(account); }
    if (path === '/api/account/activate') {
      const selected = account.profiles.find(item => item.id === data.profile_id);
      account = {...account, active_profile_id: selected.id, connected: selected.connected, plan_usage: selected.plan_usage};
      return Response.json(account);
    }
    if (path === '/api/models') return Response.json({models: [{id: 'exact-model'}]});
    if (path === '/api/health') return Response.json({ok: true, message: 'Catalogue found.'});
    throw new Error(`Unexpected request ${path}`);
  });
  return {calls, get settings() { return settings; }, setAccount(value) { account = value; }};
}

test('changing provider clears a draft key and cannot pass an old connection check', async t => {
  const f = fixture(t), page = await settingsPage();
  const key = field(page, 'API key for this session'); key.value = 'draft-test-key'; await key.dispatch('input');
  assert.equal(action(page, 'Check saved connection').disabled, true);
  const route = field(page, 'Assistant connection'); route.value = 'anthropic'; await route.dispatch('change');
  assert.equal(key.value, '');
  assert.equal(field(page, 'API base address').value, 'https://api.anthropic.com/v1');
  assert.equal(field(page, 'Model identifier').value, '');
  await action(page, 'Save my preferences').dispatch('click');
  assert.equal(f.calls.filter(call => call.path === '/api/settings' && call.data).length, 0);
});

test('native saved caps survive unrelated preference saves and explain the execution limit', async t => {
  const f = fixture(t, {model: 'erais-native-qwen3', max_tokens: 512});
  const page = await settingsPage();
  const cap = field(page, 'Maximum answer length');
  assert.equal(Number(cap.value), 512);
  assert.equal(cap.reportValidity(), true);
  assert.match(page.textContent, /Native ERAIS applies at most 128 output tokens/);
  const theme = field(page, 'Colour theme'); theme.value = 'light';
  await action(page, 'Save my preferences').dispatch('click');
  assert.equal(f.settings.max_tokens, 512);
  assert.equal(f.settings.model, 'erais-native-qwen3');
  assert.equal(f.settings.theme, 'light');
  assert.equal(f.calls.some(call => call.path === '/api/chat'), false);
});

test('catalogue lookup uses the approved candidate and never silently saves it', async t => {
  const f = fixture(t), page = await settingsPage();
  const route = field(page, 'Assistant connection'); route.value = 'openai'; await route.dispatch('change');
  await action(page, 'Load available models').dispatch('click');
  assert.equal(f.calls.some(call => call.path === '/api/models'), false);
  const approval = walk(page).find(node => node.tag === 'input' && node.type === 'checkbox' &&
    walk(page).some(parent => parent.tag === 'label' && parent.children.includes(node) && parent.textContent.includes('I approve')));
  approval.checked = true;
  const key = field(page, 'API key for this session'); key.value = 'draft-test-key'; await key.dispatch('input');
  await action(page, 'Load available models').dispatch('click');
  const request = f.calls.find(call => call.path === '/api/models');
  assert.equal(request.data.settings.api_url, 'https://api.openai.com/v1');
  assert.equal(request.data.settings.provider, 'openai-compatible');
  assert.equal(request.data.api_key, 'draft-test-key');
  assert.equal(f.settings.api_url, 'https://neuroforge.io/v1');
  const catalogue = field(page, 'Available model'); catalogue.value = 'exact-model'; await catalogue.dispatch('change');
  assert.equal(field(page, 'Model identifier').value, 'exact-model');
  await action(page, 'Save my preferences').dispatch('click');
  assert.equal(f.settings.model, 'exact-model');
  assert.equal(f.settings.provider, 'openai-compatible');
  assert.equal(key.value, '');
  await action(page, 'Check saved connection').dispatch('click');
  assert.equal(f.calls.at(-1).path, '/api/health');
  assert.equal(f.calls.some(call => call.path === '/api/chat'), false);
});

test('ChatGPT sign-in is distinct from making it the active connection', async t => {
  const f = fixture(t), page = await settingsPage();
  const route = field(page, 'Assistant connection'); route.value = 'chatgpt'; await route.dispatch('change');
  assert.equal(field(page, 'Maximum answer length').disabled, true);
  assert.equal(field(page, 'API base address').disabled, true);
  await action(page, 'Sign in with ChatGPT').dispatch('click');
  assert.equal(f.settings.provider, 'openai-compatible');
  assert.equal(f.calls.filter(call => call.path === '/api/settings' && call.data).length, 0);
  f.setAccount({connected: true, pending: null, active_profile_id: 'profile-one', profiles: [{id: 'profile-one', name: 'Example'}]});
  await action(page, 'Refresh sign-in status').dispatch('click');
  assert.match(page.textContent, /Signed in to ChatGPT as Example/);
  assert.equal(f.settings.provider, 'openai-compatible');
});


test('identity-only ChatGPT consent never looks ready for plan inference', async t => {
  const f = fixture(t), page = await settingsPage();
  const route = field(page, 'Assistant connection'); route.value = 'chatgpt'; await route.dispatch('change');
  f.setAccount({connected: true, plan_usage: false, pending: {status: 'complete', message: 'Plan usage denied.'}, profiles: []});
  await action(page, 'Refresh sign-in status').dispatch('click');
  assert.match(page.textContent, /Plan usage was not enabled/);
  assert.equal(walk(page).some(node => node.tag === 'button' && node.textContent === 'Cancel sign-in'), false);
  assert.equal(walk(page).some(node => node.tag === 'a' && node.textContent === 'Continue sign-in with ChatGPT'), false);
});


test('retained disconnected registrations reconnect without creating another account', async t => {
  const f = fixture(t), page = await settingsPage();
  f.setAccount({connected: false, pending: null, active_profile_id: '', profiles: [
    {id: 'retained-one', name: 'Returning member', connected: false, plan_usage: false}]});
  const route = field(page, 'Assistant connection'); route.value = 'chatgpt'; await route.dispatch('change');
  await action(page, 'Refresh sign-in status').dispatch('click');
  assert.equal(field(page, 'Saved ChatGPT account').value, 'retained-one');
  await action(page, 'Reconnect selected account').dispatch('click');
  assert.deepEqual(f.calls.find(call => call.path === '/api/account/connect').data, {profile_id: 'retained-one'});
  assert.equal(action(page, 'Reconnect selected account').disabled, true);
  assert.ok(walk(page).some(node => node.tag === 'a' && node.textContent === 'Continue sign-in with ChatGPT'));
  await action(page, 'Cancel sign-in').dispatch('click');
  assert.equal(action(page, 'Reconnect selected account').disabled, false);
  assert.equal(f.calls.filter(call => call.path === '/api/settings' && call.data).length, 0);
});

test('choosing a different saved account requires explicit activation', async t => {
  const f = fixture(t), page = await settingsPage();
  f.setAccount({connected: true, plan_usage: true, pending: null, active_profile_id: 'first', profiles: [
    {id: 'first', name: 'First member', connected: true, plan_usage: true},
    {id: 'second', name: 'Second member', connected: true, plan_usage: true}]});
  const route = field(page, 'Assistant connection'); route.value = 'chatgpt'; await route.dispatch('change');
  await action(page, 'Refresh sign-in status').dispatch('click');
  const chooser = field(page, 'Saved ChatGPT account'); chooser.value = 'second'; await chooser.dispatch('change');
  assert.equal(f.calls.some(call => call.path === '/api/account/activate'), false);
  assert.match(page.textContent, /Signed in to ChatGPT as First member/);
  await action(page, 'Use selected account').dispatch('click');
  assert.deepEqual(f.calls.find(call => call.path === '/api/account/activate').data, {profile_id: 'second'});
  assert.match(page.textContent, /Signed in to ChatGPT as Second member/);
  assert.equal(f.settings.provider, 'openai-compatible');
});

test('adding another account is an explicit new registration action', async t => {
  const f = fixture(t), page = await settingsPage();
  f.setAccount({connected: true, plan_usage: true, pending: null, active_profile_id: 'first', profiles: [
    {id: 'first', name: 'Existing member', connected: true, plan_usage: true}]});
  const route = field(page, 'Assistant connection'); route.value = 'chatgpt'; await route.dispatch('change');
  await action(page, 'Refresh sign-in status').dispatch('click');
  await action(page, 'Add another ChatGPT account').dispatch('click');
  assert.deepEqual(f.calls.find(call => call.path === '/api/account/connect').data, {});
  assert.equal(action(page, 'Add another ChatGPT account').disabled, true);
});
