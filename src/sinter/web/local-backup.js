import {h, button, field, notice} from './ui.js';

const backupResets = new WeakMap();

/** Call when replacing the working copy, before any old clipboard promise settles. */
export function resetLocalBackupControls(controls) {
  backupResets.get(controls)?.();
}

/** Preserve the working copy, without applying server admission or normalization. */
export function localBackupText(document, noun) {
  const text = JSON.stringify(document, null, 2);
  if (typeof text !== 'string') throw new TypeError(`A ${noun} working copy is required.`);
  return text;
}

/** Explicit local recovery: the callback reads the current editable campaign. */
export function localBackupControls(currentDocument, {noun, label,
  description = 'Includes all current inputs and unsaved work. No server connection is needed.',
  failureMessage = `Could not prepare backup text. Your ${noun} inputs are unchanged.`}) {
  if (typeof currentDocument !== 'function') throw new TypeError('A working-copy callback is required.');
  const feedback = h('div', {'aria-live': 'polite'});
  const recovery = field(`${label} backup text`, 'textarea', '',
    'Complete JSON captured by Copy backup text or Refresh backup text. Keep it somewhere safe; it can contain private inputs.',
    {readOnly: true, rows: 10, spellcheck: false});
  const select = button('Select backup text', () => {
    recovery.input.focus(); recovery.input.select();
  }, 'quiet');
  const manual = h('div', {hidden: true}, recovery.wrap, select);
  let copying = false, generation = 0;
  function capture() {
    // A failed new attempt also supersedes any older clipboard completion.
    generation++;
    const text = localBackupText(currentDocument(), noun);
    recovery.input.value = text; manual.hidden = false;
    return text;
  }
  function captureError() {
    feedback.replaceChildren(notice(failureMessage + ' Earlier backup text, if shown, has not been refreshed.', 'error'));
  }
  const refresh = button('Refresh backup text', () => {
    try {
      capture();
      feedback.replaceChildren(notice(`Backup text refreshed from your current inputs. Clipboard may contain an earlier snapshot; select the text below to copy manually. This does not save the ${noun} or create a file.`, 'warning'));
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
        feedback.replaceChildren(notice(`Backup text copied from your inputs at the time you clicked. Paste it into a text file to keep a copy. This does not save the ${noun} or create a file.`, 'success'));
      }
    } catch {
      if (generation === copiedGeneration) {
        feedback.replaceChildren(notice(`Clipboard unavailable. Select and copy the complete backup text below. This does not save the ${noun} or create a file.`, 'warning'));
        recovery.input.focus(); recovery.input.select();
      }
    } finally {
      copying = false; copy.disabled = false;
    }
  }, 'quiet');
  const controls = h('section', {class: 'local-clipboard-backup', 'aria-label': `Copy ${noun} backup`},
    h('div', {class: 'button-row'}, copy, refresh),
    h('p', {class: 'fine'}, description),
    feedback, manual);
  backupResets.set(controls, () => {
    const hadCapture = !manual.hidden || copying;
    generation++;
    recovery.input.value = ''; manual.hidden = true;
    feedback.replaceChildren(...(hadCapture ? [notice(
      `${label} changed. Earlier backup text cleared. Refresh or copy to capture current inputs. Clipboard may still contain an earlier snapshot. This does not save the ${noun} or create a file.`,
      'warning')] : []));
  });
  return controls;
}
