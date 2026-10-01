/** Local decisions use document controls; they never block browser automation. */
import {h, button} from './ui.js';

let sequence = 0, active = false;

/** The caller restores focus after releasing its own editor/transition lock. */
export function confirmAction({title, description, confirmLabel, cancelLabel = 'Cancel'}) {
  if (active) return Promise.reject(new Error('Finish the open decision before starting another.'));
  active = true;
  return new Promise((resolve, reject) => {
    const id = `confirm-action-${++sequence}`;
    let settled = false;
    const listeners = new AbortController();
    const finish = (approved, error) => {
      if (settled) return;
      settled = true; listeners.abort();
      if (dialog.open) dialog.close();
      dialog.remove(); active = false;
      if (error) reject(error); else resolve(approved);
    };
    const cancel = button(cancelLabel, () => finish(false), 'quiet');
    cancel.autofocus = true;
    const accept = button(confirmLabel, () => finish(true), 'primary');
    const dialog = h('dialog', {class: 'action-confirmation',
      'aria-labelledby': `${id}-title`, 'aria-describedby': `${id}-description`},
    h('h2', {id: `${id}-title`}, title),
    h('p', {id: `${id}-description`}, description),
    h('div', {class: 'button-row'}, cancel, accept));
    dialog.addEventListener('cancel', event => {
      event.preventDefault(); finish(false);
    }, {signal: listeners.signal});
    dialog.addEventListener('close', () => finish(false), {signal: listeners.signal});
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      event.preventDefault();
      const controls = [cancel, accept], at = controls.indexOf(document.activeElement);
      controls[(at + (event.shiftKey ? controls.length - 1 : 1)) % controls.length].focus();
    }, {signal: listeners.signal});
    window.addEventListener('pagehide', () => finish(false), {signal: listeners.signal});
    try {
      document.body.append(dialog); dialog.showModal(); cancel.focus();
    } catch {
      finish(false, new Error('The decision could not open. Your work is kept. Try again before replacing or removing it.'));
    }
  });
}
