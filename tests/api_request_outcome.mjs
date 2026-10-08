/** Request outcomes describe observed delivery, never authorise a write replay. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {acknowledgedCampaign} from '../src/sinter/web/campaign-save.js';

let sequence = 0;
async function fixture(t, handler) {
  const calls = [];
  const bridge = globalThis.sinterBrowser;
  delete globalThis.sinterBrowser;
  t.after(() => { globalThis.sinterBrowser = bridge; });
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({path, method: options.method});
    if (path === '/api/session') return Response.json({token: 'fictional-session'});
    return handler(path, options);
  });
  const {request} = await import(`../src/sinter/web/api.js?outcome=${++sequence}`);
  return {request, calls};
}

const savePath = '/api/campaigns/save';
const save = {data: {document: {title: 'Fictional only'}}};
async function failure(operation) {
  try { await operation; assert.fail('The request should fail'); }
  catch (error) { assert.notEqual(error.code, 'ERR_ASSERTION'); return error; }
}

test('a pre-aborted save performs no token work and is not dispatched', async t => {
  const f = await fixture(t, () => assert.fail('No dispatch'));
  const controller = new AbortController(); controller.abort();
  const error = await failure(f.request(savePath, {...save, signal: controller.signal}));
  assert.deepEqual(f.calls, []);
  assert.equal(error.requestState.path, savePath);
  assert.equal(error.requestState.dispatched, false);
  assert.equal(error.requestState.outcome, 'not-sent');
  assert.equal(error.cause.name, 'AbortError');
});

test('abort while the token GET is pending never dispatches the save', async t => {
  const f = await fixture(t, () => assert.fail('No save dispatch'));
  let resolve, started;
  const ready = new Promise(yes => { started = yes; });
  t.mock.method(globalThis, 'fetch', async path => {
    f.calls.push({path}); started();
    return new Promise(yes => { resolve = yes; });
  });
  const controller = new AbortController();
  const pending = f.request(savePath, {...save, signal: controller.signal});
  await ready; controller.abort(); resolve(Response.json({token: 'fictional-session'}));
  const error = await failure(pending);
  assert.deepEqual(f.calls, [{path: '/api/session'}]);
  assert.equal(error.requestState.dispatched, false);
  assert.equal(error.requestState.outcome, 'not-sent');
});

test('a failed token GET retains its immutable original context under outer not-sent POST', async t => {
  const f = await fixture(t, () => assert.fail('No save dispatch'));
  t.mock.method(globalThis, 'fetch', async path => {
    f.calls.push({path});
    return Response.json({error: 'Fictional session refusal café 中文',
      partial_result: {original: 'retained'}}, {status: 403});
  });
  const outer = await failure(f.request(savePath, save));
  const first = outer.cause;
  assert.notEqual(outer, first);
  assert.equal(outer.message, 'Fictional session refusal café 中文');
  assert.equal(outer.status, 403);
  assert.deepEqual(outer.partialResult, {original: 'retained'});
  assert.deepEqual(outer.requestState, {path: savePath, method: 'POST', dispatched: false,
    responseStatus: null, responseComplete: false, outcome: 'not-sent'});
  assert.deepEqual(first.requestState, {path: '/api/session', method: 'GET', dispatched: true,
    responseStatus: 403, responseComplete: true, outcome: 'rejected'});
  assert.ok(Object.isFrozen(first.requestState));
  assert.ok(Object.isFrozen(outer.requestState));
  assert.throws(() => { outer.requestState.outcome = 'confirmed'; }, TypeError);
  assert.deepEqual(f.calls, [{path: '/api/session'}]);
});

for (const kind of ['TypeError', 'AbortError']) {
  test(`dispatched save ${kind} retains unknown outcome and never retries`, async t => {
    const cause = kind === 'TypeError' ? new TypeError('Fictional network failure')
      : new DOMException('Fictional aborted fetch', 'AbortError');
    const f = await fixture(t, () => { throw cause; });
    const error = await failure(f.request(savePath, save));
    assert.equal(error.cause, cause);
    assert.equal(error.requestState.dispatched, true);
    assert.equal(error.requestState.responseStatus, null);
    assert.equal(error.requestState.outcome, 'unconfirmed');
    assert.doesNotMatch(error.message, /then retry|before retrying/);
    if (kind === 'TypeError') assert.match(error.message, /Cannot reach the local Sinter app/);
    assert.deepEqual(f.calls.map(call => call.path), ['/api/session', savePath]);
  });
}

for (const status of [200, 400, 403, 409, 500, 502]) {
  for (const kind of ['malformed', 'aborted']) {
    test(`HTTP ${status} ${kind} body retains observed status and correct uncertainty`, async t => {
      const cause = new DOMException('Fictional interrupted body', 'AbortError');
      const body = kind === 'malformed' ? '{' : new ReadableStream({start(c) { c.error(cause); }});
      const f = await fixture(t, () => new Response(body, {status}));
      const error = await failure(f.request(savePath, save));
      assert.equal(error.status, status);
      assert.equal(error.requestState.responseStatus, status);
      assert.equal(error.requestState.responseComplete, false);
      assert.equal(error.requestState.outcome,
        [400, 403, 409].includes(status) ? 'rejected' : 'unconfirmed');
      assert.equal(error.cause.name, kind === 'malformed' ? 'SyntaxError' : 'AbortError');
      if (kind === 'aborted') assert.equal(error.cause, cause);
      assert.match(error.message, /could not be read/);
      assert.deepEqual(f.calls.map(call => call.path), ['/api/session', savePath]);
    });
  }
}

for (const status of [400, 403, 409, 500, 502]) {
  test(`parsed null HTTP ${status} keeps the rejection status without a false connection error`, async t => {
    const f = await fixture(t, () => Response.json(null, {status}));
    const error = await failure(f.request(savePath, save));
    assert.equal(error.status, status);
    assert.equal(error.message, `The request failed (${status}).`);
    assert.equal(error.requestState.responseComplete, true);
    assert.equal(error.requestState.outcome, status < 500 ? 'rejected' : 'unconfirmed');
    assert.doesNotMatch(error.message, /Cannot reach/);
    assert.deepEqual(f.calls.map(call => call.path), ['/api/session', savePath]);
  });

  test(`complete HTTP ${status} preserves exact backend wording and partial result`, async t => {
    const message = 'Fictional refusal — café 中文 🧭 <img>.';
    const partial = {text: 'Original partial result', status: 'needs_review'};
    const f = await fixture(t, () => Response.json({error: message, partial_result: partial}, {status}));
    const error = await failure(f.request(savePath, save));
    assert.equal(error.message, message);
    assert.equal(error.status, status);
    assert.deepEqual(error.partialResult, partial);
    assert.equal(error.requestState.responseComplete, true);
    assert.equal(error.requestState.outcome, status < 500 ? 'rejected' : 'unconfirmed');
    assert.deepEqual(f.calls.map(call => call.path), ['/api/session', savePath]);
  });
}

test('normal successful save result remains unchanged and performs one POST', async t => {
  const expected = {id: 'fictional', revision: 2, document: {title: 'Fictional only'}};
  const f = await fixture(t, () => Response.json(expected));
  assert.deepEqual(await f.request(savePath, save), expected);
  assert.deepEqual(f.calls.map(call => call.path), ['/api/session', savePath]);
});

for (const status of [null, 400, 500]) {
  test(`portable bridge ${status ?? 'unknown'} failure retains conservative outcome`, async t => {
    const f = await fixture(t, () => assert.fail('No HTTP request'));
    const cause = new Error('Fictional bridge result');
    if (status !== null) cause.status = status;
    cause.partialResult = {retained: true};
    let calls = 0;
    globalThis.sinterBrowser = {request: async () => { calls++; throw cause; }};
    const error = await failure(f.request(savePath, save));
    assert.equal(error.message, cause.message);
    assert.deepEqual(error.partialResult, {retained: true});
    assert.equal(error.requestState.outcome, status === 400 ? 'rejected' : 'unconfirmed');
    assert.equal(calls, 1); assert.deepEqual(f.calls, []);
  });
}

test('pre-aborted portable request never invokes its bridge', async t => {
  const f = await fixture(t, () => assert.fail('No HTTP request'));
  globalThis.sinterBrowser = {request: () => assert.fail('No bridge request')};
  const controller = new AbortController(); controller.abort();
  const error = await failure(f.request(savePath, {...save, signal: controller.signal}));
  assert.equal(error.requestState.outcome, 'not-sent');
  assert.deepEqual(f.calls, []);
});

const acknowledged = {id: 'ab'.repeat(16), revision: 2, document: {
  schema: 'sinter-campaign/v1', title: 'Fictional only', organisation: '', objective: '',
  signatory: '', sender_role: '', contact_details: '', opportunities: [], requirements: [],
  answers: [], budget: [], actions: [{owner: '', owner_status: 'unknown', due: ''}],
  sources: [], communications: [], assets: [],
}};

test('usable acknowledgement retains exact source values and reference without rewriting owners or dates', () => {
  const before = structuredClone(acknowledged);
  assert.equal(acknowledgedCampaign(acknowledged), acknowledged);
  assert.deepEqual(acknowledged, before);
});

for (const reply of [null, {}, {...acknowledged, id: ''}, {...acknowledged, revision: 0},
  {...acknowledged, document: null}, {...acknowledged, document: {...acknowledged.document, budget: null}},
  {...acknowledged, document: {...acknowledged.document, communications: [null]}}]) {
  test(`unusable acknowledged shape ${JSON.stringify(reply)} is unconfirmed and unmodified`, async t => {
    const before = structuredClone(reply);
    const f = await fixture(t, () => Response.json(reply));
    const error = await failure(f.request(savePath, {...save, acceptResponse: acknowledgedCampaign}));
    assert.deepEqual(error.partialResult, reply);
    assert.equal(error.requestState.outcome, 'unconfirmed');
    assert.equal(error.requestState.responseStatus, 200);
    assert.equal(error.requestState.responseComplete, true);
    assert.ok(Object.isFrozen(error.requestState));
    assert.deepEqual(reply, before);
  });
}

test('an asynchronous success admission failure retains HTTP200 context and first fault', async t => {
  const f = await fixture(t, () => Response.json(acknowledged));
  const cause = new Error('Fictional rendering failure');
  const first = new TypeError('Fictional malformed row');
  const rollback = new Error('Fictional rollback failure');
  cause.cause = first; cause.rollbackError = rollback;
  cause.partialResult = acknowledged;
  const error = await failure(f.request(savePath, {...save, acceptResponse: async () => { throw cause; }}));
  assert.equal(error, cause);
  assert.equal(error.cause, first); assert.equal(error.rollbackError, rollback);
  assert.equal(error.requestState.responseStatus, 200);
  assert.equal(error.requestState.responseComplete, true);
  assert.equal(error.requestState.outcome, 'unconfirmed');
});

test('portable malformed-success admission preserves no invented HTTP status', async t => {
  const f = await fixture(t, () => assert.fail('No HTTP request'));
  globalThis.sinterBrowser = {request: async () => null};
  const error = await failure(f.request(savePath, {...save, acceptResponse: acknowledgedCampaign}));
  assert.equal(error.requestState.responseStatus, null);
  assert.equal(error.requestState.responseComplete, true);
  assert.equal(error.requestState.outcome, 'unconfirmed');
  assert.deepEqual(f.calls, []);
});
