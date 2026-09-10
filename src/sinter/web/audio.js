import {h, button, field, selectField, check, notice} from './ui.js';
import {request, waitForJob} from './api.js';
import {reviewTranscript} from './transcription.js';

export function audioForm(onTranscript, setBusy, isBusy) {
  const file = field('Meeting recording', 'file', '', 'WAV, MP3, M4A, OGG, FLAC, WebM or MP4. Up to 25 MB; the CLI accepts up to 500 MB.', {accept: '.wav,.mp3,.m4a,.ogg,.flac,.webm,.mp4'});
  const model = selectField('Local speech model', [['tiny', 'Quick preview / tiny'], ['base', 'Balanced / base'], ['small', 'More detail / small'], ['base.en', 'Balanced / English-only'], ['small.en', 'More detail / English-only']], 'base');
  const language = selectField('Recording language', [['en', 'English'], ['auto', 'Detect automatically'], ['fr', 'French'], ['de', 'German'], ['es', 'Spanish'], ['it', 'Italian'], ['pt', 'Portuguese'], ['zh', 'Chinese'], ['ja', 'Japanese'], ['ar', 'Arabic'], ['hi', 'Hindi']], 'en', 'Choose the known language to avoid unnecessary guessing.');
  const channels = check('This recording has two isolated microphone tracks. Transcribe each channel separately.');
  const permission = check('I have permission to process this recording and understand it may contain private information.');
  const downloads = check('Allow a speech model download if it is not already on this computer.');
  const message = h('div', {'aria-live': 'polite'}), capability = h('div', {'aria-live': 'polite'});
  const player = h('audio', {controls: true, preload: 'metadata', 'aria-label': 'Local recording playback'});
  player.hidden = true;
  const review = h('div'); let jobId = null, objectURL = null, disposed = false, reviewUI = null;
  const controls = h('fieldset', {}, h('legend', {class: 'sr-only'}, 'Local transcription settings'));
  const cancel = button('Cancel transcription', async () => {
    if (jobId) await request('/api/jobs/cancel', {data: {id: jobId}})
      .catch(error => message.replaceChildren(notice(error.message, 'error')));
  });
  cancel.hidden = true;
  async function diagnose() {
    capability.textContent = 'Checking this installation...';
    try {
      const result = await request('/api/speech');
      if (disposed) return;
      capability.replaceChildren(notice(result.notice, result.available ? 'success' : ''));
      if (!result.available) capability.append(h('p', {class: 'fine'}, 'From the Sinter folder, run the setup helper. It installs into .venv, not your system Python. Then restart Sinter.'),
        h('pre', {class: 'help-code'}, 'python3 setup_speech.py\n# Windows: py setup_speech.py'));
    } catch (error) { if (!disposed) capability.replaceChildren(notice(error.message, 'error')); }
  }
  file.input.addEventListener('change', () => {
    player.pause(); player.removeAttribute('src'); player.hidden = true;
    if (objectURL) URL.revokeObjectURL(objectURL); objectURL = null;
    reviewUI?.dispose(); review.replaceChildren(); reviewUI = null;
    const chosen = file.input.files[0];
    if (!chosen || chosen.size > 25 * 1024 * 1024) return;
    objectURL = URL.createObjectURL(chosen); player.src = objectURL; player.hidden = false;
  });
  const start = button('Transcribe on this computer', async () => {
    if (isBusy()) return;
    const chosen = file.input.files[0];
    if (!chosen || !chosen.size || chosen.size > 25 * 1024 * 1024 || !permission.input.checked) {
      message.replaceChildren(notice('Choose a non-empty recording no larger than 25 MB and confirm permission.', 'error')); return;
    }
    setBusy(true); controls.disabled = true; cancel.hidden = false; cancel.disabled = true;
    try {
      const status = await request('/api/speech');
      if (!status.available) throw new Error('Local speech is not installed in this Sinter environment. Run the setup helper above, then restart.');
      message.textContent = 'Reading the selected file into your local workbench...';
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1]);
        reader.onerror = () => reject(new Error('The recording could not be read.'));
        reader.readAsDataURL(chosen);
      });
      const job = await request('/api/transcribe', {data: {filename: chosen.name, audio: encoded, consent: true,
        allow_download: downloads.input.checked, model: model.input.value, language: language.input.value,
        split_channels: channels.input.checked}});
      jobId = job.id; cancel.disabled = false;
      const transcript = await waitForJob(jobId, job => { message.textContent = job.message || 'Transcribing locally...'; });
      if (!transcript.segments.length) {
        message.replaceChildren(notice('No speech detected. Check the recording and microphone level. Your existing transcript was not replaced.')); return;
      }
      reviewUI?.dispose(); reviewUI = reviewTranscript(transcript, player, onTranscript); review.replaceChildren(reviewUI);
      await onTranscript(transcript);
      message.replaceChildren(notice('Transcript ready for review. Listen back below; no names, decisions or missing words have been inferred.', 'success'));
    } catch (error) { message.replaceChildren(notice(error.message, 'error')); }
    finally { setBusy(false); controls.disabled = false; cancel.hidden = true; jobId = null; }
  }, 'primary');
  controls.append(file.wrap, h('div', {class: 'form-grid'}, model.wrap, language.wrap), channels.wrap,
    h('p', {class: 'fine'}, 'Leave channel separation off for a room microphone or ordinary stereo mix. A track can still contain more than one voice.'),
    permission.wrap, downloads.wrap, start);
  const root = h('details', {'data-audio-panel': ''}, h('summary', {}, 'Start with an audio recording (optional)'),
    notice('Audio stays on this computer. Model downloads require permission. Recognition can omit or invent words; review the original recording.'),
    button('Check transcription setup', diagnose, 'quiet'), capability, controls, player, cancel, message, review);
  root.addEventListener('toggle', () => { if (root.open && !capability.childNodes.length) diagnose(); });
  root.dispose = () => { disposed = true; player.pause(); player.removeAttribute('src'); if (objectURL) URL.revokeObjectURL(objectURL); reviewUI?.dispose(); };
  return root;
}
