import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../src/sinter/web/draft-state.js', import.meta.url), 'utf8');
const draftState = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

function state() {
  const drafts = new Map(), dirty = new Set();
  return {drafts, dirty, remember: (...args) => draftState.rememberDraft(drafts, dirty, ...args)};
}

test('clean saved campaign and tab-state updates do not trigger exit warnings', () => {
  const s = state();
  s.remember('campaigns', {id: 'saved-campaign', dirty: false, tab: 'overview'});
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, false), false);
  s.remember('campaigns', {id: 'saved-campaign', dirty: false, tab: 'budget'});
  assert.equal(s.drafts.get('campaigns').tab, 'budget');
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, false), false);
});

test('a changed draft warns, then an explicitly clean save clears that warning', () => {
  const s = state();
  s.remember('campaigns', {id: 'saved-campaign', dirty: true});
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, false), true);
  s.remember('campaigns', {id: 'saved-campaign', dirty: false}, {dirty: false});
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, false), false);
});

test('ordinary edited route work warns while fictional examples do not', () => {
  const s = state();
  s.remember('brief', {title: 'A real draft'});
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, false), true);
  s.remember('meeting', {title: 'Example transcript', demo: true});
  assert.equal(s.drafts.has('meeting'), false);
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, false), true);
});

test('active work still warns, and clean state in another route leaves dirty work intact', () => {
  const s = state();
  s.remember('brief', {title: 'Unfinished letter'});
  s.remember('campaigns', {id: 'saved-campaign', dirty: false});
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, false), true);
  s.dirty.clear();
  assert.equal(draftState.shouldWarnBeforeExit(s.dirty, true), true);
});
