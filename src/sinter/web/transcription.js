/** Review UI for local audio; labels are human edits, never biometric identity. */
import {h, button, field, check, notice, download} from './ui.js';
import {request} from './api.js';

export function timestamp(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function reviewTranscript(transcript, player, onChange) {
  let page = 0;
  const edited = structuredClone(transcript);
  const flagged = check('Show passages needing review only');
  const list = h('div', {class: 'transcript-list'}), feedback = h('div', {'aria-live': 'polite'});
  const pagination = h('div', {class: 'button-row'});
  const root = h('section', {class: 'transcript-review', 'aria-label': 'Review the recording'},
    h('h3', {}, 'Listen. Check. Keep the original.'),
    h('p', {class: 'muted'}, `${transcript.segments.length} passages / ${timestamp(transcript.duration)} / ${transcript.review_count || 0} flagged for review. Unflagged passages can still be wrong.`),
    notice('Use labels such as SPEAKER_01 after listening. Confirm their names in the speaker section. JSON keeps the original words, timings and review flags; subtitles do not.'),
    flagged.wrap, list, pagination, feedback);
  let stopAt = null;
  const stop = () => { if (stopAt !== null && player.currentTime >= stopAt) { player.pause(); stopAt = null; } };
  player.addEventListener('timeupdate', stop);
  root.dispose = () => player.removeEventListener('timeupdate', stop);
  function render() {
    const rows = edited.segments.map((segment, index) => ({segment, index}))
      .filter(({segment}) => !flagged.input.checked || segment.review_flags?.length);
    const pages = Math.max(1, Math.ceil(rows.length / 20)); page = Math.min(page, pages - 1);
    list.replaceChildren(...rows.slice(page * 20, (page + 1) * 20).map(({segment, index}) => {
      const label = field(`Speaker label for passage ${index + 1}`, 'text', segment.speaker,
        'Recording labels are not confirmed identities.', {maxLength: 100});
      const apply = button('Keep this speaker label', async () => {
        const value = label.input.value.trim();
        if (!value) { feedback.replaceChildren(notice('Enter a label or use Unidentified.', 'error')); return; }
        const original = {...segment};
        segment.original_speaker ??= segment.speaker;
        segment.speaker = value;
        segment.label_origin = 'human review against recording';
        try { await onChange(edited); feedback.replaceChildren(notice('Speaker label recorded. Original label preserved in the JSON transcript.', 'success')); }
        catch (error) { edited.segments[index] = original; feedback.replaceChildren(notice(error.message, 'error')); render(); }
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
