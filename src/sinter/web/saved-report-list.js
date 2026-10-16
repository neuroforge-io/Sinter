/** Saved-copy discovery is metadata-only until an explicit preview request. */
import {h, button, field, markdown, notice, dateTime} from './ui.js';
import {documentMarkdown} from './documents.js';

let sequence = 0;

export function savedReportMatches(report, value) {
  const query = value.trim().normalize('NFKC').toLowerCase();
  return !query || [report.title, report.id].some(value =>
    typeof value === 'string' && value.normalize('NFKC').toLowerCase().includes(query));
}

/** References help distinguish copies; full IDs remain the request authority. */
export function savedReportReference(id, reports) {
  let length = Math.min(8, id.length);
  while (length < id.length && reports.some(report => report.id !== id
      && report.id.startsWith(id.slice(0, length)))) length = Math.min(length + 4, id.length);
  return id.slice(0, length);
}

/** Bound rendered wording, keeping Unicode characters and incomplete warnings. */
export function savedReportWording(report, limit = 2400, start = 0) {
  if (!report || typeof report !== 'object' || Array.isArray(report)) {
    throw new Error('This saved copy is not a readable document.');
  }
  const value = documentMarkdown(report);
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error('This saved copy has no readable document wording. Its evidence remains saved.');
  }
  let text = '', count = 0, truncated = false;
  for (const character of value.slice(start)) {
    if (count === limit) { truncated = true; break; }
    text += character; count++;
  }
  return {markdown: text, truncated, characters: count, start, end: start + text.length,
    edited: typeof report.document_edits?.markdown === 'string',
    incomplete: Boolean(report.incomplete), stale: report.review_status === 'stale'};
}

/** Cancellation saves work; an independent generation check rejects late replies. */
export function savedReportPreview({load, active, changed}) {
  let generation = 0, controller = null, disposed = false;
  let retained = null, metadata = null, offsets = [0], page = 0;
  const close = () => {
    generation++; controller?.abort(); controller = null;
    retained = null; metadata = null; offsets = [0]; page = 0;
  };
  function showPage() {
    if (disposed || !active() || !retained) return false;
    const wording = savedReportWording(retained, 2400, offsets[page]);
    offsets[page + 1] = wording.end;
    changed({kind: 'ready', metadata, wording, page, previous: page > 0});
    return true;
  }
  return {
    close,
    dispose() { disposed = true; close(); },
    next() {
      if (!retained || offsets[page + 1] === undefined
          || !savedReportWording(retained, 2400, offsets[page]).truncated) return false;
      page++; return showPage();
    },
    previous() { if (!retained || page === 0) return false; page--; return showPage(); },
    async open(report) {
      close();
      if (disposed || !active()) return;
      const selected = generation, request = new AbortController();
      controller = request;
      metadata = {id: report.id, title: report.title, created_at: report.created_at};
      const current = () => !disposed && selected === generation && active();
      changed({kind: 'loading', metadata});
      try {
        const document = await load(metadata.id, request.signal);
        if (current()) { retained = document; showPage(); }
      } catch (error) {
        if (current()) { retained = null; changed({kind: 'error', metadata, message: error.message}); }
      } finally {
        if (selected === generation) controller = null;
      }
    },
  };
}

/** One bounded read-only preview; no report registry, save or model authority. */
export function savedReportList({load, onOpen, onDelete}) {
  const prefix = 'saved-report-list-' + ++sequence;
  const root = h('section', {class: 'saved-report-list non-print', 'aria-label': 'Saved drafts'});
  const filter = field('Find saved drafts', 'search', '',
    'Match a saved title or reference. This does not search inside documents.');
  const count = h('p', {class: 'muted', role: 'status', 'aria-atomic': 'true'});
  const cards = h('div', {class: 'stack'});
  const empty = h('p', {class: 'notice'});
  const panel = h('section', {class: 'saved-report-preview', id: prefix + '-preview',
    'aria-label': 'Saved copy preview'});
  const heading = h('h4', {tabIndex: -1}, 'Saved copy preview');
  const wording = h('div', {class: 'saved-report-wording'});
  const detail = h('p', {class: 'muted'});
  const previewStatus = h('p', {role: 'status'});
  const qualifications = h('div');
  const openPreview = button('Open saved copy', () => selected && onOpen(selected, openPreview), 'primary');
  const previous = button('Previous section', () => { if (preview.previous()) heading.focus({preventScroll: true}); }, 'quiet');
  const next = button('Next section', () => { if (preview.next()) heading.focus({preventScroll: true}); }, 'quiet');
  const closePreviewButton = button('Close preview', () => closePreview(true), 'quiet');
  panel.append(heading, detail, previewStatus, qualifications, wording,
    h('div', {class: 'button-row'}, previous, next, openPreview, closePreviewButton));
  const rows = new Map(), busy = new Set();
  let reports = [], selected = null, origin = null, disposed = false;

  const preview = savedReportPreview({
    load, active: () => !disposed && root.isConnected,
    changed(state) {
      if (selected?.id !== state.metadata.id) return;
      wording.replaceChildren(); qualifications.replaceChildren();
      openPreview.disabled = state.kind !== 'ready';
      previous.hidden = state.kind !== 'ready' || !state.previous;
      next.hidden = state.kind !== 'ready' || !state.wording.truncated;
      if (state.kind === 'loading') {
        previewStatus.textContent = 'Loading saved wording…';
      } else if (state.kind === 'error') {
        previewStatus.textContent = '';
        wording.append(notice('Preview could not be loaded: ' + state.message
          + ' Your open draft is unchanged. Select Preview saved copy to try again.', 'error'));
      } else {
        previewStatus.textContent = (state.previous || state.wording.truncated
          ? 'Section ' + (state.page + 1) + ' · ' : 'Complete saved wording · ')
          + (state.wording.edited ? 'Saved human edits' : 'Original saved document');
        if (state.wording.incomplete) qualifications.append(notice('INCOMPLETE MODEL DRAFT — review the partial wording before using it.'));
        if (state.wording.stale) qualifications.append(notice('Review status: stale. Check this saved record before current use; editing its wording does not confirm the original evidence.'));
        wording.append(markdown(state.wording.markdown));
        if (state.previous || state.wording.truncated) wording.append(h('p', {class: 'notice'},
          'Showing up to 2,400 characters at a time. Use the section controls for the rest of this saved document. '
          + 'Open the saved copy to inspect its complete evidence.'));
        if (document.activeElement === origin) heading.focus({preventScroll: true});
      }
    },
  });

  function closePreview(returnFocus = false) {
    preview.close();
    if (selected) rows.get(selected.id)?.preview.setAttribute('aria-expanded', 'false');
    selected = null;
    panel.remove(); wording.replaceChildren(); qualifications.replaceChildren(); previewStatus.textContent = '';
    if (returnFocus && origin?.isConnected && !origin.closest('[hidden]')) origin.focus({preventScroll: true});
    origin = null;
  }

  function showPreview(report, control) {
    if (busy.has(report.id)) return;
    closePreview();
    selected = report; origin = control;
    detail.textContent = report.title + ' · Saved ' + dateTime(report.created_at) + ' · Reference ' + savedReportReference(report.id, reports);
    control.setAttribute('aria-expanded', 'true');
    rows.get(report.id).card.append(panel);
    preview.open(report);
  }

  function applyFilter() {
    closePreview();
    let visible = 0;
    for (const report of reports) {
      const matches = savedReportMatches(report, filter.input.value);
      rows.get(report.id).card.hidden = !matches;
      if (matches) visible++;
    }
    const summary = visible + ' of ' + reports.length + ' saved ' + (reports.length === 1 ? 'draft' : 'drafts');
    if (count.textContent !== summary) count.textContent = summary;
    empty.hidden = visible !== 0;
    empty.textContent = reports.length
      ? 'No saved titles or references match. Clear the filter to see all saved drafts.'
      : 'Prepare a draft and choose Save to My workspace. Saved copies will appear here.';
    clear.hidden = !filter.input.value;
  }

  const clear = button('Clear filter', () => {
    filter.input.value = ''; applyFilter(); filter.input.focus({preventScroll: true});
  }, 'quiet');
  clear.hidden = true;
  filter.input.addEventListener('input', applyFilter);
  root.append(h('div', {class: 'saved-report-filter'}, filter.wrap, clear), count, empty, cards);

  return {
    element: root,
    update(next) {
      if (disposed) return;
      closePreview(); reports = next;
      const present = new Set(reports.map(report => report.id));
      for (const [id, row] of rows) if (!present.has(id)) { row.card.remove(); rows.delete(id); }
      let cursor = cards.firstElementChild;
      for (const report of reports) {
        let row = rows.get(report.id);
        if (!row) {
          const title = h('h3'), saved = h('p', {class: 'muted'}), reference = h('p', {class: 'saved-report-reference'});
          const control = button('Preview saved copy', () => showPreview(row.report, control), 'quiet');
          control.setAttribute('aria-expanded', 'false'); control.setAttribute('aria-controls', panel.id);
          const open = button('Open draft', () => onOpen(row.report, open));
          const remove = button('Delete saved copy', () => onDelete(row.report, remove), 'danger');
          const card = h('article', {class: 'card saved-report-card'}, title, saved, reference,
            h('div', {class: 'button-row'}, control, open, remove));
          row = {card, title, saved, reference, preview: control, open, remove}; rows.set(report.id, row);
        }
        row.report = report; row.title.textContent = report.title;
        for (const control of [row.preview, row.open, row.remove]) control.disabled = busy.has(report.id);
        row.saved.textContent = 'Saved ' + dateTime(report.created_at);
        row.reference.textContent = 'Reference ' + savedReportReference(report.id, reports);
        if (row.card !== cursor) cards.insertBefore(row.card, cursor);
        cursor = row.card.nextElementSibling;
      }
      applyFilter();
    },
    setBusy(id, value) {
      if (value) busy.add(id); else busy.delete(id);
      if (value && selected?.id === id) closePreview();
      const row = rows.get(id);
      if (row) for (const control of [row.preview, row.open, row.remove]) control.disabled = value;
    },
    dispose() {
      disposed = true; preview.dispose(); panel.remove(); wording.replaceChildren();
      rows.clear(); reports = []; selected = null; origin = null;
    },
  };
}
