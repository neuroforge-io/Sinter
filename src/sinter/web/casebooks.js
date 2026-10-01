/** Revisioned, local casebooks. No automatic upload, URL fetching or draft approval. */
import {h, field, selectField, check, button, notice, download, dateTime} from './ui.js';
import {request, waitForJob} from './api.js';
import {renderReport} from './reports.js';
import {senderFields} from './profile.js';
import {hasPendingSource, PENDING_SOURCE_MESSAGE} from './casebook-drafts.js';
import {casebookBackupControls} from './casebook-backup.js';
import {gardenGuide, GARDEN_PRACTICE} from './garden-practice.js';
import {HANDOVER_EVIDENCE_OPTIONS, handoverEvidenceMode,
  handoverExportNotice} from './casebook-handover.js';
import {casebookSchema, explicitScopeClear, questionScopeIssue, questionScopeControls,
  casebookDraftContext, questionLines} from './casebook-scope.js';
import {sourceFilterStates} from './casebook-source-filter.js';

// Only this scope-aware caller opts in. A cached older page using the current
// shared request helper must still be refused before it receives scoped work.
const casebookRequest = (path, options = {}) => request(path, {...options,
  headers: {'X-Sinter-Casebook-Schema': 'sinter-casebook/v2'}});

const example = () => ({schema: 'sinter-casebook/v1', title: 'Fictional P&C community evening',
  questions: 'Has the hall booking been confirmed?\nWhat access arrangements need checking?\nWho agreed to organise the volunteer roster?\nWhat is the insurance excess?',
  documents: [
    {title: 'Initial planning note (fictional)', date: '2026-08-03', content: 'We hoped to use the hall on Friday. Pat offered to ask about the hall booking. No booking has been confirmed. We need accessible entry and hearing support.'},
    {title: 'Venue reply (fictional)', date: '2026-08-05', content: 'The hall booking is provisional only. Please confirm the accessible entrance and hearing support with the venue coordinator before advertising.'},
    {title: 'Volunteer discussion (fictional)', content: 'Morgan suggested a shared volunteer roster. No one agreed to own the roster yet. We should ask at the next meeting.'}
  ]});

export async function casebooksPage({setBusy, remember, seed = {}, onOpenGarden} = {}) {
  const {settings} = await request('/api/settings');
  const sender = senderFields(seed.book || {}, settings);
  const recipient = field('Recipient or audience', 'text', seed.book?.recipient || '', '', {maxLength: 200});
  let savedId = seed.savedId || null, revision = seed.revision || null;
  let bookDirty = Boolean(seed.dirty);
  let preparedReport = seed.report || null;
  let practice = seed.practice || null;
  const practiceGuide = onOpenGarden ? gardenGuide('casebooks', onOpenGarden) : h('div');
  practiceGuide.hidden = practice !== GARDEN_PRACTICE;
  let docs = [...(seed.book?.documents || [])], busy = false, activeJob = null;
  let questionScopes = structuredClone(seed.book?.question_scopes || []);
  let scopesExplicitlyCleared = explicitScopeClear(seed.book);
  let scopeViews = sourceFilterStates(questionLines(seed.book?.questions || ''), seed.scopeViews);
  const title = field('Project name', 'text', seed.book?.title || '', 'For example: school garden proposal or volunteer handover.', {maxLength: 200});
  const questions = field('What do you need to find out?', 'textarea', seed.book?.questions || '', 'One question per line, up to 20. Missing answers stay visible.', {maxLength: 12000, rows: 5});
  const format = selectField('Prepare a', [['brief', 'Briefing note'], ['enquiry', 'Enquiry letter'], ['agenda', 'Agenda item'], ['handover', 'Volunteer handover']], seed.book?.document_type || 'brief');
  const handoverEvidence = selectField('Evidence in source-only handover', HANDOVER_EVIDENCE_OPTIONS,
    handoverEvidenceMode(seed.book), 'Word exports the document text you review or edit. The appendix carries selected passages, not all original sources; it does not establish answers.');
  const showHandoverEvidence = () => { handoverEvidence.wrap.hidden = format.input.value !== 'handover'; };
  showHandoverEvidence();
  const status = h('div', {'aria-live': 'polite'}), output = h('div', {class: 'stack', id: 'casebook-output'}), sources = h('div', {class: 'stack', style: 'grid-template-columns:minmax(0,1fr)'});
  const catalogue = h('div', {class: 'casebook-shelf'}), totals = h('p', {class: 'muted'});
  const saveState = h('p', {class: 'muted', role: 'status', 'aria-label': 'Project save state'});
  const stop = button('Stop this task', async () => {
    if (!activeJob) return;
    stop.disabled = true;
    try {
      await request('/api/jobs/cancel', {data: {id: activeJob}});
      status.replaceChildren(notice('Stop requested. Waiting for the current bounded operation to finish; your saved project is unchanged.'));
    } catch (error) { stop.disabled = false; status.replaceChildren(notice(error.message + ' Check Recent activity before starting another task.', 'error')); }
  }, 'quiet');
  stop.hidden = true;
  const name = field('Source title', 'text', seed.pendingSource?.title || '', 'Give each note or reference an identifiable name.', {maxLength: 300});
  const contents = field('Paste a note, policy or reference', 'textarea', seed.pendingSource?.content || '', 'Original wording is preserved. Links are not followed automatically.', {maxLength: 200000, rows: 5});
  const sourceDate = field('Source date (optional)', 'date', seed.pendingSource?.date || ''), sourceURL = field('Source link (optional)', 'url', seed.pendingSource?.url || '', 'Only add a link you trust. The text above is the actual evidence.');
  const upload = field('Add text files', 'file', '', 'TXT, Markdown, UTF-8 notes or code. Up to 300 documents and 2 million characters. No PDF/DOCX extraction.', {multiple: true});
  const backup = field('Restore a casebook backup', 'file', '', 'Opens as a new unsaved project; existing casebooks are not overwritten.', {accept: '.json'});
  const editor = h('fieldset', {class: 'casebook-editor'});
  const scopeContents = h('div');
  const scopePanel = h('details', {class: 'card'},
    h('summary', {}, 'Choose sources for each question'), scopeContents);
  const value = () => ({schema: casebookSchema(questionScopes), title: title.input.value, questions: questions.input.value,
    document_type: format.input.value, recipient: recipient.input.value, ...sender.values(), documents: docs,
    ...(questionScopes.length || scopesExplicitlyCleared
      ? {question_scopes: structuredClone(questionScopes)} : {}),
    ...(handoverEvidence.input.value === 'selected_appendix' ? {handover_evidence: 'selected_appendix'} : {})});
  const pendingSource = () => ({title: name.input.value, content: contents.input.value,
    date: sourceDate.input.value, url: sourceURL.input.value});
  const sourcePanel = h('details', {class: 'card', open: !docs.length || hasPendingSource(pendingSource())});
  const pendingNotice = h('p', {class: 'muted', role: 'status'});
  const pendingMessage = () => hasPendingSource(pendingSource())
    ? 'This source is waiting to be added. Its text is kept while you move between pages.' : '';
  pendingNotice.textContent = pendingMessage();
  function updateSaveState(pending = pendingSource()) {
    const pendingExists = hasPendingSource(pending);
    const message = pendingExists
      ? 'Pending source is not added or saved. Add this source or clear it before saving.'
      : bookDirty
        ? 'Unsaved project changes.' + (savedId ? ` Based on revision ${revision}.` : '')
          + ' Use Save project to keep these inputs.'
        : savedId ? `Project inputs saved at revision ${revision}.`
          : 'Project not saved yet. Use Save project to keep these inputs.';
    if (saveState.textContent !== message) saveState.textContent = message;
    if (bookDirty || pendingExists) status.querySelector('[data-casebook-save-success]')?.remove();
  }
  function rememberCurrent() {
    const pending = pendingSource();
    pendingNotice.textContent = pendingMessage(); updateSaveState(pending);
    remember?.('casebooks', {book: value(), savedId, revision, dirty: bookDirty, pendingSource: pending, practice, report: preparedReport,
      scopeViews: structuredClone(scopeViews)},
      {dirty: bookDirty || hasPendingSource(pending)});
  }
  function clearPending() {
    name.input.value = ''; contents.input.value = ''; sourceDate.input.value = ''; sourceURL.input.value = '';
    rememberCurrent();
  }
  function admitPending() {
    if (!hasPendingSource(pendingSource())) return;
    sourcePanel.open = true; contents.input.focus();
    throw new Error(PENDING_SOURCE_MESSAGE);
  }
  function canReplace() {
    return !(bookDirty || hasPendingSource(pendingSource()))
      || confirm('Replace the unsaved editor? Save your project and add or clear the pending source first if you need to keep it.');
  }
  function changed({dirty = true} = {}) {
    preparedReport = null; bookDirty = dirty; rememberCurrent();
    output.replaceChildren();
  }
  function drawSources() {
    sources.replaceChildren(); totals.textContent = `${docs.length} documents / ${docs.reduce((n, row) => n + row.content.length, 0).toLocaleString()} characters, stored locally only when you save.`;
    for (const [index, row] of docs.entries()) {
      const details = h('details', {class: 'source'}), preview = h('div');
      details.append(h('summary', {}, row.title), h('p', {class: 'muted'}, `${row.content.length.toLocaleString()} characters / source date: ${row.date || 'unknown'}`), preview,
        button('Remove source', () => { docs.splice(index, 1); changed(); drawSources(); }, 'quiet'));
      details.addEventListener('toggle', () => { if (details.open && !preview.firstChild) preview.append(h('pre', {class: 'plain-wrap'}, row.content)); });
      sources.append(details);
    }
    drawScopes();
  }
  function drawScopes() {
    scopeContents.replaceChildren(questionScopeControls({text: questions.input.value,
      scopes: questionScopes, documents: docs, viewState: scopeViews,
      onViewChange: views => { scopeViews = views; rememberCurrent(); },
      onChange: scopes => {
        scopesExplicitlyCleared = scopes.length ? false
          : scopesExplicitlyCleared || questionScopes.length > 0;
        questionScopes = scopes; changed(); }}));
  }
  function load(book, id = null, rev = null) {
    scopeViews = id && id === savedId ? sourceFilterStates(questionLines(book.questions || ''), scopeViews) : [];
    practice = null; practiceGuide.hidden = true;
    docs = book.documents; title.input.value = book.title; questions.input.value = book.questions || '';
    questionScopes = structuredClone(book.question_scopes || []);
    scopesExplicitlyCleared = explicitScopeClear(book);
    format.input.value = book.document_type || 'brief';
    handoverEvidence.input.value = handoverEvidenceMode(book); showHandoverEvidence();
    recipient.input.value = book.recipient || '';
    for (const [key, entry] of Object.entries(sender.entries)) entry.input.value = book[key] ?? '';
    savedId = id; revision = rev;
    clearPending(); sourcePanel.open = !docs.length;
    sender.panel.dispatchEvent(new Event('input', {bubbles: true}));
    changed({dirty: !id}); drawSources();
  }
  async function refresh() {
    const result = await casebookRequest('/api/casebooks'); catalogue.replaceChildren();
    if (!result.casebooks.length) catalogue.append(h('p', {class: 'muted'}, 'Your saved projects will appear here. Start with an example or add your own notes.'));
    for (const row of result.casebooks) catalogue.append(h('article', {class: 'casebook-tile'},
      h('strong', {}, row.title), h('small', {class: 'muted'}, `Revision ${row.revision} / ${dateTime(row.updated_at)}`),
      button('Open project', async () => {
        if (busy) return;
        if (!canReplace()) return;
        try { const result = await casebookRequest('/api/casebooks/' + row.id); load(result.document, result.id, result.revision); status.replaceChildren(notice('Opened locally. Originals remain available below.')); }
        catch (error) { status.replaceChildren(notice(error.message, 'error')); }
      }, 'quiet')));
  }
  async function save() {
    admitPending();
    const scopeProblem = questionScopeIssue(questions.input.value, questionScopes, docs);
    if (scopeProblem) { scopePanel.open = true; scopeContents.scrollIntoView({block: 'center'}); throw new Error(scopeProblem); }
    const result = await casebookRequest('/api/casebooks/save', {data: {document: value(), id: savedId, revision}});
    savedId = result.id; revision = result.revision; docs = result.document.documents;
    questionScopes = structuredClone(result.document.question_scopes || []);
    scopesExplicitlyCleared = false;
    bookDirty = false; rememberCurrent();
    await refresh(); drawSources(); return result;
  }
  function lock(active) { busy = active; editor.disabled = active; setBusy?.(active); }
  async function perform(kind, fingerprint) {
    if (busy) return;
    lock(true); status.replaceChildren(notice('Saving your local project before starting...'));
    try {
      await save();
      const result = await casebookRequest(`/api/casebooks/${kind}`, {data: {id: savedId, revision, document_type: format.input.value,
        ...(kind === 'draft' ? {consent: true, fingerprint} : {})}});
      activeJob = result.id; stop.hidden = false; stop.disabled = false;
      status.replaceChildren(notice('Task started. You can recover its result in Recent activity if this window loses contact.'));
      const report = await waitForJob(result.id, job => status.replaceChildren(notice(job.message)));
      drawReport(report); status.replaceChildren(notice('Ready to review. Source matches do not establish answers.', 'success'));
      output.tabIndex = -1; output.scrollIntoView({block: 'start'}); output.focus({preventScroll: true});
    } catch (error) { if (error.partialResult) drawReport(error.partialResult); status.replaceChildren(notice(error.message, 'error')); }
    finally { activeJob = null; stop.hidden = true; lock(false); }
  }
  function drawReport(report) {
    preparedReport = report; rememberCurrent();
    const coverage = report.coverage;
    const stats = h('div', {class: 'casebook-stats'},
      ...[[coverage.documents_supplied, 'documents supplied'], [coverage.passages_indexed, 'passages indexed'],
          [coverage.documents_represented, 'documents in the selection'], [coverage.questions_without_wording_matches, 'questions with no wording match']]
        .map(([number, label]) => h('div', {}, h('strong', {}, number), h('span', {}, label))));
    const gaps = h('details', {class: 'card'}, h('summary', {}, 'What might be missing?'),
      h('p', {}, 'Retrieval is not an exhaustive review. The following documents did not contribute a selected passage:'),
      h('ul', {}, coverage.unrepresented_documents.map(name => h('li', {}, name))));
    const preview = h('details', {class: 'card'}, h('summary', {}, 'Optional: preview the exact context sent for a richer draft'),
      notice('Only these first eight questions and up to eight excerpts are sent. The result is an unverified suggestion, not a replacement for the source-only report.'),
      h('pre', {class: 'plain-wrap'}, JSON.stringify(casebookDraftContext(report), null, 2)));
    const consent = check('I approve sending the previewed context to my configured API and will review the draft.');
    const draftButton = button('Prepare an optional AI draft', () => perform('draft', report.casebook_fingerprint), 'quiet'); draftButton.disabled = true;
    consent.input.addEventListener('change', () => draftButton.disabled = !consent.input.checked);
    preview.append(consent.wrap, draftButton);
    const exportScope = handoverExportNotice(report);
    output.replaceChildren(stats, gaps, ...(exportScope
      ? [notice(exportScope)] : []), renderReport(report));
    if (report.excerpts.length && !report.model_draft) output.append(preview);
  }
  title.input.addEventListener('input', changed);
  questions.input.addEventListener('input', () => {
    scopeViews = sourceFilterStates(questionLines(questions.input.value), scopeViews);
    changed(); drawScopes(); });
  recipient.input.addEventListener('input', changed);
  sender.panel.addEventListener('input', changed);
  format.input.addEventListener('change', () => { showHandoverEvidence(); changed(); });
  handoverEvidence.input.addEventListener('change', changed);
  for (const entry of [name, contents, sourceDate, sourceURL]) entry.input.addEventListener('input', rememberCurrent);
  upload.input.addEventListener('change', async () => {
    if (busy) return;
    const batch = [], files = [...upload.input.files];
    let characters = docs.reduce((n, row) => n + row.content.length, 0);
    lock(true);
    try {
      if (docs.length + files.length > 300) throw new Error('Choose fewer files. A casebook supports at most 300 documents.');
      if (files.reduce((n, file) => n + file.size, 0) > 8000000) throw new Error('This selection is too large. Split it into smaller projects.');
      for (const file of files) {
        if (file.size > 800000) throw new Error(`${file.name} is too large. Split it into smaller text sources.`);
        const content = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
        if (!content.trim() || content.includes('\0') || content.length > 200000) throw new Error(`${file.name} is empty, binary or too large.`);
        characters += content.length;
        if (characters > 2000000) throw new Error('This selection exceeds the two-million-character limit. No files from this selection were added.');
        batch.push({title: file.name, content});
      }
      if (docs.length + batch.length > 300 || [...docs, ...batch].reduce((n, row) => n + row.content.length, 0) > 2000000) throw new Error('The project exceeds the collection limit. Use a separate casebook.');
      docs.push(...batch); changed(); drawSources(); status.replaceChildren(notice(`${batch.length} text files added. Nothing has been sent to an API.`));
    } catch (error) { status.replaceChildren(notice(error.message, 'error')); }
    finally { upload.input.value = ''; lock(false); }
  });
  backup.input.addEventListener('change', async () => {
    if (busy) return;
    lock(true);
    try {
      const file = backup.input.files[0]; if (!file) return;
      if (file.size > 10000000) throw new Error('This backup is too large.');
      if (!canReplace()) return;
      const original = JSON.parse(await file.text());
      const result = await casebookRequest('/api/casebooks/validate', {data: {document: original}});
      load({...result.document, ...(explicitScopeClear(original) ? {question_scopes: []} : {})});
      status.replaceChildren(notice('Backup opened as a new unsaved project.'));
    } catch (error) { status.replaceChildren(notice(error.message, 'error')); }
    finally { backup.input.value = ''; lock(false); }
  });
  editor.append(h('legend', {}, 'Bring the fragments together'), title.wrap, questions.wrap, scopePanel,
    h('div', {class: 'casebook-actions'}, button('Try a fictional community example', () => {
      if (!canReplace()) return;
      load(example()); status.replaceChildren(notice('Fictional example. No real venue, person or decision is represented.'));
    }), button('New project', () => { if (canReplace()) load({title: '', questions: '', documents: []}); }, 'quiet')),
    sourcePanel,
    totals, saveState, sources, format.wrap, handoverEvidence.wrap, recipient.wrap, sender.panel,
    h('div', {class: 'casebook-actions'}, button('Prepare source-only report', () => perform('build'), 'primary'),
      button('Save project', async () => { lock(true); try { await save(); const savedNotice = notice(`Saved revision ${revision}. This saves the project inputs; use Save to this computer on an edited report to keep that draft. Local storage is not encrypted.`, 'success'); savedNotice.dataset.casebookSaveSuccess = 'true'; status.replaceChildren(savedNotice); } catch(error) { status.replaceChildren(notice(error.message, 'error')); } finally { lock(false); if (hasPendingSource(pendingSource())) contents.input.focus(); } }),
      button('Export project backup', () => { try { admitPending(); download('sinter-casebook.json', JSON.stringify(value(), null, 2), 'application/json'); } catch(error) { status.replaceChildren(notice(error.message, 'error')); } })),
    h('details', {class: 'card'}, h('summary', {}, 'Backups and project removal'), backup.wrap,
      casebookBackupControls(() => { admitPending(); return value(); }),
      button('Remove saved project', async () => {
        if (!savedId || !confirm('Remove this saved project? Export a backup first. The current editor is kept.')) return;
        try { await casebookRequest('/api/casebooks/delete', {data: {id: savedId, revision}}); savedId = null; revision = null; changed(); await refresh(); }
        catch(error) { status.replaceChildren(notice(error.message, 'error')); }
      }, 'quiet')));
  sourcePanel.append(h('summary', {}, 'Add notes and references'), name.wrap, contents.wrap,
      h('div', {class: 'form-grid'}, sourceDate.wrap, sourceURL.wrap),
      button('Add this source', () => {
        if (!name.input.value.trim() || !contents.input.value.trim()) { status.replaceChildren(notice('Give the source a title and some original text.', 'error')); return; }
        if (docs.length >= 300 || docs.reduce((n, row) => n + row.content.length, contents.input.value.length) > 2000000) { status.replaceChildren(notice('The collection limit is reached. Start a separate casebook.', 'error')); return; }
        docs.push({title: name.input.value, content: contents.input.value, date: sourceDate.input.value, url: sourceURL.input.value});
        clearPending(); changed(); drawSources();
      }), button('Clear pending source', () => { if (!hasPendingSource(pendingSource()) || confirm('Clear this pending source? It has not been added or saved.')) clearPending(); }, 'quiet'), pendingNotice, upload.wrap);
  updateSaveState(); drawSources(); await refresh();
  if (preparedReport) drawReport(preparedReport);
  return h('div', {class: 'stack casebooks-page'}, h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'LESS CHASING. MORE CONTEXT.'),
    h('h2', {}, 'All the bits. One useful picture.'), h('p', {}, 'Gather scattered notes, replies, policies and past decisions. Find the original wording behind each question and keep the gaps visible.')),
    h('section', {class: 'card'}, h('h3', {}, 'Your saved projects'), catalogue),
    practiceGuide, notice('Local by default. Sources are not fetched or uploaded automatically. Save deliberately, export backups, and review before sharing.'), editor, status, stop, output);
}
