/** Review UI for local audio; labels are human edits, never biometric identity. */
import {h, button, field, selectField, check, notice, download} from './ui.js';
import {request} from './api.js';

export function timestamp(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function speakerGroups(segments) {
  const groups = new Map();
  for (const segment of Array.isArray(segments) ? segments : []) {
    const label = typeof segment?.speaker === 'string' && segment.speaker.trim()
      ? segment.speaker.trim() : 'Unidentified';
    const entry = groups.get(label) || {label, count: 0, duration: 0, anonymous: false};
    entry.count += 1;
    const start = Number(segment?.start), end = Number(segment?.end);
    if (Number.isFinite(start) && Number.isFinite(end) && end > start)
      entry.duration += end - start;
    if (/^Speaker [A-Z]$/.test(label)) entry.anonymous = true;
    groups.set(label, entry);
  }
  return [...groups.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function recordRevision(edited, revision) {
  edited.speaker_revisions ??= [];
  const previous = edited.speaker_revisions.filter(row => !row.undone).at(-1);
  const record = {
    revision_id: `R${edited.speaker_revisions.length + 1}`,
    previous_revision: previous?.revision_id || null,
    undone: false,
    ...revision,
  };
  edited.speaker_revisions.push(record);
  return record;
}

export function renameSpeaker(edited, from, to, {operation = 'rename_group', reason = ''} = {}) {
  const value = String(to ?? '').trim();
  if (!value || value === from) return 0;
  const changed = [];
  const previous = {};
  for (const [index, segment] of (edited?.segments || []).entries()) {
    if ((segment.speaker || 'Unidentified') !== from) continue;
    previous[index] = segment.speaker || 'Unidentified';
    segment.original_speaker ??= segment.speaker;
    segment.speaker = value;
    segment.label_origin = 'human review against recording';
    changed.push(index);
  }
  if (!changed.length) return 0;
  recordRevision(edited, {
    operation, from, to: value, segment_indices: changed, previous, reason,
  });
  return changed.length;
}

export function representativePassage(edited, label) {
  const candidates = (edited?.segments || [])
    .map((segment, index) => ({segment, index}))
    .filter(({segment}) => (segment.speaker || 'Unidentified') === label);
  if (!candidates.length) return null;
  const score = ({segment}) => {
    const start = Number(segment.start), end = Number(segment.end);
    const duration = Number.isFinite(start) && Number.isFinite(end) && end > start
      ? end - start : 0;
    const flagged = (segment.review_flags || []).length;
    return (flagged ? 0 : 1_000_000) + duration;
  };
  return candidates.sort((a, b) => score(b) - score(a))[0];
}

export function mergeSpeaker(edited, from, into, reason = '') {
  return renameSpeaker(edited, from, into, {operation: 'merge_group', reason});
}

export function relabelPassage(edited, index, to, reason = '') {
  const segment = edited?.segments?.[index];
  const value = String(to ?? '').trim();
  if (!segment || !value) return 0;
  const current = segment.speaker || 'Unidentified';
  if (value === current) return 0;
  const previous = {[index]: current};
  segment.original_speaker ??= segment.speaker;
  segment.speaker = value;
  segment.label_origin = 'human review against recording';
  recordRevision(edited, {
    operation: 'relabel_passage', from: current, to: value,
    segment_indices: [index], previous, reason,
  });
  return 1;
}

export function undoSpeakerRevision(edited) {
  const revisions = edited?.speaker_revisions;
  if (!Array.isArray(revisions)) return null;
  const revision = [...revisions].reverse().find(row => !row.undone);
  if (!revision) return null;
  for (const index of revision.segment_indices || []) {
    const segment = edited.segments?.[index];
    const label = revision.previous?.[index];
    if (segment && label) segment.speaker = label;
  }
  revision.undone = true;
  revision.undone_at = new Date().toISOString();
  return revision;
}

export function reviewTranscript(transcript, player, onChange) {
  let page = 0;
  const edited = structuredClone(transcript);
  const flagged = check('Show passages needing review only');
  const list = h('div', {class: 'transcript-list'}), feedback = h('div', {'aria-live': 'polite'});
  const pagination = h('div', {class: 'button-row'}), groupsPanel = h('div', {class: 'speaker-groups'});
  const root = h('section', {class: 'transcript-review', 'aria-label': 'Review the recording'},
    h('h3', {}, 'Listen. Check. Keep the original.'),
    h('p', {class: 'muted'}, `${transcript.segments.length} passages / ${timestamp(transcript.duration)} / ${transcript.review_count || 0} flagged for review. Unflagged passages can still be wrong.`),
    notice('Use labels such as SPEAKER_01 after listening. Confirm their names in the speaker section. JSON keeps the original words, timings and review flags; subtitles do not.'),
    groupsPanel, flagged.wrap, list, pagination, feedback);
  let stopAt = null;
  const stop = () => { if (stopAt !== null && player.currentTime >= stopAt) { player.pause(); stopAt = null; } };
  player.addEventListener('timeupdate', stop);
  root.dispose = () => player.removeEventListener('timeupdate', stop);
  function renderGroups() {
    const groups = speakerGroups(edited.segments);
    const others = groups.filter(group => group.label !== 'Overlap');
    const rows = groups.filter(group => group.anonymous || group.count > 1).map(group => {
      const name = field(`Rename ${group.label}`, 'text', group.anonymous ? '' : group.label,
        `${group.count} passage${group.count === 1 ? '' : 's'} / ${timestamp(group.duration)}.`, {maxLength: 100});
      const listen = button('Listen to a passage', async () => {
        const chosen = representativePassage(edited, group.label);
        const segment = chosen?.segment;
        if (!segment) return;
        try {
          player.currentTime = Number(segment.start) || 0;
          stopAt = Math.min(Number(segment.end) || player.currentTime + 8, player.currentTime + 12);
          await player.play();
        } catch { feedback.replaceChildren(notice('Your browser could not play this format.', 'error')); }
      }, 'quiet');
      const apply = button('Rename every passage', async () => {
        const value = name.input.value.trim();
        const changed = renameSpeaker(edited, group.label, value);
        if (!changed) { feedback.replaceChildren(notice('Enter a different non-empty label.', 'error')); return; }
        try { await onChange(edited); feedback.replaceChildren(notice(`Renamed ${changed} passages. Original labels and a revision event remain in the JSON transcript.`, 'success')); render(); }
        catch (error) { undoSpeakerRevision(edited); feedback.replaceChildren(notice(error.message, 'error')); }
      }, 'quiet');
      const target = selectField(`Merge ${group.label} into`,
        [['', 'Choose a group'], ...others.filter(other => other.label !== group.label)
          .map(other => [other.label, `${other.label} (${other.count})`])]);
      const merge = button('Merge groups', async () => {
        const value = target.input.value;
        if (!value) { feedback.replaceChildren(notice('Choose the group that should receive these passages.', 'error')); return; }
        const changed = mergeSpeaker(edited, group.label, value);
        if (!changed) { feedback.replaceChildren(notice('Those passages already use that label.', 'error')); return; }
        try { await onChange(edited); feedback.replaceChildren(notice(`Merged ${changed} passages into ${value}. The merge is reversible in the JSON revisions.`, 'success')); render(); }
        catch (error) { undoSpeakerRevision(edited); feedback.replaceChildren(notice(error.message, 'error')); }
      }, 'quiet');
      return h('details', {}, h('summary', {}, `${group.label} — ${group.count} passages / ${timestamp(group.duration)}`),
        name.wrap, apply, listen, target.wrap, merge);
    });
    const revisions = (edited.speaker_revisions || []).filter(row => !row.undone);
    const undo = button('Undo last speaker change', async () => {
      const revision = undoSpeakerRevision(edited);
      if (!revision) { feedback.replaceChildren(notice('There is no speaker change to undo.', 'error')); return; }
      try { await onChange(edited); feedback.replaceChildren(notice(`Undid ${revision.operation}. The revision remains recorded as undone.`, 'success')); render(); }
      catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    }, 'quiet');
    undo.disabled = !revisions.length;
    groupsPanel.replaceChildren(...(rows.length ? [
      h('h4', {}, 'Speaker groups in this transcript'),
      h('p', {class: 'fine'}, `${revisions.length} human speaker revision${revisions.length === 1 ? '' : 's'} in this review.`),
      undo, ...rows] : [h('p', {class: 'fine'}, 'No speaker groups need review.')]));
  }
  function render() {
    renderGroups();
    const rows = edited.segments.map((segment, index) => ({segment, index}))
      .filter(({segment}) => !flagged.input.checked || segment.review_flags?.length);
    const pages = Math.max(1, Math.ceil(rows.length / 20)); page = Math.min(page, pages - 1);
    list.replaceChildren(...rows.slice(page * 20, (page + 1) * 20).map(({segment, index}) => {
      const label = field(`Speaker label for passage ${index + 1}`, 'text', segment.speaker,
        'Recording labels are not confirmed identities.', {maxLength: 100});
      const apply = button('Keep this speaker label', async () => {
        const value = label.input.value.trim();
        if (!value) { feedback.replaceChildren(notice('Enter a label or use Unidentified.', 'error')); return; }
        if (!relabelPassage(edited, index, value)) {
          feedback.replaceChildren(notice('Choose a different label.', 'error')); return;
        }
        try { await onChange(edited); feedback.replaceChildren(notice('Speaker label recorded. Original label and a revision event remain in the JSON transcript.', 'success')); }
        catch (error) { undoSpeakerRevision(edited); feedback.replaceChildren(notice(error.message, 'error')); render(); }
      }, 'quiet');
      const play = button(`Listen ${timestamp(segment.start)} to ${timestamp(segment.end)}`, async () => {
        try { player.currentTime = segment.start; stopAt = segment.end; await player.play(); }
        catch { feedback.replaceChildren(notice('Your browser could not play this format. Use your audio player or convert the recording to WAV.', 'error')); }
      }, 'quiet');
      const uncertain = (segment.words || []).filter(word => word.probability < .5).map(word => word.word.trim()).join(', ');
      return h('article', {class: 'transcript-passage'}, h('div', {class: 'passage-heading'},
        h('strong', {}, `Passage ${index + 1}`), play), h('p', {}, segment.text),
        ...(segment.review_flags || []).map(flag => notice(flag)),
        uncertain ? h('p', {class: 'fine'}, 'Words to check: ' + uncertain) : null,
        h('details', {}, h('summary', {}, 'Label this passage after listening'), label.wrap, apply));
    }));
    if (!rows.length) list.append(notice('No flagged passages in this view. This is not a guarantee of accuracy.'));
    const previous = button('Previous passages', () => { page--; render(); }, 'quiet'); previous.disabled = page === 0;
    const next = button('Next passages', () => { page++; render(); }, 'quiet'); next.disabled = page + 1 >= pages;
    pagination.replaceChildren(previous, h('span', {class: 'fine', role: 'status'}, `Page ${page + 1} of ${pages}`), next);
  }
  flagged.input.addEventListener('change', () => { page = 0; render(); });
  const exports = h('div', {class: 'button-row'});
  for (const format of ['json', 'srt', 'vtt', 'txt']) exports.append(button(`Download transcript ${format.toUpperCase()}`, async () => {
    try {
      if (format === 'json') {
        download('sinter-transcript-DRAFT.json', JSON.stringify(edited, null, 2), 'application/json');
      } else {
        const compact = {segments: edited.segments.map(({start, end, speaker, text}) => ({start, end, speaker, text}))};
        const {content} = await request('/api/transcript/export', {data: {transcript: compact, format}});
        download(`sinter-transcript-DRAFT.${format}`, content);
      }
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
  }, 'quiet'));
  root.append(exports); render(); return root;
}
