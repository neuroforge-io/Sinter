/** Read-only saved wording presentation; callers retain request and editor authority. */
import {h, button, notice, dateTime} from './ui.js';

export function savedReportPreviewView({id, render, onOpen, onPrevious, onNext, onClose}) {
  const element = h('section', {class: 'saved-report-preview', id,
    'aria-label': 'Saved copy preview'});
  const status = h('p', {class: 'saved-report-preview-status muted',
    role: 'status', 'aria-atomic': 'true', id: id + '-status'});
  const qualifications = h('div', {class: 'saved-report-qualifications',
    role: 'list', 'aria-label': 'Saved copy qualifications', id: id + '-qualifications'});
  const heading = h('h4', {tabIndex: -1,
    'aria-describedby': status.id + ' ' + qualifications.id}, 'Saved copy preview');
  const summary = h('summary', {}, 'Copy details');
  const identity = h('dl', {class: 'saved-report-identity'});
  const explanations = h('div', {class: 'saved-report-explanations'});
  const details = h('details', {class: 'saved-report-context'}, summary, identity, explanations);
  const wording = h('div', {class: 'saved-report-wording'});
  const focus = () => {
    heading.focus({preventScroll: true});
    heading.scrollIntoView({block: 'start', behavior: 'instant'});
  };
  const previous = button('Previous', () => { if (onPrevious()) focus(); }, 'quiet');
  previous.setAttribute('aria-label', 'Previous section');
  const next = button('Next', () => { if (onNext()) focus(); }, 'quiet');
  next.setAttribute('aria-label', 'Next section');
  const navigation = h('nav', {class: 'saved-report-sections',
    'aria-label': 'Saved wording sections'}, previous, next);
  const open = button('Open saved copy', () => onOpen(open), 'primary');
  const close = button('Close', onClose, 'quiet');
  close.setAttribute('aria-label', 'Close preview');
  element.append(h('div', {class: 'saved-report-preview-header'}, heading, close),
    status, qualifications, details, navigation, wording,
    h('div', {class: 'button-row saved-report-preview-actions'}, open));

  function clear() {
    status.textContent = '';
    qualifications.replaceChildren(); qualifications.hidden = true;
    identity.replaceChildren(); explanations.replaceChildren(); wording.replaceChildren();
    summary.textContent = 'Copy details'; details.open = false;
    navigation.hidden = true; previous.disabled = true; next.disabled = true; open.disabled = true;
  }
  clear();

  return {
    element, focus, clear,
    identify(report, reference) {
      summary.textContent = 'Copy details · ' + reference;
      identity.replaceChildren(
        h('dt', {}, 'Title'), h('dd', {}, report.title),
        h('dt', {}, 'Saved'), h('dd', {}, dateTime(report.created_at)),
        h('dt', {}, 'Full reference'), h('dd', {}, report.id));
    },
    show(state) {
      wording.replaceChildren(); qualifications.replaceChildren(); explanations.replaceChildren();
      const ready = state.kind === 'ready';
      open.disabled = !ready;
      previous.disabled = !ready || !state.previous;
      next.disabled = !ready || !state.wording.truncated;
      navigation.hidden = !ready || (!state.previous && !state.wording.truncated);
      qualifications.hidden = true;
      if (state.kind === 'loading') {
        status.textContent = 'Loading saved wording…';
        return;
      }
      if (state.kind === 'error') {
        status.textContent = '';
        wording.append(notice('Preview could not be loaded: ' + state.message
          + ' Your open draft is unchanged. Select Preview saved copy to try again.', 'error'));
        return;
      }
      const value = state.wording;
      status.textContent = (state.previous || value.truncated
        ? 'Section ' + (state.page + 1) + (value.truncated ? '' : ' (last)') + ' · '
        : 'Complete saved wording · ')
        + (value.edited ? 'Saved human edits' : 'Original saved document');
      const flag = (text, style = 'warm') => qualifications.append(
        h('span', {class: 'badge ' + style, role: 'listitem'}, text));
      if (value.incomplete) {
        flag('Incomplete model draft');
        explanations.append(notice('INCOMPLETE MODEL DRAFT — review the partial wording before using it.'));
      }
      if (value.stale) {
        flag('Stale review');
        explanations.append(notice('Review status: stale. Check this saved record before current use; editing its wording does not confirm the original evidence.'));
      }
      if (value.literal) {
        flag('Partly plain text', 'subtle');
        explanations.append(h('p', {class: 'fine'}, value.literalReason === 'unfinished-block'
          ? 'Formatting is unfinished, so the affected text is shown as plain text.'
          : 'Formatting extends beyond this section, so the affected text is shown as plain text.'));
      }
      qualifications.hidden = !qualifications.childElementCount;
      if (state.previous || value.truncated) explanations.append(h('p', {class: 'fine'},
        'Showing up to 2,400 characters at a time. Use the section controls for the rest of this saved document.'));
      explanations.append(h('p', {class: 'fine'},
        'Preview leaves your open draft unchanged. Open the saved copy to inspect its complete evidence.'));
      wording.append(...render(value));
    },
  };
}
