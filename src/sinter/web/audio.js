import {h, button, field, selectField, check, notice} from './ui.js';
import {request, waitForJob} from './api.js';
import {reviewTranscript} from './transcription.js';

const BACKEND_LABELS = {
  'erais-native': 'ERAIS native — this computer',
  'erais-neuroforge': 'ERAIS configured service',
  'faster-whisper': 'faster-whisper — local alternative',
};

export function backendChoices(status) {
  return (Array.isArray(status?.backends) ? status.backends : [])
    .filter(item => item && item.installed === true)
    .map(item => ({
      id: String(item.id), label: BACKEND_LABELS[item.id] || String(item.id),
      models: Array.isArray(item.models) ? item.models.filter(model => typeof model === 'string') : [],
      modelLabels: item.model_labels && typeof item.model_labels === 'object' ? item.model_labels : {},
      network: item.network_required === true,
    }));
}

export function defaultBackend(choices) {
  return choices.find(item => item.id === 'erais-native')?.id
    || choices.find(item => item.id === 'erais-neuroforge')?.id
    || choices.find(item => item.id === 'faster-whisper')?.id || '';
}

export function requiresTransmissionConsent(backendId) {
  return backendId === 'erais-neuroforge';
}

export function audioForm(onTranscript, setBusy, isBusy) {
  const file = field('Meeting recording', 'file', '', 'WAV, MP3, M4A, OGG, FLAC, WebM or MP4. Up to 25 MB; the CLI accepts up to 500 MB.', {accept: '.wav,.mp3,.m4a,.ogg,.flac,.webm,.mp4'});
  const backend = selectField('Recognition backend', [], '', 'The actual backend is reported with the transcript.');
  const model = selectField('Recognition model', [], '', 'Models are populated from the selected installed backend.');
  const language = selectField('Recording language', [['en', 'English'], ['auto', 'Detect automatically'], ['fr', 'French'], ['de', 'German'], ['es', 'Spanish'], ['it', 'Italian'], ['pt', 'Portuguese'], ['zh', 'Chinese'], ['ja', 'Japanese'], ['ar', 'Arabic'], ['hi', 'Hindi']], 'en', 'Choose the known language to avoid unnecessary guessing.');
  const channels = check('This recording has two isolated microphone tracks. Transcribe each channel separately.');
  const permission = check('I have permission to process this recording and understand it may contain private information.');
  const transmit = check('I authorize sending this recording to the configured ERAIS network service.');
  transmit.wrap.hidden = true;
  const downloads = check('Allow a speech model download if it is not already on this computer.');
  const message = h('div', {'aria-live': 'polite'}), capability = h('div', {'aria-live': 'polite'});
  const player = h('audio', {controls: true, preload: 'metadata', 'aria-label': 'Local recording playback'});
  player.hidden = true;
  const review = h('div'); let jobId = null, objectURL = null, disposed = false, reviewUI = null;
  let choices = [];
  const selectedChoice = () => choices.find(item => item.id === backend.input.value);
  function syncBackendControls() {
    const choice = selectedChoice();
    transmit.wrap.hidden = !requiresTransmissionConsent(backend.input.value);
    model.input.replaceChildren();
    for (const name of choice?.models || [])
      model.input.append(h('option', {value: name}, choice?.modelLabels?.[name] || name));
    model.input.value = choice?.models?.[0] || '';
    channels.input.disabled = choice?.network === true;
  }
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
      choices = backendChoices(result);
      backend.input.replaceChildren();
      for (const choice of choices)
        backend.input.append(h('option', {value: choice.id}, choice.label));
      backend.input.value = defaultBackend(choices);
      syncBackendControls();
      capability.replaceChildren(notice(
        choices.length ? 'Installed local or configured speech backends are ready. The transcript reports which one ran.' : result.notice,
        choices.length ? 'success' : ''));
      if (!choices.length) capability.append(h('p', {class: 'fine'}, 'From the Sinter folder, run the setup helper. It installs into .venv, not your system Python. Then restart Sinter.'),
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
  backend.input.addEventListener('change', syncBackendControls);
  const start = button('Transcribe with the selected backend', async () => {
    if (isBusy()) return;
    const chosen = file.input.files[0];
    if (!chosen || !chosen.size || chosen.size > 25 * 1024 * 1024 || !permission.input.checked) {
      message.replaceChildren(notice('Choose a non-empty recording no larger than 25 MB and confirm permission.', 'error')); return;
    }
    const choice = selectedChoice();
    if (!choice) { message.replaceChildren(notice('Choose an installed recognition backend.', 'error')); return; }
    if (requiresTransmissionConsent(choice.id) && !transmit.input.checked) {
      message.replaceChildren(notice('Authorize sending this recording to the configured ERAIS service, or choose a local backend.', 'error')); return;
    }
    if (choice.network && channels.input.checked) {
      message.replaceChildren(notice('The configured network service does not support isolated-channel mode. Choose a local backend or disable channel separation.', 'error')); return;
    }
    setBusy(true); controls.disabled = true; cancel.hidden = false; cancel.disabled = true;
    try {
      const status = await request('/api/speech');
      if (!choices.length) throw new Error('Speech recognition is not installed in this Sinter environment. Run the setup helper above, then restart.');
      message.textContent = 'Reading the selected file into your local workbench...';
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1]);
        reader.onerror = () => reject(new Error('The recording could not be read.'));
        reader.readAsDataURL(chosen);
      });
      const job = await request('/api/transcribe', {data: {filename: chosen.name, audio: encoded, consent: true,
        allow_download: downloads.input.checked, model: model.input.value, language: language.input.value,
        split_channels: channels.input.checked, backend: backend.input.value}});
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
  controls.append(file.wrap, h('div', {class: 'form-grid'}, backend.wrap, model.wrap, language.wrap), channels.wrap,
    h('p', {class: 'fine'}, 'Leave channel separation off for a room microphone or ordinary stereo mix. A track can still contain more than one voice.'),
    permission.wrap, transmit.wrap, downloads.wrap, start);
  const root = h('details', {'data-audio-panel': ''}, h('summary', {}, 'Start with an audio recording (optional)'),
    notice('Local backends process on this computer. A configured ERAIS service receives the recording at its explicit endpoint. Model downloads require permission. Recognition can omit or invent words; review the original recording.'),
    button('Check transcription setup', diagnose, 'quiet'), capability, controls, player, cancel, message, review);
  root.addEventListener('toggle', () => { if (root.open && !capability.childNodes.length) diagnose(); });
  root.dispose = () => { disposed = true; player.pause(); player.removeAttribute('src'); if (objectURL) URL.revokeObjectURL(objectURL); reviewUI?.dispose(); };
  return root;
}
