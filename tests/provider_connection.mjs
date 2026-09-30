import assert from 'node:assert/strict';
import test from 'node:test';
import {CONNECTION_PRESETS, connectionPreset, inferConnectionPreset,
  connectionTokenLimits, connectionChanged, connectionDestinationChanged,
  connectionStatus, availableModelIds} from '../src/sinter/web/provider-connection.js';

const saved = {provider: 'openai-compatible', api_url: 'https://neuroforge.io/v1', model: 'auto', max_tokens: 64};

test('presets use native Claude transport and provider-specific verified base addresses', () => {
  assert.equal(connectionPreset('anthropic').provider, 'anthropic');
  assert.equal(connectionPreset('anthropic').api_url, 'https://api.anthropic.com/v1');
  assert.equal(connectionPreset('gemini').api_url, 'https://generativelanguage.googleapis.com/v1beta/openai');
  assert.equal(connectionPreset('local').api_url, 'http://127.0.0.1:11434/v1');
  assert.equal(connectionPreset('neuroforge').model, 'auto');
  for (const preset of CONNECTION_PRESETS.filter(item => item.id !== 'neuroforge')) assert.equal(preset.model, '');
});

test('provider matching rejects lookalike hosts and preserves custom native transports', () => {
  assert.equal(inferConnectionPreset(saved), 'neuroforge');
  assert.equal(inferConnectionPreset({...saved, api_url: 'https://neuroforge.io/v1/'}), 'neuroforge');
  for (const api_url of ['https://neuroforge.io.example/v1', 'https://user@neuroforge.io/v1',
    'https://neuroforge.io/v1?override=1', 'https://neuroforge.io/v1#other',
    'https://neuroforge.io/other/../v1', 'https://neuroforge.io/%2e/v1',
    'https://neuroforge.io/v1\n']) {
    assert.equal(inferConnectionPreset({...saved, api_url}), 'custom');
  }
  assert.equal(inferConnectionPreset({api_url: 'https://api.anthropic.com/v1', provider: 'anthropic'}), 'anthropic');
  assert.equal(inferConnectionPreset({api_url: 'https://api.anthropic.com/v1', provider: 'openai-compatible'}), 'custom');
  assert.equal(inferConnectionPreset({api_url: 'http://[::1]:1234/v1'}), 'local');
});

test('native, dense and hybrid preview limits are explicit and never leak to custom providers', () => {
  assert.deepEqual(Object.fromEntries(Object.entries(connectionTokenLimits({...saved, model: 'erais-native-qwen3'})).filter(([key]) => key !== 'help')), {min: 1, max: 2048, effectiveMax: 128});
  assert.equal(connectionTokenLimits({...saved, model: 'erais-dense-gemma4-e4b'}).effectiveMax, 512);
  assert.equal(connectionTokenLimits({...saved, model: 'erais-fracture-gemma'}).max, 2048);
  assert.equal(connectionTokenLimits({...saved, api_url: 'https://another.example/v1', model: 'erais-native-qwen3'}).max, 8192);
  assert.equal(connectionTokenLimits({...saved, provider: 'anthropic', model: 'erais-native-qwen3'}).min, 32);
  assert.equal(connectionTokenLimits({...saved, api_url: 'https://neuroforge.io/other/../v1', model: 'erais-native-qwen3'}).min, 32);
});

test('saved output caps stay editable when an exact profile has a lower execution ceiling', () => {
  for (const model of ['auto', 'erais-native-qwen3', 'erais-dense-gemma4-e4b', 'erais-fracture-gemma']) {
    for (const max_tokens of [64, 128, 512, 2048]) {
      const state = {...saved, model, max_tokens};
      const limits = connectionTokenLimits(state);
      assert.ok(max_tokens >= limits.min && max_tokens <= limits.max);
      assert.equal(state.max_tokens, max_tokens);
    }
  }
});

test('unsaved changes disable remote checking and distinguish destination from model changes', () => {
  assert.equal(connectionChanged(saved, {...saved, api_url: `${saved.api_url}/`}), false);
  assert.equal(connectionDestinationChanged(saved, {...saved, model: 'erais-fracture-gemma'}), false);
  assert.equal(connectionDestinationChanged(saved, {...saved, provider: 'anthropic'}), true);
  assert.equal(connectionStatus({saved, draft: {...saved, max_tokens: 128}, verified: true}).canCheck, false);
  assert.equal(connectionStatus({saved, draft: saved, keyEdited: true}).canCheck, false);
  assert.equal(connectionStatus({saved, draft: saved, checking: true}).canCheck, false);
  assert.equal(connectionStatus({saved, draft: saved, verified: true}).kind, 'success');
});

test('model catalogue entries remain safe, distinct identifiers', () => {
  assert.deepEqual(availableModelIds({models: ['model-1', {id: 'model-2'}, 'model-1', '<bad>', null]}), ['model-1', 'model-2']);
  assert.deepEqual(availableModelIds({models: 'invalid'}), []);
  assert.equal(availableModelIds({models: Array.from({length: 300}, (_, index) => `model-${index}`)}).length, 256);
});
