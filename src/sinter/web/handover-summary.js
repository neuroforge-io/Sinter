/** Recipient-first, user-reviewed wording; never an inferred answer or commitment. */
import {h, button, field, selectField, check, notice, markdown} from './ui.js';
import {confirmAction} from './confirm-action.js';
import {trackReportForm, reportFormDraft, clearReportForm} from './report-drafts.js';
import {retainedQuestionContext} from './casebook-retained-context.js';
import {casebookQuestionEvidence} from './casebook-question-evidence.js';
import {reportCitationIndex, reportCitationMatcher} from './report-citations.js';

const MAX_ROWS = 12;
const FORM = 'handover-summary';
const MAX_TEXT = 1000;
const MARKER = '## Handover next steps\n';
let contextSequence = 0;
const OWNER_LABELS = {
  unknown: 'Owner type unknown; acceptance unconfirmed',
  unassigned: 'Unassigned; no owner has been recorded',
  role: 'Suggested role',
  person: 'Named person',
};
const PERIODS = new Set(['as_recorded', 'historical']);
const snapshot = report => JSON.stringify(report);
const literal = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replace(/[\\`*_{}\[\]#!|]/g, '\\$&');

export function handoverSummaryAvailable(report) {
  const original = report?.document_markdown;
  return report?.document_type === 'handover' && casebookQuestionEvidence(report) !== null
    && typeof original === 'string' && original.split(MARKER).length === 2;
}

function text(value, label, references, required = true) {
  if (typeof value !== 'string' || value.length > MAX_TEXT
      || /[\x00-\x1f\x7f-\x9f\u2028\u2029]/u.test(value)
      || Array.from(value).some(char => char.codePointAt(0) >= 0xd800 && char.codePointAt(0) <= 0xdfff)
      || (required && !value.trim())) throw new Error(`Enter ${label} as a single line of up to ${MAX_TEXT} characters.`);
  if (reportCitationMatcher(references)(value).length) {
    throw new Error('Choose evidence from a retained passage; do not type source IDs or Passage labels into summary wording.');
  }
  return value;
}

function target(value) {
  if (value === '') return 'Proposed target not supplied';
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)
      || Number(value.slice(0, 4)) === 0 || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) {
    throw new Error('Use a valid proposed target date, or leave it unknown.');
  }
  return `Proposed target ${value} (unconfirmed; not a funder deadline)`;
}

function owner(row, references) {
  if (!Object.hasOwn(OWNER_LABELS, row.ownerType)
      || !['unconfirmed', 'user_marked_accepted'].includes(row.ownerAcceptance)) {
    throw new Error('Choose an explicit owner type and acceptance state.');
  }
  const name = text(row.ownerName, 'the owner name or role', references, false);
  if (['unknown', 'unassigned'].includes(row.ownerType)) {
    if (name || row.ownerAcceptance !== 'unconfirmed') throw new Error('Unknown and unassigned owners cannot carry a name or accepted commitment.');
    return OWNER_LABELS[row.ownerType];
  }
  if (!name.trim()) throw new Error('Enter the suggested role or named person, without inventing a missing name.');
  if (row.ownerType === 'role' && row.ownerAcceptance !== 'unconfirmed') {
    throw new Error('A suggested role does not identify a person who has accepted.');
  }
  return `${OWNER_LABELS[row.ownerType]}: ${name}; ${row.ownerAcceptance === 'user_marked_accepted'
    ? 'acceptance marked by the user (not independently verified)' : 'acceptance unconfirmed'}`;
}

/** Validate a literal subspan of this question's exact retained passage. */
export async function handoverSummaryQuote(report, evidence) {
  if (!evidence || typeof evidence !== 'object' || Array.isArray(evidence)) throw new Error('Choose an exact retained passage.');
  const context = await retainedQuestionContext(report, evidence.questionIndex, evidence.excerptId);
  const {passages} = reportCitationIndex(report);
  const found = [...passages].find(([, row]) => row.excerpt_id === evidence.excerptId);
  if (!found || !Number.isSafeInteger(evidence.start) || !Number.isSafeInteger(evidence.end)
      || evidence.start < context.start || evidence.end > context.end || evidence.start >= evidence.end
      || typeof evidence.quote !== 'string'
      || Array.from(context.quote).slice(evidence.start - context.start, evidence.end - context.start).join('') !== evidence.quote) {
    throw new Error('The selected wording or Passage reference does not match this exact retained quotation. Nothing was substituted.');
  }
  return Object.freeze({label: found[0], sourceId: context.sourceId, excerptId: evidence.excerptId,
    start: evidence.start, end: evidence.end, quote: evidence.quote});
}

function quoted(value) {
  const longest = Math.max(0, ...(value.match(/`+/g) || []).map(run => run.length));
  const fence = '`'.repeat(Math.max(3, longest + 1));
  return `> ${fence}text\n> ${value.replace(/\r\n|[\r\n\v\f\x85\u2028\u2029]/g, '\n').replaceAll('\n', '\n> ')}\n> ${fence}`;
}

/** Return a detached edit; all original report evidence and review state stay intact. */
export async function compileHandoverSummary(report, rows) {
  if (!handoverSummaryAvailable(report)) throw new Error('Use a complete source-only handover with its original checklist and retained references.');
  if (!Array.isArray(rows) || !rows.length || rows.length > MAX_ROWS) throw new Error(`Review between 1 and ${MAX_ROWS} summary items.`);
  const original = structuredClone(report), entered = structuredClone(rows);
  const {references} = reportCitationIndex(original);
  const entries = [], quotations = [];
  for (const row of entered) {
    if (!row || typeof row !== 'object' || Array.isArray(row) || !PERIODS.has(row.period)) throw new Error('Choose as-recorded or historical wording for each item.');
    const item = text(row.item, 'an item', references), status = text(row.status, 'your recorded status or missing detail', references);
    const action = text(row.proposedAction, 'a proposed next step', references);
    const responsibility = owner(row, references), date = target(row.targetDate);
    const evidence = row.evidence === null ? null : await handoverSummaryQuote(original, row.evidence);
    if (evidence) quotations.push({item, position: entries.length + 1, ...evidence});
    const state = `${row.period === 'historical' ? 'Historical wording' : 'As recorded'}: ${status} · ${responsibility} · ${date}`;
    entries.push(`| ${literal(item)} | ${literal(state)} | ${literal(action)} | ${evidence ? evidence.label : 'Missing supporting record; answer remains unknown'} |`);
  }
  const lines = ['## At a glance',
    'Statuses and next steps below are user-entered for review. Next steps are proposals, not accepted commitments. A retained quotation establishes supplied wording, not independent verification.',
    ...(original.review_status === 'stale' ? ['**Review status: stale.** Review this saved record again before current use. Original evidence and historical wording remain unchanged; no current source was substituted.'] : []),
    ['| Item | Recorded status — user-entered | Next step — proposed | Evidence |',
      '| --- | --- | --- | --- |', ...entries].join('\n'),
    '**Evidence coverage:** this opening uses selected wording from this saved report. The unchanged checklist and selected evidence follow. This is not full supplied history; request the matching original project backup for unselected text. Later project or campaign changes are not included.'];
  if (quotations.length) {
    lines.push('', '### Wording selected for this summary');
    quotations.forEach(row => lines.push('', `**Summary item ${row.position}: ${literal(row.item)}** — ${row.label}`, quoted(row.quote)));
  }
  const base = original.document_markdown, at = base.indexOf(MARKER);
  const composed = base.slice(0, at) + lines.join('\n\n') + '\n\n' + base.slice(at);
  if (composed.length > 500000) throw new Error('This opening and retained handover exceed the 500,000-character edit limit. Your local work is unchanged; reduce summary scope or keep the originals in a separate project backup.');
  return {markdown: composed, openingMarkdown: lines.join('\n\n'), quotations, sourceSnapshot: snapshot(original)};
}

/** Explicit replacement is a separate decision from compilation. */
export async function applyHandoverSummary(report, compiled, {currentMarkdown, confirm, apply}) {
  if (snapshot(report) !== compiled.sourceSnapshot) throw new Error('This report changed during review. Your existing draft is kept; review the current retained snapshot before applying.');
  const before = currentMarkdown();
  if (report.document_edits) {
    if (!await confirm()) return false;
    if (snapshot(report) !== compiled.sourceSnapshot || currentMarkdown() !== before) throw new Error('The draft changed while the replacement decision was open. Your newer wording is kept.');
  }
  apply(compiled.markdown);
  return true;
}

/** Presentation only: a bounded, exact opening table; quoted source tables stay literal. */
export function presentHandoverSummaryTable(article, {report, currentMarkdown} = {}) {
  const children = [...article.children];
  const headings = children.filter(node => node.tagName === 'H2' && node.textContent === 'At a glance');
  if (headings.length !== 1) return false;
  const following = children.slice(children.indexOf(headings[0]) + 1);
  const boundary = following.findIndex(node => /^H[1-6]$/.test(node.tagName));
  const section = boundary === -1 ? following : following.slice(0, boundary);
  const wrappers = section.filter(node => node.className.split(' ').includes('table-scroll'));
  if (wrappers.length !== 1) return false;
  const wrapper = wrappers[0], table = wrapper.children[0];
  if (table?.tagName !== 'TABLE') return false;
  const head = [...table.children].find(node => node.tagName === 'THEAD');
  const body = [...table.children].find(node => node.tagName === 'TBODY');
  const labels = ['Item', 'Recorded status — user-entered', 'Next step — proposed', 'Evidence'];
  if (head?.children.length !== 1 || head.children[0].children.length !== labels.length
      || !labels.every((label, index) => head.children[0].children[index].textContent === label)
      || !body || body.children.length < 1 || body.children.length > MAX_ROWS
      || ![...body.children].every(row => row.tagName === 'TR' && row.children.length === labels.length
        && [...row.children].every(cell => cell.tagName === 'TD'))) return false;
  if (table.className.split(' ').includes('handover-opening-table')) return true;
  table.classList.add('handover-opening-table'); table.setAttribute('role', 'table');
  wrapper.classList.add('handover-opening-scroll');
  for (const row of body.children) {
    row.setAttribute('role', 'row');
    [...row.children].forEach((cell, index) => {
      cell.setAttribute('role', 'cell');
      cell.append(h('span', {class: 'handover-cell-label', 'aria-hidden': 'true'}, labels[index]));
    });
  }
  const prefix = report?.document_markdown?.split(MARKER)[0];
  const preamble = children.slice(0, children.indexOf(headings[0]));
  const cover = [report?.document_title || report?.title,
    'Source-only handover checklist — review before using.'];
  const details = report?.document_details;
  let knownCover = details && typeof details === 'object' && !Array.isArray(details);
  for (const [key, label] of [['recipient', 'Prepared for: '], ['signatory', 'Prepared by: '],
    ['sender_role', 'Role: '], ['organisation', ''], ['contact_details', 'Contact details: ']]) {
    const value = details?.[key];
    if (typeof value !== 'string' || /[\r\n\v\f\x85\u2028\u2029]/u.test(value)) knownCover = false;
    else if (value) cover.push(label + value);
  }
  // Only the exact retained generated cover is condensed. A user's added or
  // changed preamble, extra warning, quote, heading or source table stays visible.
  if (handoverSummaryAvailable(report) && !report.demo
      && knownCover && preamble.length === cover.length
      && preamble.every((node, index) => node.textContent === cover[index])
      && typeof prefix === 'string' && typeof currentMarkdown === 'string'
      && currentMarkdown.startsWith(prefix + '## At a glance\n')
      && preamble[0].tagName === 'H1'
      && preamble[1].tagName === 'P'
      && preamble.slice(1).every(node => node.tagName === 'P')) {
    const id = `handover-context-${++contextSequence}`;
    const context = h('div', {id, class: 'handover-context-content', hidden: true,
      role: 'region', 'aria-label': 'Audience and document context'});
    const toggle = button('Audience and document context', () => {
      context.hidden = !context.hidden;
      toggle.setAttribute('aria-expanded', String(!context.hidden));
    }, 'quiet handover-context-toggle non-print');
    toggle.setAttribute('aria-controls', id); toggle.setAttribute('aria-expanded', 'false');
    const opening = h('section', {class: 'handover-reading-opening', 'aria-label': 'Reviewed handover opening'});
    article.insertBefore(opening, preamble[0]);
    for (const node of preamble) { node.remove(); context.append(node); }
    opening.append(context, h('p', {class: 'handover-source-label non-print'},
      'Source-only handover · review before using'));
    for (const node of [headings[0], ...section.slice(0, section.indexOf(wrapper) + 1)]) {
      node.remove(); opening.append(node);
    }
    opening.append(toggle); article.classList.add('handover-reading-document');
  }
  return true;
}

/** No source extraction, auto-answer, provider call or persistent schema extension. */
export function handoverSummaryEditor(report, {actions, onDraftChange = () => {}}) {
  if (!handoverSummaryAvailable(report)) return null;
  const panel = h('details', {class: 'handover-summary non-print'}, h('summary', {}, 'Write handover opening'));
  const instructions = h('p', {class: 'fine'}, 'Enter the recorded status and a proposed next step. Select literal supporting wording below; missing answers stay unknown. Applying replaces the edited document only after your approval. Save to My workspace afterward. Unapplied rows stay in this browser session’s unsaved drafts and trigger the existing quit warning. After applying, rows become ordinary editable document text; they are not a separate saved form.');
  const cards = h('div', {class: 'stack'}), feedback = h('div', {'aria-live': 'polite'});
  const rows = [], evidenceRows = casebookQuestionEvidence(report);
  const options = [['', 'Missing supporting record — no citation']];
  const choices = new Map();
  for (const question of evidenceRows) for (const passage of question.matches) {
    if (!passage.available || !/^Passage \d+$/.test(passage.label)) continue;
    const key = `${question.position - 1}:${passage.excerptId}`;
    if (!choices.has(key)) {
      choices.set(key, {questionIndex: question.position - 1, excerptId: passage.excerptId});
      options.push([key, `Question ${question.position} · ${passage.label} · ${passage.sourceTitle || 'Retained source'}`]);
    }
  }
  let busy = false, reviewed, reviewedRows;
  const seed = reportFormDraft(report, FORM);
  const remember = () => { trackReportForm(report, FORM, {rows: rows.map(row => row.capture()), open: panel.open}); onDraftChange(); };
  const invalidate = () => { reviewed = undefined; reviewedRows = undefined; apply.hidden = true; };
  const changed = () => { rows.forEach(row => row.refresh()); invalidate(); remember(); };
  const short = value => Array.from(value.trim()).length > 100 ? Array.from(value.trim()).slice(0, 100).join('') + '…' : value.trim();
  function addRow(saved = {}, edited = true) {
    if (rows.length >= MAX_ROWS || busy) return;
    const legend = h('legend', {}, `Summary item ${rows.length + 1}`);
    const heading = h('span', {class: 'summary-item-heading'}), detail = h('span', {class: 'summary-item-detail'});
    const row = h('details', {class: 'handover-summary-item', open: edited || (typeof saved.open === 'boolean' ? saved.open : rows.length === 0)},
      h('summary', {}, heading, detail));
    const fields = h('fieldset', {class: 'stack'}, legend);
    const item = field('Item', 'text', saved.item || '', '', {maxLength: MAX_TEXT});
    const fromQuestion = selectField('Retained question', [['', 'Choose a question'],
      ...evidenceRows.filter(question => question.questionAvailable)
        .map(question => [String(question.position), question.question])]);
    fromQuestion.input.addEventListener('change', event => event.stopPropagation());
    const questionFeedback = h('p', {class: 'fine', role: 'status'});
    const useQuestion = button('Use question as item', () => {
      const question = evidenceRows.find(row => String(row.position) === fromQuestion.input.value && row.questionAvailable);
      if (!question) { questionFeedback.textContent = 'Choose a retained question first.'; return; }
      if (item.input.value) { questionFeedback.textContent = 'Your Item wording is kept. Clear it explicitly before using a question.'; item.input.focus(); return; }
      try {
        text(question.question, 'the item', reportCitationIndex(report).references);
        item.input.value = question.question; changed(); status.input.focus();
        questionFeedback.textContent = 'Exact question copied. Enter the recorded status and proposed next step yourself.';
      } catch (error) { questionFeedback.textContent = error.message; }
    }, 'quiet');
    const questionStart = h('details', {class: 'handover-question-start'}, h('summary', {}, 'Start from a question'),
      fromQuestion.wrap, useQuestion, questionFeedback);
    const status = field('Recorded status or missing detail — your wording', 'text', saved.status || '', '', {maxLength: MAX_TEXT});
    const action = field('Next step — proposed, not accepted', 'text', saved.proposedAction || '', '', {maxLength: MAX_TEXT});
    const period = selectField('When this wording applies', [['as_recorded', 'As recorded — current status not independently verified'], ['historical', 'Historical wording — retain without making it current']], saved.period || 'as_recorded');
    const ownerType = selectField('Recorded owner type', Object.entries(OWNER_LABELS), saved.ownerType || 'unknown');
    const ownerName = field('Named person or suggested role', 'text', saved.ownerName || '', 'Leave blank when unknown or unassigned.', {maxLength: MAX_TEXT});
    const accepted = check('I mark that this named person accepted — my record, not independently verified', saved.ownerAcceptance === 'user_marked_accepted');
    const date = field('Proposed target date — unconfirmed', 'date', saved.targetDate || '', 'This does not become a funder deadline. Leave blank when not supplied.');
    const rowOptions = saved.sourceChoice && !choices.has(saved.sourceChoice)
      ? [...options, [saved.sourceChoice, 'Retained choice unavailable — review required']] : options;
    const source = selectField('Supporting wording from this saved report', rowOptions, saved.sourceChoice || '');
    const original = field('Retained passage — select literal wording to use', 'textarea', '', 'Select the exact sentence or span, then choose Use selected wording. No neighbouring text or current source is substituted.', {rows: 5, readOnly: true});
    original.wrap.hidden = true;
    const selected = h('pre', {class: 'plain-wrap'}), quoteStatus = h('p', {class: 'fine'});
    let passage = saved.passage, binding = saved.evidence || null;
    if (passage) { original.input.value = passage.quote; original.wrap.hidden = false; }
    if (binding) selected.textContent = binding.quote;
    if (saved.sourceChoice) quoteStatus.textContent = 'Unapplied wording restored; its exact source binding will be rechecked before applying.';
    const pick = button('Use selected wording', () => {
      if (!passage || !choices.has(source.input.value)) { quoteStatus.textContent = 'This retained choice is unavailable. Keep the old wording and inspect its matching backup.'; return; }
      const start = original.input.selectionStart, end = original.input.selectionEnd;
      if (start === end) { quoteStatus.textContent = 'Select literal wording in the retained passage first.'; return; }
      binding = {...choices.get(source.input.value), start: passage.start + Array.from(passage.quote.slice(0, start)).length,
        end: passage.start + Array.from(passage.quote.slice(0, end)).length, quote: passage.quote.slice(start, end)};
      changed(); selected.textContent = binding.quote;
      quoteStatus.textContent = 'Exact selected wording is shown above. Status and next step remain your interpretation.';
    }, 'quiet');
    pick.hidden = !passage;
    source.input.addEventListener('change', async () => {
      const choice = source.input.value; binding = null; passage = null; changed(); selected.textContent = ''; original.input.value = '';
      original.wrap.hidden = pick.hidden = true;
      if (!choice) { quoteStatus.textContent = 'Missing supporting record; no citation will be created.'; return; }
      try {
        const result = await retainedQuestionContext(report, choices.get(choice).questionIndex, choices.get(choice).excerptId);
        if (source.input.value !== choice) return;
        passage = result; remember(); original.input.value = result.quote; original.wrap.hidden = pick.hidden = false;
        quoteStatus.textContent = 'Select the literal wording you reviewed. Selecting a passage does not select an answer.';
      } catch (error) { quoteStatus.textContent = error.message; }
    });
    const capture = () => ({item: item.input.value, status: status.input.value, proposedAction: action.input.value,
      period: period.input.value, ownerType: ownerType.input.value, ownerName: ownerName.input.value,
      ownerAcceptance: accepted.input.checked ? 'user_marked_accepted' : 'unconfirmed', targetDate: date.input.value,
      sourceChoice: source.input.value, passage, evidence: binding, open: row.open});
    const refresh = () => {
      heading.textContent = `${legend.textContent} — ${short(item.input.value) || 'Untitled item'}`;
      detail.textContent = `${short(status.input.value) || 'Status not entered'} · ${binding ? 'Literal wording selected' : source.input.value ? 'Exact wording still needed' : 'No supporting record; no citation'}`;
    };
    const entry = {capture, legend, row, refresh, read: () => {
      if (source.input.value && !binding) throw new Error('Choose the exact supporting wording for every selected passage.');
      const {open, ...value} = capture();
      return value;
    }};
    rows.push(entry);
    const remove = button('Remove this summary item', () => {
      if (busy) return;
      rows.splice(rows.indexOf(entry), 1); row.remove();
      rows.forEach((item, index) => { item.legend.textContent = `Summary item ${index + 1}`; item.refresh(); });
      if (rows.length) changed();
      else { addRow({}, false); clearReportForm(report, FORM); invalidate(); onDraftChange(); }
    }, 'quiet');
    const responsibilityCaption = h('summary');
    const responsibility = h('details', {class: 'handover-responsibility'}, responsibilityCaption,
      period.wrap, ownerType.wrap, ownerName.wrap, accepted.wrap, date.wrap);
    const refreshResponsibility = () => {
      responsibilityCaption.textContent = `${OWNER_LABELS[ownerType.input.value] || 'Review owner type'} · ${date.input.value ? 'Proposed target ' + date.input.value + ' (unconfirmed)' : 'Target not supplied'}`;
    };
    responsibility.addEventListener('input', refreshResponsibility);
    responsibility.addEventListener('change', refreshResponsibility); refreshResponsibility();
    fields.append(item.wrap, questionStart, status.wrap, action.wrap,
      source.wrap, original.wrap, pick, selected, quoteStatus, responsibility, remove);
    row.append(fields); cards.append(row); refresh();
    row.addEventListener('toggle', () => { if (reportFormDraft(report, FORM)) remember(); });
    add.disabled = rows.length >= MAX_ROWS;
    if (edited) {
      rows.forEach(existing => { if (existing !== entry) existing.row.open = false; });
      changed(); item.input.focus();
    }
  }
  const add = button('Add summary item', () => addRow(), 'quiet');
  const preview = button('Preview opening summary', async () => {
    if (busy || !actions.canUseDocument('reviewing an opening summary')) return;
    busy = true; preview.disabled = add.disabled = true;
    try {
      const entered = rows.map(row => row.read()), before = snapshot(entered);
      const compiled = await compileHandoverSummary(report, entered);
      if (before !== snapshot(rows.map(row => row.read()))) throw new Error('The summary changed during preparation. Review your current wording again.');
      reviewed = compiled; reviewedRows = before;
      const document = markdown(compiled.openingMarkdown); document.classList.add('handover-summary-document');
      const responsive = presentHandoverSummaryTable(document);
      feedback.replaceChildren(h('h3', {}, 'Opening summary preview'),
        ...(responsive ? [] : [h('p', {class: 'handover-summary-scroll-hint fine'}, 'On a small screen, scroll the summary table sideways to review every column.')]), document);
      apply.hidden = false;
    } catch (error) { invalidate(); feedback.replaceChildren(notice(error.message, 'error')); }
    finally { busy = false; preview.disabled = false; add.disabled = rows.length >= MAX_ROWS; }
  }, 'quiet');
  const apply = button('Apply reviewed opening summary', async () => {
    if (busy || !reviewed || !actions.canUseDocument('applying an opening summary')) return;
    busy = true; apply.disabled = preview.disabled = add.disabled = true;
    try {
      if (reviewedRows !== snapshot(rows.map(row => row.read()))) throw new Error('The summary changed. Preview the current wording before applying.');
      const compiled = reviewed, acceptedRows = reviewedRows;
      const applied = await applyHandoverSummary(report, compiled, {
        currentMarkdown: actions.currentMarkdown,
        confirm: async () => {
          const approved = await confirmAction({title: 'Replace the edited handover?', description: 'The new opening summary will be assembled with the retained original handover. Existing applied draft edits will be replaced. Cancel keeps them.', confirmLabel: 'Replace edited draft'});
          if (approved && acceptedRows !== snapshot(rows.map(row => row.read()))) throw new Error('The summary changed while the replacement decision was open. Your current rows are kept.');
          return approved;
        },
        apply: actions.applyMarkdown,
      });
      if (applied) { feedback.replaceChildren(notice('Opening summary applied. Save to My workspace to keep it. Original evidence and historical wording are retained.', 'success')); panel.open = false; clearReportForm(report, FORM); invalidate(); actions.feedback?.replaceChildren(); onDraftChange(); }
      else feedback.append(notice('Your existing edited draft is kept. Summary rows remain in this editor.'));
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    finally { busy = false; apply.disabled = preview.disabled = false; add.disabled = rows.length >= MAX_ROWS; }
  }, 'primary');
  apply.hidden = true;
  const discard = button('Discard unapplied summary rows', async () => {
    if (busy) return;
    const before = snapshot(reportFormDraft(report, FORM));
    if (before === undefined) return;
    busy = true;
    try {
      const approved = await confirmAction({title: 'Discard unapplied summary rows?', description: 'This removes this editor’s unapplied rows only. Your applied draft and original evidence stay intact.', confirmLabel: 'Discard summary rows'});
      if (!approved) return;
      if (before !== snapshot(reportFormDraft(report, FORM))) throw new Error('The summary changed while the decision was open. Your rows are kept.');
      clearReportForm(report, FORM); rows.length = 0; cards.replaceChildren(); invalidate(); busy = false;
      addRow({}, false); onDraftChange(); feedback.replaceChildren(notice('Unapplied summary rows discarded. Your applied draft is unchanged.'));
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    finally { busy = false; }
  }, 'quiet');
  panel.addEventListener('input', changed);
  panel.addEventListener('change', changed);
  panel.addEventListener('toggle', () => { if (reportFormDraft(report, FORM)) remember(); });
  panel.append(instructions, cards, h('div', {class: 'button-row'}, add, preview, discard), feedback,
    h('div', {class: 'button-row handover-summary-review-actions'}, apply));
  if (seed?.rows?.length) { for (const saved of seed.rows) addRow(saved, false); panel.open = true; }
  else addRow({}, false);
  return panel;
}
