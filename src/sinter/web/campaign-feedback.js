/** Read clipped campaign feedback without changing the message or its actions. */
import {h, button} from './ui.js';

let sequence = 0;

export function campaignFeedback(fallbackFocus = () => null) {
  const feedback = h('div', {class: 'campaign-save-feedback',
    'aria-live': 'polite', tabindex: 0});
  let dialog = null, disposed = false;
  const expand = button('Read full message', open, 'quiet campaign-message-expand');
  expand.setAttribute('aria-haspopup', 'dialog');
  expand.hidden = true;
  const panel = h('div', {class: 'campaign-save-feedback-panel', hidden: true},
    feedback, expand);

  function update() {
    if (disposed) return;
    panel.hidden = !feedback.textContent.trim();
    expand.hidden = panel.hidden || feedback.scrollHeight <= feedback.clientHeight + 1;
  }

  function open() {
    if (disposed || dialog || !feedback.textContent.trim()) return;
    const id = `campaign-message-${++sequence}`;
    // Keep the original text as a snapshot. This view never retries or saves.
    const message = h('div', {class: 'campaign-message-text', role: 'region', tabindex: 0,
      'aria-label': 'Complete campaign message'}, feedback.textContent);
    const close = button('Close', () => opened.close(), 'quiet');
    const opened = h('dialog', {class: 'action-confirmation campaign-message-dialog',
      'aria-labelledby': `${id}-title`},
    h('div', {class: 'campaign-message-heading'},
      h('h2', {id: `${id}-title`}, 'Campaign message'), close),
    message,
    h('p', {class: 'fine'}, 'Message when opened. Close to check the latest status.'));
    dialog = opened;
    opened.addEventListener('close', () => {
      opened.remove();
      const current = dialog === opened;
      if (current) dialog = null;
      if (current && !disposed && panel.isConnected) {
        const target = panel.hidden ? fallbackFocus() : expand.hidden ? feedback : expand;
        target?.focus({preventScroll: true});
      }
    }, {once: true});
    try {
      document.body.append(opened);
      opened.showModal();
      message.focus({preventScroll: true});
    } catch {
      opened.remove(); dialog = null;
      // The existing focusable, scrollable message remains a keyboard fallback.
      feedback.focus({preventScroll: true});
    }
  }

  const mutations = new MutationObserver(update);
  mutations.observe(feedback, {childList: true, characterData: true, subtree: true});
  const resize = typeof ResizeObserver === 'function' ? new ResizeObserver(update) : null;
  resize?.observe(feedback);
  window.addEventListener('resize', update);
  return {feedback, panel, dispose() {
    disposed = true;
    mutations.disconnect(); resize?.disconnect();
    window.removeEventListener('resize', update);
    if (dialog) {
      if (dialog.open) dialog.close();
      dialog.remove(); dialog = null;
    }
  }};
}
