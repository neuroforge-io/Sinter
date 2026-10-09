/** Compact local feedback without discarding messages or replaying actions. */
import {h, button} from './ui.js';

let sequence = 0;

export function campaignFeedbackPresentation(text, severity = '') {
  if (!String(text || '').trim()) return {kind: 'empty', summary: ''};
  const uncertain = /save may have finished|did not receive confirmation|\bunconfirmed (?:request|save|outcome)\b/i.test(text);
  const partial = /\bincomplete\b|\bpartial (?:answer|result|work)\b/i.test(text);
  const kind = severity === 'error' ? 'error'
    : severity === 'warning' || uncertain || partial ? 'warning' : 'routine';
  return {kind, summary: uncertain ? 'Outcome unconfirmed — read recovery details.'
    : partial ? 'Read the partial-work recovery details before continuing.'
      : kind === 'error' ? 'Needs attention — read the full message.'
        : kind === 'warning' ? 'Review this message before continuing.' : ''};
}

export function campaignFeedback(fallbackFocus = () => null) {
  const feedback = h('div', {class: 'campaign-save-feedback',
    'aria-live': 'polite', tabindex: 0});
  const summary = h('p', {class: 'campaign-message-summary', hidden: true});
  const announcement = h('div', {class: 'sr-only campaign-message-announcement',
    'aria-live': 'polite', 'aria-atomic': 'true'});
  let dialog = null, disposed = false, inlineExpanded = false, previousText = '';
  const expand = button('Read full message', open, 'quiet campaign-message-expand');
  expand.setAttribute('aria-haspopup', 'dialog');
  expand.hidden = true;
  const panel = h('div', {class: 'campaign-save-feedback-panel', hidden: true},
    summary, feedback, expand, announcement);

  function update() {
    if (disposed) return;
    const text = feedback.textContent;
    if (text !== previousText) { inlineExpanded = false; previousText = text; }
    const severity = feedback.querySelector('.notice.error') ? 'error'
      : feedback.querySelector('.notice.warning') ? 'warning' : '';
    const state = campaignFeedbackPresentation(text, severity);
    panel.hidden = state.kind === 'empty';
    panel.dataset.kind = state.kind;
    panel.dataset.inlineExpanded = String(inlineExpanded);
    feedback.hidden = state.kind === 'routine' && !inlineExpanded;
    summary.hidden = !state.summary;
    summary.textContent = state.summary;
    // Hidden routine DOM is retained verbatim; announce its actual new content.
    const routineAnnouncement = state.kind === 'routine' ? text : '';
    if (announcement.textContent !== routineAnnouncement) {
      announcement.textContent = routineAnnouncement;
    }
    expand.hidden = panel.hidden;
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
      // A missing dialog API must not make compact routine feedback unreadable.
      inlineExpanded = true; update();
      feedback.focus({preventScroll: true});
    }
  }

  const mutations = new MutationObserver(update);
  mutations.observe(feedback, {childList: true, characterData: true, subtree: true,
    attributes: true, attributeFilter: ['class']});
  const resize = typeof ResizeObserver === 'function' ? new ResizeObserver(update) : null;
  resize?.observe(feedback);
  window.addEventListener('resize', update);
  return {feedback, panel, dispose() {
    disposed = true;
    mutations.disconnect(); resize?.disconnect();
    window.removeEventListener('resize', update);
    if (dialog) {
      const closing = dialog; dialog = null;
      if (closing.open) closing.close();
      closing.remove();
    }
  }};
}
