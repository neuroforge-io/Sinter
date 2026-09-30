import {h, button, field, notice} from './ui.js';

/** Preserve the working copy, without applying server admission or normalization. */
export function campaignBackupText(document) {
  const text = JSON.stringify(document, null, 2);
  if (typeof text !== 'string') throw new TypeError('A campaign working copy is required.');
  return text;
}

/** Explicit local recovery: the callback reads the current editable campaign. */
export function campaignBackupControls(currentDocument) {
  if (typeof currentDocument !== 'function') throw new TypeError('A working-copy callback is required.');
  const feedback = h('div', {'aria-live': 'polite'});
  const recovery = field('Campaign backup text', 'textarea', '',
    'Complete JSON captured by Copy backup text or Refresh backup text. Keep it somewhere safe; it can contain private inputs.',
    {readOnly: true, rows: 10, spellcheck: false});
  const select = button('Select backup text', () => {
    recovery.input.focus(); recovery.input.select();
  }, 'quiet');
  const manual = h('div', {hidden: true}, recovery.wrap, select);
  let copying = false, generation = 0;
  function capture() {
    const text = campaignBackupText(currentDocument());
    recovery.input.value = text; manual.hidden = false; generation++;
    return text;
  }
  function captureError() {
    feedback.replaceChildren(notice('Could not prepare backup text. Your campaign inputs are unchanged.', 'error'));
  }
  const refresh = button('Refresh backup text', () => {
    try {
      capture();
      feedback.replaceChildren(notice('Backup text refreshed from your current inputs. Clipboard may contain an earlier snapshot; select the text below to copy manually. This does not save the campaign or create a file.', 'warning'));
    } catch { captureError(); }
  }, 'quiet');
  const copy = button('Copy backup text', async () => {
    if (copying) return;
    let text;
    try {
      text = capture();
    } catch { captureError(); return; }
    const copiedGeneration = generation;
    // Recovery remains usable even when the browser's clipboard promise stalls.
    copying = true; copy.disabled = true;
    feedback.replaceChildren(notice('Backup text is ready below. Trying your clipboard…'));
    try {
      const clipboard = globalThis.navigator?.clipboard;
      if (typeof clipboard?.writeText !== 'function') throw new Error('Clipboard unavailable');
      await clipboard.writeText(text);
      if (generation === copiedGeneration) {
        feedback.replaceChildren(notice('Backup text copied from your inputs at the time you clicked. Paste it into a text file to keep a copy. This does not save the campaign or create a file.', 'success'));
      }
    } catch {
      if (generation === copiedGeneration) {
        feedback.replaceChildren(notice('Clipboard unavailable. Select and copy the complete backup text below. This does not save the campaign or create a file.', 'warning'));
        recovery.input.focus(); recovery.input.select();
      }
    } finally {
      copying = false; copy.disabled = false;
    }
  }, 'quiet');
  return h('section', {class: 'campaign-clipboard-backup', 'aria-label': 'Copy campaign backup'},
    h('div', {class: 'button-row'}, copy, refresh),
    h('p', {class: 'fine'}, 'Includes all current inputs and unsaved work. No server connection is needed.'),
    feedback, manual);
}
