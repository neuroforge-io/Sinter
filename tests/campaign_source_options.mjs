import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignSourceOptions, matchingCampaignSources,
  MAX_CAMPAIGN_SOURCE_MATCHES} from '../src/sinter/web/campaign-source-options.js';

const source = (index, changes = {}) => ({id: index.toString(16).padStart(32, '0'),
  title: `Fictional saved source ${index}`, url: `https://example.invalid/${index}`,
  checked_at: '2026-09-30', notes: 'No permission has been granted.', ...changes});

test('a large source register has bounded matches in record order with exact canonical objects', () => {
  const sources = Object.freeze(Array.from({length: 81}, (_, index) => Object.freeze(source(index))));
  const original = structuredClone(sources);
  const options = campaignSourceOptions(sources);
  const result = matchingCampaignSources(options, '');
  assert.equal(result.total, 81);
  assert.equal(result.matches.length, MAX_CAMPAIGN_SOURCE_MATCHES);
  result.matches.forEach((option, index) => assert.equal(option.source, sources[index]));
  assert.equal(matchingCampaignSources(options, sources[80].id).matches[0].source, sources[80]);
  assert.deepEqual(sources, original);
});

test('duplicate title and website use uniquely long source identities even when six-digit prefixes collide', () => {
  const sources = [source(1, {title: 'Same title'}), source(2, {title: 'Same title'})];
  const options = campaignSourceOptions(sources);
  assert.notEqual(options[0].label, options[1].label);
  options.forEach((option, index) => {
    assert.match(option.label, /Source /);
    assert.equal(matchingCampaignSources(options, option.label).matches[0].source, sources[index]);
  });
  assert.equal(matchingCampaignSources(options, 'Same title').total, 2);
});

test('search handles literal Unicode titles and website text without changing source wording or dates', () => {
  const row = Object.freeze(source(4, {title: 'Überprüfung e\u0301 🌱 <keep>',
    url: 'https://www.example.invalid/exact/path', checked_at: ''}));
  const options = campaignSourceOptions([row]);
  for (const query of ['überPRÜFUNG', 'é 🌱', 'example.invalid', '/exact/path', '<keep>']) {
    assert.equal(matchingCampaignSources(options, query).matches[0].source, row);
  }
  assert.equal(options[0].source.title, row.title);
  assert.equal(options[0].source.checked_at, '');
  assert.equal(matchingCampaignSources(options, 'permission').total, 0);
});

test('missing, malformed or duplicate source identities cannot become selectable choices', () => {
  const duplicate = source(9);
  const options = campaignSourceOptions([null, {}, {id: ' ', title: 'Blank identity'},
    {id: 23, title: 'Numeric identity'}, {...source(10), title: ' '},
    duplicate, {...duplicate, title: 'Conflicting source'}, source(11)]);
  assert.deepEqual(options.map(option => option.source.id), [source(11).id]);
  assert.deepEqual(campaignSourceOptions(null), []);
  assert.deepEqual(matchingCampaignSources([], 'unknown'), {total: 0, matches: []});
});
