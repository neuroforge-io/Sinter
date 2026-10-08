import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {home} from '../src/sinter/web/home.js';
import {helpPage} from '../src/sinter/web/help.js';
import {gardenGuide, gardenSeed} from '../src/sinter/web/garden-practice.js';

class TestNode {
  constructor(tag = '#text', text = '') {
    this.tag = tag; this.children = []; this.attributes = {}; this.events = {};
    this._text = text;
  }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ''; this.children = []; this.append(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, handler) { this.events[name] = handler; }
  click() { return this.events.click?.({currentTarget: this}); }
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
    createTextNode: text => new TestNode('#text', String(text))});
  replaceGlobal(t, 'sinterBrowser', browser ? {} : undefined);
  replaceGlobal(t, 'fetch', () => { throw new Error('Onboarding must not send a request.'); });
  const casebook = JSON.parse(readFileSync(new URL('../src/sinter/web/offline-garden-casebook.json', import.meta.url)));
  const campaign = JSON.parse(readFileSync(new URL('../src/sinter/web/offline-garden-campaign.json', import.meta.url)));
  const bundle = {schema: 'sinter-practice-bundle/v1', id: 'offline-garden',
    fictional: true, casebook, campaign};
  const opened = [], routes = [], checks = [];
  return {bundle, opened, routes, checks,
    go: route => routes.push(route),
    openGarden: kind => opened.push({kind, seed: gardenSeed(kind, bundle)}),
    checkConnection: async () => { checks.push('health'); return {ok: false, message: 'Public service unavailable. Local work remains available.'}; }};
}

function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function control(page, label) {
  const found = walk(page).filter(node => node.tag === 'button' && node.textContent === label);
  assert.equal(found.length, 1, `Expected one reachable ${label} control`);
  return found[0];
}

for (const browser of [false, true]) {
  const edition = browser ? 'browser' : 'installed';
  test(`${edition} overview leads to the named local handover and preserves the actual source bundle`, t => {
    const f = fixture(t, browser), before = structuredClone(f.bundle);
    const page = home(f.go, new Map(), {}, f.openGarden);
    const controls = walk(page).filter(node => node.tag === 'button');
    assert.equal(controls[0].textContent, 'Open garden handover');
    assert.match(controls[0].className, /primary/);
    assert.doesNotMatch(controls[1].className, /primary/);
    control(page, 'Open garden handover').click();
    assert.equal(f.opened.length, 1);
    assert.equal(f.opened[0].kind, 'casebooks');
    const book = f.opened[0].seed.book;
    assert.equal(book.title, 'Fictional garden project - volunteer handover');
    assert.equal(book.document_type, 'handover');
    assert.deepEqual(book.documents, before.casebook.documents);
    assert.equal(book.fingerprint, before.casebook.fingerprint);
    assert.equal(book.questions, before.casebook.questions);
    assert.match(book.documents.at(-1).content, /No person has accepted/);
    assert.match(book.documents.at(-1).content, /Earlier-round.*historical/);
    assert.equal(book.signatory, '');
    book.documents[0].content = 'Local practice edit';
    assert.deepEqual(f.bundle, before, 'Opening and editing the copy must not rewrite the source bundle');
    assert.deepEqual(f.routes, []);
    assert.deepEqual(f.checks, []);
    assert.match(page.textContent, /source-only document/);
    assert.match(page.textContent, /unknown insurance/);
    assert.match(page.textContent, /Save project keeps inputs; Save to My workspace keeps edited reports/);
    assert.match(page.textContent, /Wait for Saved/);
    if (browser) {
      assert.match(page.textContent, /After the app loads, this practice runs locally without a model/);
      assert.match(page.textContent, /not unsaved editor inputs/);
      assert.doesNotMatch(page.textContent, /No account or internet needed/);
    } else assert.match(page.textContent, /closing this browser tab does not stop the app/);
    control(page, 'Try an example').click();
    control(page, 'Getting started').click();
    assert.deepEqual(f.routes, ['brief?example=1', 'help']);
  });

  test(`${edition} getting started puts the handover before qualifications and explains distinct copies`, t => {
    const f = fixture(t, browser), page = helpPage(f);
    assert.equal(page.children[0].children[0].textContent, 'Start with one piece of work');
    assert.equal(page.children[1].attributes['aria-label'], 'Fictional garden practice project');
    const firstDetails = page.children.findIndex(node => node.tag === 'details');
    assert.ok(firstDetails > 1, 'The actionable handover must precede detailed limits');
    control(page, 'Open garden handover').click();
    assert.equal(f.opened[0].kind, 'casebooks');
    control(page, 'Open garden campaign').click();
    assert.equal(f.opened[1].kind, 'campaigns');
    assert.deepEqual(f.opened[1].seed.document, f.bundle.campaign);
    assert.match(page.textContent, /Save project keeps the notes and questions/);
    assert.match(page.textContent, /Save to My workspace keeps an edited report/);
    assert.match(page.textContent, /Find project inputs in Community casebooks and saved reports in My workspace/);
    assert.match(page.textContent, /Export project backup contains casebook inputs; export an edited report separately/);
    assert.match(page.textContent, /campaign backup contains the campaign, not a saved report/);
    assert.match(page.textContent, /Restore a casebook backup opens a new unsaved project/);
    assert.match(page.textContent, /traceability, not truth/);
    assert.match(page.textContent, /not verified answers/);
    assert.deepEqual(f.checks, [], 'Opening help must not test a hosted connection');
    if (browser) {
      assert.match(page.textContent, /After the app loads/);
      assert.match(page.textContent, /Unsaved editor inputs are not included/);
      assert.match(page.textContent, /imported search watches start paused/);
      assert.match(page.textContent, /operating-system file paths, ChatGPT sign-in and RKC executable connections need installed Sinter/);
      assert.equal(walk(page).filter(node => node.tag === 'button' && node.textContent === 'Check public API connection').length, 0);
    } else {
      assert.match(page.textContent, /choose Quit Sinter/);
      assert.match(page.textContent, /Core native installers do not bundle the speech engine/);
    }
  });
}

test('an existing unsaved project remains the first return path and is never opened as practice automatically', t => {
  const f = fixture(t, false);
  const drafts = new Map([['casebooks', {book: {title: 'Current real notes'}}]]);
  const page = home(f.go, drafts, {full_name: 'Ari'}, f.openGarden);
  const controls = walk(page).filter(node => node.tag === 'button');
  assert.equal(controls[0].textContent, 'Continue: Current real notes');
  controls[0].click();
  assert.deepEqual(f.routes, ['casebooks']);
  assert.deepEqual(f.opened, []);
  assert.equal(drafts.get('casebooks').book.title, 'Current real notes');
});

test('the optional installed connection check runs only when chosen and keeps local recovery advice', async t => {
  const f = fixture(t, false), page = helpPage(f);
  assert.deepEqual(f.checks, []);
  await control(page, 'Check public API connection').click();
  assert.deepEqual(f.checks, ['health']);
  assert.match(page.textContent, /Public service unavailable\. Local work remains available/);
  assert.match(page.textContent, /does not establish useful model answers/);
  const failed = helpPage({...f, checkConnection: async () => { throw new Error('Connection failed.'); }});
  await control(failed, 'Check public API connection').click();
  assert.match(failed.textContent, /Connection failed\. Local examples still work/);
});

test('practice guidance keeps reopen and backup scope explicit without rewriting campaign history', t => {
  const f = fixture(t, true);
  const handover = gardenGuide('casebooks', f.openGarden);
  assert.match(handover.textContent, /Reopen inputs in Community casebooks and reports in My workspace/);
  assert.match(handover.textContent, /Export project inputs and the edited report separately/);
  assert.match(handover.textContent, /insurance answer remains unknown/);
  const campaign = gardenGuide('campaigns', f.openGarden);
  assert.match(campaign.textContent, /without claiming an accepted owner or confirmed date/);
  assert.match(campaign.textContent, /Earlier-round records remain historical/);
});
