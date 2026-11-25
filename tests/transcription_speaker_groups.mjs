import assert from 'node:assert/strict';
import test from 'node:test';
import {
  mergeSpeaker, relabelPassage, renameSpeaker, speakerGroups,
  undoSpeakerRevision,
} from '../src/sinter/web/transcription.js';

test('speaker groups count passages and expose anonymous clusters', () => {
  const groups = speakerGroups([
    {speaker: 'Speaker A'}, {speaker: 'Speaker A'}, {speaker: 'Speaker B'},
    {speaker: 'Unidentified'}, {speaker: ''}, {},
  ]);
  assert.deepEqual(groups, [
    {label: 'Unidentified', count: 3, duration: 0, anonymous: false},
    {label: 'Speaker A', count: 2, duration: 0, anonymous: true},
    {label: 'Speaker B', count: 1, duration: 0, anonymous: true},
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


test('group duration is the sum of its passage spans', () => {
  const groups = speakerGroups([
    {speaker: 'Speaker A', start: 1, end: 4},
    {speaker: 'Speaker A', start: 10, end: 12.5},
    {speaker: 'Speaker B', start: 4, end: 9},
    {speaker: 'Speaker B', start: 9, end: 9},
  ]);
  const byLabel = Object.fromEntries(groups.map(group => [group.label, group]));
  assert.equal(byLabel['Speaker A'].duration, 5.5);
  assert.equal(byLabel['Speaker B'].duration, 5);
});

test('merging groups records a reversible revision', () => {
  const transcript = {segments: [
    {speaker: 'Speaker A', text: 'first'},
    {speaker: 'Speaker B', text: 'second'},
    {speaker: 'Speaker A', text: 'third'},
  ]};
  assert.equal(mergeSpeaker(transcript, 'Speaker A', 'Speaker B'), 2);
  assert.equal(transcript.segments[0].speaker, 'Speaker B');
  assert.equal(transcript.speaker_revisions.length, 1);
  const revision = transcript.speaker_revisions[0];
  assert.equal(revision.operation, 'merge_group');
  assert.deepEqual(revision.segment_indices, [0, 2]);
  assert.deepEqual(revision.previous, {0: 'Speaker A', 2: 'Speaker A'});
  const undone = undoSpeakerRevision(transcript);
  assert.equal(undone.revision_id, revision.revision_id);
  assert.equal(transcript.segments[0].speaker, 'Speaker A');
  assert.equal(transcript.segments[2].speaker, 'Speaker A');
  assert.equal(undone.undone, true);
  assert.equal(undoSpeakerRevision(transcript), null);
});

test('relabelling one passage keeps earlier group renaming reversible', () => {
  const transcript = {segments: [
    {speaker: 'Speaker A', text: 'first'},
    {speaker: 'Speaker A', text: 'second'},
  ]};
  renameSpeaker(transcript, 'Speaker A', 'Chair');
  assert.equal(relabelPassage(transcript, 1, 'Treasurer'), 1);
  assert.equal(transcript.segments[1].speaker, 'Treasurer');
  assert.equal(transcript.speaker_revisions.length, 2);
  assert.equal(transcript.speaker_revisions[1].previous_revision, 'R1');
  undoSpeakerRevision(transcript);
  assert.equal(transcript.segments[1].speaker, 'Chair');
  undoSpeakerRevision(transcript);
  assert.equal(transcript.segments[0].speaker, 'Speaker A');
  assert.equal(transcript.segments[1].speaker, 'Speaker A');
});
