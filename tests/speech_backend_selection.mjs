import assert from 'node:assert/strict';
import test from 'node:test';
import {backendChoices, defaultBackend, requiresTransmissionConsent} from '../src/sinter/web/audio.js';

test('backend choices expose only installed backends and their real models', () => {
  const choices = backendChoices({backends: [
    {id: 'faster-whisper', installed: true, models: ['base.en'], network_required: false},
    {id: 'erais-native', installed: false, models: ['native-large']}]});
  assert.equal(choices.length, 1);
  assert.deepEqual(choices[0], {id: 'faster-whisper', label: 'faster-whisper — local alternative', models: ['base.en'], network: false});
});

test('native is preferred, then configured service, then local alternative', () => {
  assert.equal(defaultBackend([{id: 'faster-whisper'}, {id: 'erais-neuroforge'}, {id: 'erais-native'}]), 'erais-native');
  assert.equal(defaultBackend([{id: 'faster-whisper'}, {id: 'erais-neuroforge'}]), 'erais-neuroforge');
  assert.equal(defaultBackend([{id: 'faster-whisper'}]), 'faster-whisper');
  assert.equal(defaultBackend([]), '');
});

test('network transmission consent is separate and explicit', () => {
  assert.equal(requiresTransmissionConsent('erais-neuroforge'), true);
  assert.equal(requiresTransmissionConsent('erais-native'), false);
  assert.equal(requiresTransmissionConsent('faster-whisper'), false);
});
