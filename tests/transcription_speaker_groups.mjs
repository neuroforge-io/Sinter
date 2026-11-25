import assert from 'node:assert/strict';
import test from 'node:test';
import {renameSpeaker, speakerGroups} from '../src/sinter/web/transcription.js';

test('speaker groups count passages and expose anonymous clusters', () => {
  const groups = speakerGroups([
    {speaker: 'Speaker A'}, {speaker: 'Speaker A'}, {speaker: 'Speaker B'},
    {speaker: 'Unidentified'}, {speaker: ''}, {},
  ]);
  assert.deepEqual(groups, [
    {label: 'Unidentified', count: 3, anonymous: false},
    {label: 'Speaker A', count: 2, anonymous: true},
    {label: 'Speaker B', count: 1, anonymous: true},
  ]);
});

test('renaming a speaker preserves the original label on every passage', () => {
  const transcript = {segments: [
    {speaker: 'Speaker A', text: 'first'},
    {speaker: 'Speaker B', text: 'second'},
    {speaker: 'Speaker A', text: 'third', original_speaker: 'Speaker A'},
  ]};
  assert.equal(renameSpeaker(transcript, 'Speaker A', 'Chair'), 2);
  assert.equal(transcript.segments[0].speaker, 'Chair');
  assert.equal(transcript.segments[0].original_speaker, 'Speaker A');
  assert.equal(transcript.segments[0].label_origin, 'human review against recording');
  assert.equal(transcript.segments[1].speaker, 'Speaker B');
  assert.equal(transcript.segments[2].original_speaker, 'Speaker A');
  assert.equal(renameSpeaker(transcript, 'Speaker B', '  '), 0);
  assert.equal(renameSpeaker(transcript, 'Speaker B', 'Speaker B'), 0);
});
