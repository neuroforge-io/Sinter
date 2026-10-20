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
  let settings = {schema_version: 1, full_name: '', role: '', email: '', phone: '', website: '',
    location: '', organisation_type: '', api_url: 'https://neuroforge.io/v1', provider: 'openai-compatible',
    model: 'auto', max_tokens: 64, organisation: '', theme: 'dark', text_size: 'normal',
    density: 'comfortable', reduce_motion: false, rkc_port: 8787, rkc_executable: '', ...initial};
  let revision = 1, heldKey = '';
  let account = {connected: false, pending: null, profiles: []};
  const calls = [], holds = [];
  const current = () => ({settings: {...settings}, revision: revision.toString(16).padStart(32, '0'),
    has_session_key: !!heldKey, warning: '', environment_override: false});
  function reply(path, data) {
    if (path === '/api/session') return Response.json({token: 'test-local-token'});
    if (path === '/api/settings') {
      if (data) {
        if ('expected_revision' in data && data.expected_revision !== current().revision)
          return Response.json({error: 'Saved settings changed. Check what was saved.'}, {status: 409});
        if (data.settings.api_url && data.settings.api_url !== settings.api_url ||
            data.settings.provider && data.settings.provider !== settings.provider) heldKey = '';
        settings = {...settings, ...data.settings};
        if ('api_key' in data) heldKey = data.api_key;
        revision++;
      }
      return Response.json(current());
    }
    if (path === '/api/account/connect') return Response.json({...account, pending: {status: 'awaiting'}, auth_url: 'https://auth.openai.com/test'});
    if (path === '/api/account') return Response.json(account);
    if (path === '/api/account/cancel') { account = {...account, pending: null}; return Response.json(account); }
    if (path === '/api/account/disconnect') { account = {...account, connected: false, plan_usage: false}; return Response.json(account); }
    if (path === '/api/account/activate') {
      const selected = account.profiles.find(item => item.id === data.profile_id);
      account = {...account, active_profile_id: selected.id, connected: selected.connected, plan_usage: selected.plan_usage};
      return Response.json(account);
    }
    if (path === '/api/models') return Response.json({models: [{id: 'exact-model'}]});
    if (path === '/api/health') return Response.json({ok: true, message: 'Catalogue found.', settings_revision: current().revision});
    throw new Error('Unexpected request ' + path);
  }
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    const data = options.body ? JSON.parse(options.body) : null; calls.push({path, data});
    const hold = holds.find(item => item.path === path && item.writing === !!data && !item.used);
    const response = reply(path, data);
    if (!hold) return response;
    hold.used = true; hold.entered({path, data}); const result = await hold.wait;
    if (result.error) throw result.error;
    return result.response || response;
  });
  return {calls, get settings() { return {...settings}; }, get snapshot() { return current(); },
    setAccount(value) { account = value; },
    defer(path, writing = false) {
      let release, entered;
      const wait = new Promise(resolve => { release = resolve; });
      const started = new Promise(resolve => { entered = resolve; });
      holds.push({path, writing, wait, entered, used: false});
      return {started, release: () => release({}), drop: () => release({error: new TypeError('Fixture lost acknowledgement')}),
        respond: value => release({response: Response.json(value)}),
        reject: () => release({response: Response.json({error: 'Old fixture failure'}, {status: 503})})};
    },
    externalUpdate(values) { reply('/api/settings', {settings: values}); }
  };
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

test('native 16-token catalogue keeps the saved model and output cap', async t => {
  const f = fixture(t, {model: 'erais-native-qwen3', max_tokens: 16});
  const page = await settingsPage();
  await action(page, 'Load available models').dispatch('click');
  const lookup = f.calls.find(call => call.path === '/api/models');
  assert.deepEqual(lookup.data.settings, {
    provider: 'openai-compatible', api_url: 'https://neuroforge.io/v1'
  });
  assert.equal(field(page, 'Model identifier').value, 'erais-native-qwen3');
  assert.equal(Number(field(page, 'Maximum answer length').value), 16);
  assert.equal(field(page, 'Available model').value, '');
  assert.equal(f.settings.model, 'erais-native-qwen3');
  assert.equal(f.settings.max_tokens, 16);
  assert.equal(f.calls.filter(call => call.path === '/api/settings' && call.data).length, 0);
  assert.equal(f.calls.some(call => call.path === '/api/chat'), false);
});

test('connection-only save leaves profile and appearance drafts unsaved', async t => {
  const f = fixture(t), page = await settingsPage();
  field(page, 'Your full name').value = 'Fictional editor';
  field(page, 'Colour theme').value = 'light';
  field(page, 'Local RKC port').value = '1';
  const model = field(page, 'Model identifier'); model.value = 'chosen-model'; await model.dispatch('input');
  await action(page, 'Save connection').dispatch('click');
  const write = f.calls.find(call => call.path === '/api/settings' && call.data);
  assert.deepEqual(Object.keys(write.data.settings).sort(), ['api_url', 'max_tokens', 'model', 'provider']);
  assert.equal(f.settings.model, 'chosen-model'); assert.equal(f.settings.full_name, '');
  assert.equal(f.settings.theme, 'dark');
  assert.equal(field(page, 'Your full name').value, 'Fictional editor');
  assert.equal(field(page, 'Colour theme').value, 'light');
});

test('save acknowledgement preserves newer connection and key drafts', async t => {
  const f = fixture(t), page = await settingsPage();
  const model = field(page, 'Model identifier'), key = field(page, 'API key for this session');
  model.value = 'first-model'; await model.dispatch('input');
  key.value = 'fictional-first'; await key.dispatch('input');
  const held = f.defer('/api/settings', true), saving = action(page, 'Save connection').dispatch('click');
  await held.started;
  model.value = 'newer-model'; await model.dispatch('input');
  key.value = 'fictional-newer'; await key.dispatch('input');
  await action(page, 'Forget the session API key').dispatch('click');
  assert.equal(f.calls.filter(call => call.path === '/api/settings' && call.data).length, 1);
  held.release(); await saving;
  assert.equal(f.settings.model, 'first-model'); assert.equal(model.value, 'newer-model');
  assert.equal(key.value, 'fictional-newer');
  assert.equal(action(page, 'Check saved connection').disabled, true);
  assert.match(page.textContent, /Connection changes are not saved/);
});

test('Forget changes only the held key and preserves a replacement key draft', async t => {
  const f = fixture(t, {organisation: 'Fictional group', model: 'erais-native-qwen3', max_tokens: 16});
  const page = await settingsPage(), key = field(page, 'API key for this session');
  key.value = 'fictional-held'; await key.dispatch('input');
  await action(page, 'Save connection').dispatch('click');
  const before = f.settings, held = f.defer('/api/settings', true);
  const forgetting = action(page, 'Forget the session API key').dispatch('click');
  await held.started;
  key.value = 'fictional-replacement'; await key.dispatch('input');
  held.release(); await forgetting;
  assert.deepEqual(f.settings, before); assert.equal(f.snapshot.has_session_key, false);
  assert.equal(key.value, 'fictional-replacement');
  const write = f.calls.filter(call => call.path === '/api/settings' && call.data).at(-1);
  assert.deepEqual(write.data.settings, {}); assert.equal(write.data.api_key, '');
  assert.equal(typeof write.data.expected_revision, 'string');
});

test('lost save acknowledgement needs explicit readback before a separate Forget', async t => {
  const f = fixture(t), page = await settingsPage();
  const model = field(page, 'Model identifier'), key = field(page, 'API key for this session');
  model.value = 'committed-model'; await model.dispatch('input');
  key.value = 'fictional-committed'; await key.dispatch('input');
  const held = f.defer('/api/settings', true), saving = action(page, 'Save connection').dispatch('click');
  await held.started; held.drop(); await saving;
  const writes = () => f.calls.filter(call => call.path === '/api/settings' && call.data);
  assert.equal(f.settings.model, 'committed-model'); assert.equal(writes().length, 1);
  assert.match(page.textContent, /unconfirmed outcome/); assert.equal(key.value, 'fictional-committed');
  await action(page, 'Forget the session API key').dispatch('click');
  await action(page, 'Save connection').dispatch('click');
  assert.equal(writes().length, 1);
  await action(page, 'Check what was saved').dispatch('click');
  assert.equal(writes().length, 1);
  assert.match(page.textContent, /Earlier unconfirmed requests remain unconfirmed/);
  await action(page, 'Forget the session API key').dispatch('click');
  assert.equal(writes().length, 2); assert.equal(f.settings.model, 'committed-model');
  assert.equal(f.snapshot.has_session_key, false); assert.equal(key.value, 'fictional-committed');
  assert.match(page.textContent, /unconfirmed outcome/);
});

test('malformed successful acknowledgement cannot discard drafts or release the recovery gate', async t => {
  const f = fixture(t), page = await settingsPage(), key = field(page, 'API key for this session');
  key.value = 'fictional-retained'; await key.dispatch('input');
  const held = f.defer('/api/settings', true), saving = action(page, 'Save connection').dispatch('click');
  await held.started; held.respond({settings: {model: 'incomplete'}}); await saving;
  assert.equal(key.value, 'fictional-retained'); assert.match(page.textContent, /unconfirmed outcome/);
  assert.equal(action(page, 'Save connection').disabled, true);
  await action(page, 'Check what was saved').dispatch('click');
  assert.equal(action(page, 'Save connection').disabled, false);
});

test('revision conflict retains form and needs an explicit observation', async t => {
  const f = fixture(t), page = await settingsPage();
  f.externalUpdate({organisation: 'Other explicit local change'});
  const model = field(page, 'Model identifier'); model.value = 'draft-model'; await model.dispatch('input');
  await action(page, 'Save connection').dispatch('click');
  assert.equal(f.settings.model, 'auto'); assert.equal(model.value, 'draft-model');
  assert.equal(action(page, 'Save connection').disabled, true);
  await action(page, 'Check what was saved').dispatch('click');
  await action(page, 'Save connection').dispatch('click');
  assert.equal(f.settings.organisation, 'Other explicit local change');
  assert.equal(f.settings.model, 'draft-model');
});

for (const failure of [false, true]) test('late health ' + (failure ? 'error' : 'success') + ' cannot verify A after A→B→A', async t => {
  const f = fixture(t), page = await settingsPage(), model = field(page, 'Model identifier');
  const held = f.defer('/api/health'), checking = action(page, 'Check saved connection').dispatch('click');
  await held.started;
  model.value = 'temporary-model'; await model.dispatch('input');
  model.value = 'auto'; await model.dispatch('input');
  if (failure) held.reject(); else held.release();
  await checking;
  assert.doesNotMatch(page.textContent, /Model connection checked|Old fixture failure/);
  assert.equal(action(page, 'Check saved connection').disabled, false);
});

test('old health settlement cannot release or replace a newer check', async t => {
  const f = fixture(t), page = await settingsPage(), model = field(page, 'Model identifier');
  const old = f.defer('/api/health'), first = action(page, 'Check saved connection').dispatch('click');
  await old.started; model.value = 'B'; await model.dispatch('input');
  model.value = 'auto'; await model.dispatch('input');
  const newer = f.defer('/api/health'), second = action(page, 'Check saved connection').dispatch('click');
  await newer.started; old.reject(); await first;
  assert.equal(action(page, 'Check saved connection').disabled, true);
  assert.doesNotMatch(page.textContent, /Old fixture failure/);
  newer.release(); await second;
  assert.match(page.textContent, /Model connection checked/);
});

for (const order of ['catalogue-first', 'health-first']) test('unchanged health and catalogue remain independent: ' + order, async t => {
  const f = fixture(t), page = await settingsPage();
  const health = f.defer('/api/health'), catalogue = f.defer('/api/models', true);
  const checking = action(page, 'Check saved connection').dispatch('click');
  const loading = action(page, 'Load available models').dispatch('click');
  await Promise.all([health.started, catalogue.started]);
  if (order === 'catalogue-first') { catalogue.release(); await loading; health.release(); await checking; }
  else { health.release(); await checking; catalogue.release(); await loading; }
  assert.match(page.textContent, /Model connection checked/);
  assert.equal(field(page, 'Available model').value, '');
});

test('late catalogue and detached choices cannot replace a newer connection', async t => {
  const f = fixture(t), page = await settingsPage(), model = field(page, 'Model identifier');
  await action(page, 'Load available models').dispatch('click');
  const oldChoice = field(page, 'Available model');
  const held = f.defer('/api/models', true), loading = action(page, 'Load available models').dispatch('click');
  await held.started;
  oldChoice.value = 'exact-model'; await oldChoice.dispatch('change');
  assert.equal(model.value, 'auto');
  model.value = 'new-model'; await model.dispatch('input');
  held.release(); await loading;
  assert.equal(walk(page).some(node => node.tag === 'label' && node.textContent === 'Available model'), false);
  oldChoice.value = 'exact-model'; await oldChoice.dispatch('change');
  assert.equal(model.value, 'new-model');
});

test('persistent complete sign-in records preserve a staged account choice', async t => {
  const f = fixture(t), page = await settingsPage();
  f.setAccount({connected: true, plan_usage: true, pending: {status: 'complete'}, active_profile_id: 'A', profiles: [
    {id: 'A', name: 'A', connected: true, plan_usage: true}, {id: 'B', name: 'B', connected: true, plan_usage: true}]});
  const route = field(page, 'Assistant connection'); route.value = 'chatgpt'; await route.dispatch('change');
  await action(page, 'Refresh sign-in status').dispatch('click');
  const chooser = field(page, 'Saved ChatGPT account'); chooser.value = 'B'; await chooser.dispatch('change');
  await action(page, 'Refresh sign-in status').dispatch('click');
  assert.equal(chooser.value, 'B'); assert.equal(f.calls.some(call => call.path === '/api/account/activate'), false);
});

test('account activation fences an older status response and model check', async t => {
  const f = fixture(t), page = await settingsPage();
  f.setAccount({connected: true, plan_usage: true, pending: null, active_profile_id: 'A', profiles: [
    {id: 'A', name: 'First', connected: true, plan_usage: true}, {id: 'B', name: 'Second', connected: true, plan_usage: true}]});
  const route = field(page, 'Assistant connection'); route.value = 'chatgpt'; await route.dispatch('change');
  await action(page, 'Refresh sign-in status').dispatch('click');
  const model = field(page, 'Model identifier'); model.value = 'fictional-chatgpt-model'; await model.dispatch('input');
  await action(page, 'Save connection').dispatch('click');
  const health = f.defer('/api/health'), checking = action(page, 'Check saved connection').dispatch('click');
  await health.started;
  const old = f.defer('/api/account'), refreshing = action(page, 'Refresh sign-in status').dispatch('click');
  await old.started;
  const chooser = field(page, 'Saved ChatGPT account'); chooser.value = 'B'; await chooser.dispatch('change');
  await action(page, 'Use selected account').dispatch('click');
  old.release(); health.release(); await Promise.all([refreshing, checking]);
  assert.match(page.textContent, /Signed in to ChatGPT as Second/);
  assert.doesNotMatch(page.textContent, /Model connection checked/);
});

test('a mismatched health revision cannot verify the shown saved model', async t => {
  const f = fixture(t), page = await settingsPage();
  const held = f.defer('/api/health'), checking = action(page, 'Check saved connection').dispatch('click');
  await held.started;
  held.respond({ok: true, message: 'Different saved context', settings_revision: 'f'.repeat(32)});
  await checking;
  assert.doesNotMatch(page.textContent, /Model connection checked/);
  assert.match(page.textContent, /Saved settings changed before this check/);
});

test('a stale catalogue error remains a read failure, never an uncertain settings write', async t => {
  const f = fixture(t), page = await settingsPage(), model = field(page, 'Model identifier');
  const held = f.defer('/api/models', true), loading = action(page, 'Load available models').dispatch('click');
  await held.started; model.value = 'B'; await model.dispatch('input');
  model.value = 'auto'; await model.dispatch('input');
  held.reject(); await loading;
  assert.doesNotMatch(page.textContent, /Old fixture failure|unconfirmed outcome/);
  assert.equal(action(page, 'Save connection').disabled, false);
});

for (const invalid of [{max_tokens: 0}, {rkc_port: 1}]) test('unusable settings acknowledgement is not a save: ' + Object.keys(invalid)[0], async t => {
  const f = fixture(t), page = await settingsPage(), key = field(page, 'API key for this session');
  key.value = 'fictional-newer-key'; await key.dispatch('input');
  const held = f.defer('/api/settings', true), saving = action(page, 'Save connection').dispatch('click');
  await held.started;
  const reply = f.snapshot; reply.settings = {...reply.settings, ...invalid};
  held.respond(reply); await saving;
  assert.match(page.textContent, /unconfirmed outcome/);
  assert.equal(key.value, 'fictional-newer-key');
  assert.equal(action(page, 'Save connection').disabled, true);
});
