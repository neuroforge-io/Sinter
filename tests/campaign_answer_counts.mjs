import test from 'node:test';
import assert from 'node:assert/strict';
import {campaignAnswerCounts} from '../src/sinter/web/campaign-answer-counts.js';

test('empty and whitespace-only input has no approximate words', () => {
  assert.deepEqual(campaignAnswerCounts(), {characters: 0, words: 0});
  assert.deepEqual(campaignAnswerCounts(''), {characters: 0, words: 0});
  assert.deepEqual(campaignAnswerCounts(' \t\r\n\u0085\u00a0\u2003\u2028\u2029\uFEFF'),
    {characters: 10, words: 0});
});

test('Unicode code points and whitespace separators do not rewrite the input', () => {
  const text = 'Café e\u0301 🐝\n第二行';
  assert.deepEqual(campaignAnswerCounts(text), {characters: 13, words: 4});
  assert.equal(text, 'Café e\u0301 🐝\n第二行');
  assert.deepEqual(campaignAnswerCounts('one\r\ntwo\tthree\u0085four\u00a0five\uFEFFsix'),
    {characters: 28, words: 6});
});

test('approximate words are whitespace-delimited, without linguistic claims', () => {
  assert.deepEqual(campaignAnswerCounts("Don't split hyphenated-words or 第二行."),
    {characters: 36, words: 5});
  assert.deepEqual(campaignAnswerCounts('第二行'), {characters: 3, words: 1});
  assert.deepEqual(campaignAnswerCounts('🐝🐝'), {characters: 2, words: 1});
  assert.deepEqual(campaignAnswerCounts('a\u0301'), {characters: 2, words: 1});
});

test('the maximum local draft is counted without a character or word admission decision', () => {
  const text = '🐝 '.repeat(10000);
  assert.deepEqual(campaignAnswerCounts(text), {characters: 20000, words: 10000});
  const answer = {text, limit: null, status: 'draft'};
  campaignAnswerCounts(answer.text);
  assert.deepEqual(answer, {text, limit: null, status: 'draft'});
});
