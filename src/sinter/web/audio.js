import {h, button, field, selectField, check, notice} from './ui.js';
import {request, waitForJob} from './api.js';

export function audioForm(onTranscript, setBusy, isBusy) {
  const file = field('Meeting recording', 'file', '', 'Up to 25 MB here; use the command line for larger recordings.', {accept: '.wav,.mp3,.m4a,.ogg,.flac,.webm,.mp4'});
  const model = selectField('Local speech model', [['tiny', 'Tiny / quickest'], ['base', 'Base / balanced'], ['small', 'Small / more resources']], 'base');
  const permission = check('I have permission to process this recording and understand it may contain private information.');
  const downloads = check('Allow a speech model download if it is not already on this computer.');
  const message = h('div', {'aria-live': 'polite'});
  let jobId;
  const cancel = button('Cancel transcription', async () => {
    if (jobId) await request('/api/jobs/cancel', {data: {id: jobId}})
      .catch(error => message.replaceChildren(notice(error.message, 'error')));
  });
  cancel.hidden = true;
  const start = button('Transcribe on this computer', async () => {
    if (isBusy()) return;
    const chosen = file.input.files[0];
    if (!chosen || chosen.size > 25 * 1024 * 1024 || !permission.input.checked) {
      message.replaceChildren(notice('Choose a recording no larger than 25 MB and confirm permission.', 'error')); return;
    }
    setBusy(true); start.disabled = true; cancel.hidden = false;
    try {
      const capability = await request('/api/speech');
      if (!capability.available) throw new Error('Local transcription is an optional extra. See Getting started for installation. You can import a transcript without it.');
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1]);
        reader.onerror = () => reject(new Error('The recording could not be read.'));
        reader.readAsDataURL(chosen);
      });
      const job = await request('/api/transcribe', {data: {filename: chosen.name, audio: encoded, consent: true,
        allow_download: downloads.input.checked, model: model.input.value}});
      jobId = job.id;
      const transcript = await waitForJob(jobId, job => { message.textContent = job.message || 'Transcribing locally...'; });
      await onTranscript(transcript);
      message.replaceChildren(notice('Transcription complete. Speaker separation and identity were not inferred.', 'success'));
    } catch (error) { message.replaceChildren(notice(error.message, 'error')); }
    finally { setBusy(false); start.disabled = false; cancel.hidden = true; jobId = null; }
  });
  return h('details', {}, h('summary', {}, 'Start with an audio recording (optional)'),
    notice('Speech recognition is not installed by default. Audio stays on this computer. Transcription may be inaccurate; '
      + 'automatic speaker separation and identity recognition are not included. A model download is separate from uploading a recording.'),
    file.wrap, model.wrap, permission.wrap, downloads.wrap, h('div', {class: 'button-row'}, start, cancel), message);
}
