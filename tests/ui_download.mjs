import assert from 'node:assert/strict';
import test from 'node:test';
import {download} from '../src/sinter/web/ui.js';

function environment(t, failAt = '') {
  const saved = {document: globalThis.document, timeout: globalThis.setTimeout,
    create: URL.createObjectURL, revoke: URL.revokeObjectURL};
  const created = [], revoked = [], timers = [], links = [];
  globalThis.document = {
    createElement() {
      if (failAt === 'create') throw new Error('No link available');
      const link = {href: '', download: '', clicks: 0, removed: false,
        click() { this.clicks++; if (failAt === 'click') throw new Error('Download blocked'); },
        remove() { this.removed = true; }};
      links.push(link); return link;
    },
    body: {append() { if (failAt === 'append') throw new Error('No document available'); }},
  };
  URL.createObjectURL = blob => {
    const url = `blob:fictional-${created.length}`;
    created.push({url, blob}); return url;
  };
  URL.revokeObjectURL = url => revoked.push(url);
  globalThis.setTimeout = (callback, delay) => {
    if (failAt === 'timer') throw new Error('No cleanup timer available');
    timers.push({callback, delay}); return timers.length;
  };
  t.after(() => {
    if (saved.document === undefined) delete globalThis.document;
    else globalThis.document = saved.document;
    globalThis.setTimeout = saved.timeout;
    URL.createObjectURL = saved.create; URL.revokeObjectURL = saved.revoke;
  });
  return {created, revoked, timers, links};
}

test('download retains exact Unicode bytes, filename and MIME during a bounded handoff grace', async t => {
  const env = environment(t);
  const text = 'Fictional selected evidence 🌱 e\u0301\r\nNot agreed.';
  download('Fictional 🌱 evidence.json', text, 'application/json');
  assert.equal(await env.created[0].blob.text(), text);
  assert.equal(env.created[0].blob.type, 'application/json');
  assert.equal(env.links[0].download, 'Fictional 🌱 evidence.json');
  assert.equal(env.links[0].href, env.created[0].url);
  assert.equal(env.links[0].clicks, 1);
  assert.equal(env.links[0].removed, true);
  assert.deepEqual(env.revoked, []);
  assert.equal(env.timers[0].delay, 60000);
  env.timers[0].callback();
  assert.deepEqual(env.revoked, [env.created[0].url]);
});

test('independent Word and backup downloads retain their own content and cleanup', async t => {
  const env = environment(t);
  const word = new Blob([new Uint8Array([80, 75, 0, 255])], {type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'});
  download('fictional.docx', word, word.type);
  download('fictional-backup.json', '{"status":"unconfirmed"}', 'application/json');
  assert.deepEqual(new Uint8Array(await env.created[0].blob.arrayBuffer()), new Uint8Array([80, 75, 0, 255]));
  assert.equal(await env.created[1].blob.text(), '{"status":"unconfirmed"}');
  env.timers[1].callback();
  assert.deepEqual(env.revoked, [env.created[1].url]);
  env.timers[0].callback();
  assert.deepEqual(env.revoked, [env.created[1].url, env.created[0].url]);
});

for (const failure of ['create', 'append', 'click', 'timer']) {
  test(`a ${failure} failure releases the Blob immediately and propagates the failure`, t => {
    const env = environment(t, failure);
    assert.throws(() => download('fictional.txt', 'Local original'), /available|blocked/);
    assert.deepEqual(env.revoked, [env.created[0].url]);
    assert.deepEqual(env.timers, []);
    assert.ok(env.links.every(link => link.removed));
  });
}
