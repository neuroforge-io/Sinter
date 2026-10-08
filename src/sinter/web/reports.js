import {h, button, notice, markdown, safeLink, download, reportName, field, selectField, check, announce} from './ui.js';
import {request} from './api.js';
import {documentActions, documentMarkdown, plainDocument} from './documents.js';
import {campaignCommunicationFromDraft, campaignDraftLogBlockReason} from './campaign-letter.js';
import {campaignActionOwnerState} from './campaign-owner.js';
import {campaignActionPhaseLabel} from './campaign-plan.js';
import {registerReportDraft, trackReportEdits, trackReportEditor, reportEditorDraft,
  markReportSaved, markReportSaving, markReportSaveFailed, reportSaveState, observeReportSaveState,
  isReportDraftUnsaved, reportDraftNotice} from './report-drafts.js';
import {reportCitationIndex, reportCitationMatcher} from './report-citations.js';
import {casebookQuestionEvidence} from './casebook-question-evidence.js';
import {retainedCasebookSource, retainedQuestionContext} from './casebook-retained-context.js';
import {handoverSummaryEditor, handoverSummaryAvailable, presentHandoverSummaryTable} from './handover-summary.js';

/** The document is the default view; provenance remains one click away. */
export function renderReport(report, {onCorrect, onEditInputs, onCampaignUpdated, onSaved, recovered = false, saved = false} = {}) {
  registerReportDraft(report, documentMarkdown(report), {saved});
  const result = h('section', {class: 'report-area', 'aria-label': 'Your draft report'});
  const message = h('div', {class: 'non-print', 'aria-live': 'polite'});
  const saveState = h('p', {class: 'document-save-state non-print', role: 'status', 'aria-label': 'Document save state'});
  let savePending = false;
  function refreshSaveState() {
    const state = reportSaveState(report);
    saveState.textContent = state.message; saveState.dataset.state = state.kind;
    save.disabled = savePending || state.kind === 'saving' || state.kind === 'saved';
  }
  const campaignLog = report.campaign_link ? campaignDraftLog(report, message,
    onCampaignUpdated, () => actions.canUseDocument('saving to the campaign log'),
    () => { trackReportEdits(report, documentMarkdown(report)); refreshSaveState(); }) : null;
  const save = button('Save to My workspace', async () => {
    if (!actions.canUseDocument('saving')) return;
    if (savePending || reportSaveState(report).kind === 'saving') return;
    let snapshot, submittedMarkdown;
    try { snapshot = structuredClone(report); submittedMarkdown = documentMarkdown(snapshot); }
    catch (error) {
      markReportSaveFailed(report, {requestState: {outcome: 'not-sent'}});
      message.replaceChildren(notice(error.message, 'error')); refreshSaveState(); return;
    }
    savePending = true; markReportSaving(report);
    let failure, viewFailures = [];
    try {
      refreshSaveState();
    } catch (error) {
      savePending = false; markReportSaveFailed(report, {requestState: {outcome: 'not-sent'}});
      message.replaceChildren(notice('Save was not sent because the view could not be updated: ' + error.message, 'error')); return;
    }
    try {
      await request('/api/reports', {data: {report: snapshot}, acceptResponse: result => {
        if (!result || Array.isArray(result) || typeof result.id !== 'string'
            || !/^[a-f0-9]{32}$/.test(result.id)) throw new Error('The app did not return a valid saved-document acknowledgement.');
        return result;
      }});
      viewFailures = markReportSaved(report, submittedMarkdown, snapshot) || [];
    } catch (error) {
      markReportSaveFailed(report, error); failure = error;
    } finally { savePending = false; }
    // Persistence has been acknowledged. A later view/callback failure cannot
    // turn that known save into an uncertain write or trigger a replay.
    try {
      refreshSaveState();
      if (failure) { message.replaceChildren(notice(failure.message, 'error')); return; }
      if (viewFailures.length) throw viewFailures[0];
      const newerEdits = isReportDraftUnsaved(report);
      if (!newerEdits) actions.feedback.replaceChildren();
      message.replaceChildren(notice(newerEdits
        ? 'The submitted document was saved in My workspace. ' + reportDraftNotice(report)
        : 'Saved in My workspace, including your edits and original evidence.', newerEdits ? 'warning' : 'success'));
      announce('Report saved to My workspace.');
      await onSaved?.();
    } catch (error) {
      refreshSaveState();
      message.replaceChildren(notice(failure
        ? 'The save failed and refreshing the view also failed: ' + error.message
        : 'The submitted document was saved, but refreshing the view failed: ' + error.message, 'warning'));
    }
  }, 'primary');
  const paper = h('div', {class: 'document-paper'});
  const isCampaign = report.workflow === 'campaign';
  const isAssistant = report.workflow === 'assistant';
  const documentLabel = isCampaign ? 'Decision brief' : 'Document';
  const evidenceLabel = isCampaign ? 'Audit & evidence' : 'Evidence';
  const documentPanel = h('section', {class: 'document-panel report-print-target', role: 'tabpanel', 'aria-label': documentLabel}, paper);
  const evidencePanel = h('section', {class: 'evidence-panel non-print', role: 'tabpanel', 'aria-label': evidenceLabel, hidden: true});
  const tabs = h('div', {class: 'report-tabs non-print', role: 'tablist', 'aria-label': isCampaign ? 'Campaign views' : 'Draft views'});
  const completion = h('div', {class: 'completion-panel non-print'});
  function select(view) {
    documentPanel.hidden = view !== 'document'; evidencePanel.hidden = view !== 'evidence';
    for (const tab of tabs.children) { const selected = tab.dataset.view === view; tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1; }
  }
  for (const [id, label] of [['document', documentLabel], ['evidence', evidenceLabel]]) {
    const tab = button(label, () => select(id), 'report-tab');
    tab.setAttribute('role', 'tab'); tab.dataset.view = id;
    tab.addEventListener('keydown', event => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 'document' : event.key === 'End' ? 'evidence' : id === 'document' ? 'evidence' : 'document'; select(next); [...tabs.children].find(item => item.dataset.view === next).focus(); }
    });
    tabs.append(tab);
  }
  const sources = h('aside', {class: 'sources-panel', 'aria-label': 'Source register'},
    h('h3', {}, isCampaign ? 'Registered campaign sources' : 'Original sources'),
    h('p', {class: 'muted'}, isCampaign
      ? 'These titles, links, notes and dates were entered in the campaign. Sinter has not opened or verified them.'
      : 'Open a source to check its full supplied wording.'));
  if (isCampaign) {
    for (const source of report.campaign?.sources || []) {
      const usageCount = (report.campaign?.opportunities || []).filter(row =>
        row.window_source_id === source.id).length
        + (report.campaign?.requirements || []).filter(row => row.source_id === source.id).length
        + (report.campaign?.assets || []).reduce((total, asset) => total
          + (asset.references || []).filter(reference => reference.source_id === source.id).length, 0);
      sources.append(h('details', {class: 'source source-jump', 'data-source-id': source.id},
        h('summary', {}, source.title || 'Untitled source',
          h('span', {class: 'source-usage-count'}, `${usageCount} linked record${usageCount === 1 ? '' : 's'}`)),
        source.url ? safeLink(source.url, 'Open campaign source')
          : h('p', {class: 'fine'}, 'No source link recorded.'),
        h('p', {class: 'campaign-source-notes'}, source.notes || 'No source notes recorded.'),
        h('p', {class: 'source-id'}, 'Checked date (user-entered): '
          + (source.checked_at || 'Not recorded'))));
    }
  } else {
    for (const source of report.sources || []) {
      sources.append(h('details', {class: 'source source-jump', 'data-source-id': source.id}, h('summary', {}, source.title),
        source.url ? safeLink(source.url, 'Open the source') : h('p', {class: 'fine'}, 'Added on this computer'),
        h('pre', {}, source.content), h('details', {class: 'source-metadata'}, h('summary', {}, 'Source record'),
          h('p', {class: 'source-id'}, (source.id || '') + ' / ' + (source.kind || 'source')), h('p', {class: 'fine'}, 'Retrieved / imported: ' + (source.retrieved_at || 'Not supplied')),
          source.sha256 ? h('p', {class: 'source-id'}, 'SHA-256: ' + source.sha256) : null)));
    }
  }
  function updateDocument() {
    const article = markdown(documentMarkdown(report));
    if (isCampaign) article.classList.add('campaign-decision-document');
    const hasSummary = handoverSummaryAvailable(report) && documentMarkdown(report).includes('## At a glance\n');
    const responsiveSummary = hasSummary && presentHandoverSummaryTable(article,
      {report, currentMarkdown: documentMarkdown(report)});
    const compactReading = article.className.split(' ').includes('handover-reading-document');
    result.classList.toggle('handover-reading-report', compactReading);
    guidance.hidden = compactReading;
    if (summaryEditor) {
      summaryEditor.classList.toggle('handover-inline-editor', compactReading);
      summaryEditor.querySelector('summary').classList.toggle('button', compactReading);
      if (compactReading) actions.controls.querySelector('.button-row').append(summaryEditor);
      else result.insertBefore(summaryEditor, tabs);
    }
    if (hasSummary) article.classList.add('handover-summary-document');
    connectCitations(article, report, sources, () => select('evidence'), true);
    paper.replaceChildren(h('div', {class: 'paper-label'}, report.workflow === 'campaign'
      ? 'CAMPAIGN DECISION RECORD'
      : report.incomplete ? 'INCOMPLETE MODEL DRAFT' : report.demo ? 'FICTIONAL EXAMPLE' : report.model_draft ? 'MODEL-GENERATED DRAFT' : report.document_edits ? 'EDITED DRAFT' : 'DRAFT FOR REVIEW'),
      ...(report.review_status === 'stale' ? [h('p', {class: 'document-review-warning', role: 'note'},
        'Review status: stale. Check this saved record before current use; editing its wording does not confirm the original evidence.')] : []),
      ...(hasSummary && !responsiveSummary ? [h('p', {class: 'handover-summary-scroll-hint fine'}, 'On a small screen, scroll the summary table sideways to review every column.')] : []), article);
    completion.replaceChildren(h('div', {}, h('strong', {}, report.document_edits ? 'Check these details' : 'Finish the details'),
      h('p', {}, (report.document_edits ? 'Originally missing: ' : '') + (report.missing_fields || []).map(item => item.label).join(' · '))),
      onEditInputs ? button('Add missing details', onEditInputs) : h('span', {class: 'fine'}, 'Use Edit draft to complete these.'));
    refreshSaveState();
  }
  let evidenceArticle = markdown(report.markdown);
  connectCitations(evidenceArticle, report, sources);
  const campaignEvidence = campaignEvidenceCounts(report.campaign);
  const questionEvidence = casebookQuestionEvidence(report);
  if (questionEvidence) evidencePanel.append(questionEvidenceView(report, questionEvidence, sources));
  if (isAssistant) evidencePanel.append(assistantEvidence(report, evidenceArticle));
  else evidencePanel.append(...[h('div', {class: 'evidence-overview'},
    h('div', {}, h('h3', {}, isCampaign ? 'Campaign evidence at a glance' : 'What supports this draft'),
      h('p', {class: 'muted'}, isCampaign
        ? `${campaignEvidence.sources} linked campaign sources · ${campaignEvidence.excerpts} recorded wording excerpts`
        : `${(report.sources || []).length} sources · ${(report.segments || report.excerpts || []).length} ${report.segments ? 'transcript passages' : 'selected excerpts'}`)),
    h('p', {class: 'fine'}, isCampaign
      ? 'Links and excerpts are campaign entries; source records establish provenance, not truth.'
      : 'Source records establish provenance, not truth.')),
    (report.warnings || []).length ? h('details', {class: 'report-notes'}, h('summary', {}, 'Source limits and review notes'), h('ul', {}, report.warnings.map(item => h('li', {}, item)))) : null,
    h('div', {class: 'report-layout'}, evidenceArticle, sources)].filter(Boolean));
  const actions = documentActions(report, {save, editorSeed: reportEditorDraft(report),
    onEditorChange: (text, open) => { trackReportEditor(report, text, open); refreshSaveState(); },
    onChange: () => { trackReportEdits(report, documentMarkdown(report)); updateDocument(); select('document'); }});
  const summaryEditor = handoverSummaryEditor(report, {actions, onDraftChange: refreshSaveState});
  const missing = report.missing_fields || [];
  const guidance = h('p', {class: 'muted'}, isCampaign
    ? 'Review the decision and privacy before sharing. The full audit trail and source notes are in Audit & evidence.'
    : 'Review the wording, make it yours, then copy or download.');
  result.append(...[recovered ? notice('Recovered draft from an earlier preparation. It retains the original inputs and evidence; later project changes are not included. Check the current saved project before using this draft.', 'warning') : null,
    h('header', {class: 'report-heading'}, h('div', {}, h('span', {class: 'eyebrow'}, isCampaign ? 'CAMPAIGN PREVIEW' : 'YOUR DOCUMENT'),
    h('h2', {}, isCampaign ? 'Decision brief' : (report.document_title || report.title)), guidance)),
    missing.length ? completion : null,
    saveState, actions.controls, campaignLog, message, actions.feedback, actions.editor, summaryEditor, report.model_review ? h('details', {class: 'model-review non-print'}, h('summary', {}, 'Check the model’s review notes'), h('p', {class: 'fine'}, 'A self-check by the same model; verify against your original source.'), markdown(report.model_review)) : null, tabs, documentPanel, evidencePanel].filter(Boolean));
  select('document'); updateDocument();
  if (report.workflow === 'grants' && report.sources?.length) {
    documentPanel.append(grantChecks(report, () => {
      const updated = markdown(report.markdown); connectCitations(updated, report, sources); evidenceArticle.replaceWith(updated); evidenceArticle = updated;
      const last = report.screening.checks.at(-1);
      const cleanCheck = '\n\n### Requirement check\n\n' + last.field.replaceAll('_', ' ') + ': **' + last.status.replaceAll('_', ' ') + '**. ' + last.reason;
      if (report.document_edits) report.document_edits.markdown += cleanCheck;
      else if (report.document_markdown) report.document_markdown += cleanCheck;
      trackReportEdits(report, documentMarkdown(report));
      updateDocument(); message.replaceChildren(notice('Requirement checks updated. Save a copy to keep them.'));
    }));
  }
  if (onCorrect && report.segments?.length) documentPanel.append(correctionForm(report, onCorrect));
  observeReportSaveState(report, refreshSaveState, () => result.isConnected);
  return result;
}

/** A local view of this report's historical search choices and exact quotations. */
function questionEvidenceView(report, rows, sources) {
  const panel = h('section', {class: 'casebook-question-evidence', 'aria-label': 'Questions and evidence'},
    h('h3', {}, 'Questions and evidence'),
    h('p', {class: 'muted'}, 'Recorded wording-search choices and passages from this report. Related wording is not an answer; no match does not prove an issue is absent.'),
    h('p', {class: 'fine'}, 'This view retains the report’s own evidence. Later project edits are not included. Opening a quote does not send anything.'));
  const jumpToOriginal = sourceId => {
    const original = [...sources.querySelectorAll('[data-source-id]')]
      .find(item => item.dataset.sourceId === sourceId);
    if (!original) throw new Error('The original text is not available in this report. No current source was substituted.');
    original.open = true; original.scrollIntoView({block: 'center'});
    original.querySelector('summary').focus({preventScroll: true});
  };
  for (const row of rows) {
    const card = h('article', {class: 'question-evidence-row', 'aria-label': `Question ${row.position} evidence`},
      h('h4', {}, `Question ${row.position}`, h('span', {class: 'question-evidence-state'}, row.status)),
      h('p', {class: 'question-evidence-question'}, row.questionAvailable ? row.question : 'Question wording unavailable'),
      h('p', {class: 'fine'}, 'Recorded search choice: ', h('strong', {}, row.scopeLabel)));
    for (const gap of row.gaps) card.append(notice(gap, 'warning'));
    if (row.coverage && row.scopeMode !== 'none') {
      const {sourceCount, excerptedSourceCount, unexcerptedSources} = row.coverage;
      card.append(h('p', {class: 'question-evidence-coverage'},
        `Exact retained quotes from ${excerptedSourceCount} of ${sourceCount} ${row.scopeMode === 'all' ? 'supplied' : 'chosen'} source${sourceCount === 1 ? '' : 's'}.`));
      if (unexcerptedSources.length) {
        if (row.scopeMode !== 'all') card.append(notice(
          `${unexcerptedSources.length} chosen source${unexcerptedSources.length === 1 ? ' has' : 's have'} no exact retained quote for this question. This does not mean ${unexcerptedSources.length === 1 ? 'it lacks' : 'they lack'} an answer.`, 'warning'));
        const missing = h('details', {class: 'question-evidence-unrepresented'},
          h('summary', {}, `Inspect ${unexcerptedSources.length} source${unexcerptedSources.length === 1 ? '' : 's'} without a retained quote for this question`),
          h('p', {class: 'fine'}, 'This counts source identities and exact quote matches, not relevance, authority or eligibility. All original sources remain separate from the selected quotations.'));
        const contents = h('div'); missing.append(contents);
        missing.addEventListener('toggle', () => {
          if (!missing.open || contents.firstChild) return;
          for (const source of unexcerptedSources) {
            const feedback = h('p', {role: 'status', class: 'fine'});
            const item = h('div', {}, h('p', {}, source.title || 'Title not retained'),
              h('p', {class: 'source-id'}, `Source reference: ${source.id}`),
              ...(source.date ? [h('p', {class: 'fine'}, `Supplied date (unverified): ${source.date}`)] : []));
            if (source.originalRetained) item.append(button(`Inspect retained original for question ${row.position}, source ${source.id}`, async event => {
              const control = event.currentTarget; control.disabled = true;
              try { await retainedCasebookSource(report, source.id); if (control.isConnected) jumpToOriginal(source.id); }
              catch (error) { if (control.isConnected) feedback.textContent = error.message; }
              finally { control.disabled = false; }
            }, 'quiet'));
            else item.append(h('p', {class: 'fine'}, 'This report retains the source record, but not its original text. Inspect the project or backup that produced this report; a newer project is not a substitute.'));
            item.append(feedback); contents.append(item);
          }
        });
        card.append(missing);
      }
    }
    for (const passage of row.matches) {
      if (!passage.available) {
        card.append(notice('Evidence unavailable: the recorded excerpt or its exact original cannot be resolved. No substitute was used.'),
          h('p', {class: 'source-id'}, 'Recorded excerpt ID: ' + (passage.excerptId || 'unavailable')));
        continue;
      }
      const displayLabel = passage.label === 'Recorded excerpt' ? `${passage.label} ${passage.excerptId}` : passage.label;
      const context = h('div', {class: 'question-evidence-context'});
      const contextStatus = h('p', {role: 'status', class: 'fine'});
      const surrounding = button(`Inspect surrounding text for question ${row.position} ${displayLabel}`, async event => {
        const control = event.currentTarget; control.disabled = true;
        try {
          const retained = await retainedQuestionContext(report, row.position - 1, passage.excerptId);
          if (!control.isConnected) return;
          context.replaceChildren(notice('Additional original text shown locally. It is not included in this report’s quotations, Word document or optional AI preview.'),
            h('p', {class: 'fine'}, `Retained original: ${retained.originalCharacters} Unicode characters. The quotation remains ${retained.start}–${retained.end}. These windows may end inside a section or table; inspect the full original if needed.`),
            h('p', {class: 'fine'}, `Before the quote: Unicode characters ${retained.beforeStart}–${retained.start}.`),
            retained.before ? h('pre', {class: 'plain-wrap'}, retained.before) : h('p', {class: 'fine'}, 'The quote starts at the beginning of this original.'),
            h('p', {class: 'fine'}, `After the quote: Unicode characters ${retained.end}–${retained.afterEnd}.`),
            retained.after ? h('pre', {class: 'plain-wrap'}, retained.after) : h('p', {class: 'fine'}, 'The quote ends at the end of this original.'));
          contextStatus.textContent = 'Surrounding text inspected locally; the recorded quotation is unchanged.';
        } catch (error) { if (control.isConnected) contextStatus.textContent = error.message; }
        finally { control.disabled = false; }
      }, 'quiet');
      const quote = h('details', {class: 'question-evidence-quote'},
        h('summary', {'aria-label': `Inspect question ${row.position} ${displayLabel}, source ${passage.sourceId}`},
          `Inspect ${displayLabel}: ${passage.sourceTitle || 'Title not retained'}`),
        h('pre', {class: 'plain-wrap'}, passage.quote),
        h('p', {class: 'source-id'}, `Excerpt ID: ${passage.excerptId}`),
        h('p', {class: 'source-id'}, `Source ID: ${passage.sourceId}`),
        h('p', {class: 'fine'}, `Unicode characters ${passage.start}–${passage.end} (zero-based, end-exclusive) in the retained original.`),
        surrounding, contextStatus, context,
        button(`Open original source for ${displayLabel}`, async event => {
          const control = event.currentTarget; control.disabled = true;
          try { await retainedCasebookSource(report, passage.sourceId); if (control.isConnected) jumpToOriginal(passage.sourceId); }
          catch (error) { if (control.isConnected) contextStatus.textContent = error.message; }
          finally { control.disabled = false; }
        }, 'quiet'));
      card.append(quote);
    }
    if (!row.matches.length && !row.gaps.length) card.append(h('p', {class: 'fine'}, row.status === 'No sources selected'
      ? 'No source was selected for this question. No evidence was matched.'
      : 'No wording match was retained for this question. Ask for clarification or add the missing source in the project.'));
    panel.append(card);
  }
  return panel;
}

/** Campaign entries preserve the approved context without implying verification. */
function assistantEvidence(report, response) {
  const context = report.context || {};
  const checks = Array.isArray(context.selected_checks) ? context.selected_checks : [];
  const actions = Array.isArray(context.selected_actions) ? context.selected_actions : [];
  const route = context.route || {};
  const count = (total, noun) => `${total} selected ${noun}${total === 1 ? '' : 's'}`;
  const records = h('div', {class: 'stack'},
    h('div', {class: 'evidence-overview'}, h('div', {},
      h('h3', {}, 'Campaign records used by the assistant'),
      h('p', {class: 'muted'}, `${count(checks.length, 'check')} · ${count(actions.length, 'action')}`)),
      h('p', {class: 'fine'}, 'User-entered and unverified')),
    h('p', {}, 'These are the campaign entries included in the approved request. Links, quotations, assessments and dates were entered by a user; Sinter has not opened or verified the sources.'),
    context.organisation ? h('p', {class: 'fine'}, `${context.organisation} · ${report.campaign_title || 'Saved campaign'} · revision ${report.revision ?? 'not recorded'}`) : null,
    route.name ? h('details', {class: 'source'}, h('summary', {}, `Recorded route: ${route.name}`),
      h('p', {}, context.objective || 'Objective not recorded.'),
      h('p', {class: 'fine'}, `Recorded state: ${route.status || 'not recorded'}. Window: ${route.application_window || 'not recorded'}. Deadline: ${route.deadline || 'not recorded'}.`),
      route.window_source_quote ? h('div', {}, h('p', {class: 'fine'}, 'Window wording entered by a user'), h('blockquote', {}, route.window_source_quote)) : null,
      h('p', {class: 'fine'}, `Window checked date (user-entered): ${route.window_checked_at || 'not recorded'}`)) : null,
    h('h4', {}, 'Selected checks'));
  if (!checks.length) records.append(h('p', {class: 'fine'}, Array.isArray(context.selected_checks)
    ? 'No eligibility checks were included in this request.' : 'No selected check records were retained in this saved report.'));
  for (const row of checks) records.append(h('details', {class: 'source'},
    h('summary', {}, `Check ${row.record}: ${row.rule}`),
    h('p', {class: 'fine'}, `Recorded assessment: ${row.status || 'not recorded'} · checked date (user-entered): ${row.checked_at || 'not recorded'}`),
    h('p', {}, row.evidence || 'Applicant evidence not recorded.'),
    h('p', {class: 'fine'}, `Source linkage at request time: ${row.source_snapshot || 'not recorded'}`),
    row.source_url ? safeLink(row.source_url, 'Open the recorded source link') : h('p', {class: 'fine'}, 'No source link was included.'),
    row.source_quote ? h('div', {}, h('p', {class: 'fine'}, 'Quoted wording entered by a user'), h('blockquote', {}, row.source_quote))
      : h('p', {class: 'fine'}, 'No quoted source wording was included.')));
  records.append(h('h4', {}, 'Selected actions'));
  if (!actions.length) records.append(h('p', {class: 'fine'}, Array.isArray(context.selected_actions)
    ? 'No existing actions were included in this request.' : 'No selected action records were retained in this saved report.'));
  for (const row of actions) records.append(h('details', {class: 'source'},
    h('summary', {}, `Action ${row.record}: ${row.task}`),
    h('p', {class: 'fine'}, `Recorded state: ${row.status || 'not recorded'}. Proposed date: ${row.due || 'not recorded'}.`),
    h('p', {}, `Recorded owner: ${campaignActionOwnerState(row.owner, row.owner_confirmed, row.owner_kind).summary}`),
    h('p', {class: 'fine'}, `Scope: ${row.opportunity || 'campaign-wide'} (${row.scope_confirmed ? 'user-marked confirmed' : 'unconfirmed'}). Phase: ${campaignActionPhaseLabel(row.submission_phase)}.`)));
  if (report.warnings?.length) records.append(h('details', {class: 'report-notes'}, h('summary', {}, 'Source limits and review notes'),
    h('ul', {}, report.warnings.map(item => h('li', {}, item)))));
  records.append(h('details', {class: 'report-notes'}, h('summary', {}, 'Model response and request record'),
    response, h('h4', {}, 'Exact approved request'),
    report.request_content ? h('pre', {class: 'help-code'}, report.request_content)
      : h('p', {class: 'fine'}, 'The exact request was not retained in this saved report.')));
  return records;
}

export function campaignEvidenceCounts(campaign) {
  if (!campaign || typeof campaign !== 'object') return {sources: 0, excerpts: 0};
  const sourceIds = new Set();
  const excerpts = [];
  for (const row of Array.isArray(campaign.opportunities) ? campaign.opportunities : []) {
    if (row.window_source_id) {
      sourceIds.add(row.window_source_id);
      excerpts.push(row.window_source_quote);
    }
  }
  for (const row of Array.isArray(campaign.requirements) ? campaign.requirements : []) {
    if (row.source_id) sourceIds.add(row.source_id);
    if (row.source_id || row.source_url) excerpts.push(row.source_quote);
  }
  for (const asset of Array.isArray(campaign.assets) ? campaign.assets : []) {
    for (const reference of Array.isArray(asset.references) ? asset.references : []) {
      if (reference.source_id) sourceIds.add(reference.source_id);
      if (reference.source_id || reference.url) excerpts.push(reference.excerpt);
    }
  }
  return {sources: sourceIds.size,
    excerpts: excerpts.filter(value => typeof value === 'string' && value.trim()).length};
}

function campaignDraftLog(report, feedback, onCampaignUpdated, canSave, onChange) {
  const channel = selectField('Draft channel for the campaign log', [
    ['email', 'Email'], ['letter', 'Letter'], ['portal', 'Application portal'], ['other', 'Other'],
  ], 'email');
  const control = button('Save draft to campaign log', async () => {
    if (!canSave()) return;
    const link = report.campaign_link;
    const blocked = campaignDraftLogBlockReason(link);
    if (blocked) { feedback.replaceChildren(notice(blocked, 'error')); return; }
    control.disabled = true;
    try {
      const current = await request('/api/campaigns/' + encodeURIComponent(link.id));
      if (current.revision !== link.revision) {
        throw new Error('The campaign changed after this letter was prepared. Nothing was saved. Open the latest campaign, review its changes, then create a fresh clarification draft.');
      }
      const document = structuredClone(current.document);
      if (!document.opportunities?.some(row => row.name === link.opportunity)) {
        throw new Error('This opportunity is no longer in the saved campaign. Nothing was saved. Open the campaign and create a fresh clarification draft.');
      }
      const communication = campaignCommunicationFromDraft({report,
        content: plainDocument(documentMarkdown(report)), channel: channel.input.value, date: ''});
      document.communications = Array.isArray(document.communications) ? document.communications : [];
      if (document.communications.length >= 200) throw new Error('This campaign log already has 200 communications. Export or archive a copy before adding another.');
      document.communications.push(communication);
      const saved = await request('/api/campaigns/save', {data: {
        document, id: link.id, revision: link.revision,
      }});
      onCampaignUpdated?.(saved);
      report.campaign_link = {...link, revision: saved.revision, logged: true};
      onChange();
      control.textContent = 'Saved as a draft · not sent';
      feedback.replaceChildren(notice('Saved to this computer in the campaign communications log as a draft. It has not been sent.', 'success'));
      announce('Campaign draft saved locally and marked not sent.');
    } catch (error) {
      feedback.replaceChildren(notice(error.message, 'error'));
      control.disabled = false;
    }
  }, 'quiet');
  const blocked = campaignDraftLogBlockReason(report.campaign_link);
  if (blocked) control.disabled = true;
  const evidenceLinks = Array.isArray(report.campaign_link?.evidence_links)
    ? report.campaign_link.evidence_links : [];
  return h('section', {class: 'campaign-draft-log non-print', 'aria-label': 'Campaign communication log'},
    h('p', {class: 'muted'}, 'Keep a copy of this exact draft in the linked campaign. Saving it marks it as not sent; Sinter will not contact anyone.'),
    evidenceLinks.length ? h('div', {class: 'campaign-draft-source-preview'},
      h('p', {class: 'fine'}, 'These selected campaign source links will be attached to the communication record. They remain user-entered and unverified.'),
      h('ul', {}, evidenceLinks.map(link => h('li', {}, safeLink(link.url, link.title || link.url),
        h('small', {class: 'fine'}, [
          link.source_id ? `Source ID ${link.source_id.slice(0, 8)}` : 'Manual link',
          link.checked_at ? `checked ${link.checked_at} · user-entered` : 'check date not recorded',
        ].join(' · '))))))
      : h('p', {class: 'fine'}, 'No linked campaign source is recorded for this route’s open checks. You can add references to the communication record after saving.'),
    channel.wrap, control, blocked ? h('p', {class: 'fine'}, blocked) : null);
}

/** Source IDs become local disclosure controls; no navigation or HTML parsing. */
function connectCitations(article, report, sources, beforeJump = () => {}, includePassages = false) {
  const {references, passages} = reportCitationIndex(report, {includePassages});
  const citationMatches = reportCitationMatcher(references);
  const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
  const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    if (node.parentElement?.closest('code,pre,blockquote,a,button')) continue;
    const matches = citationMatches(node.textContent);
    if (!matches.length) continue;
    const fragment = document.createDocumentFragment(); let start = 0;
    for (const match of matches) {
      fragment.append(document.createTextNode(node.textContent.slice(start, match.index)));
      const sourceId = match.sourceId;
      const parent = (report.sources || []).find(item => item.id === sourceId);
      const sourceNumber = (report.sources || []).findIndex(item => item.id === sourceId) + 1;
      const passage = passages.get(match.id);
      const jump = button(passage?.label || 'Source ' + sourceNumber, () => {
        beforeJump();
        const source = [...sources.querySelectorAll('details')].find(item => item.dataset.sourceId === sourceId);
        if (source) { source.open = true; source.scrollIntoView({block: 'center'}); source.querySelector('summary').focus({preventScroll: true}); }
      }, 'citation-link');
      jump.setAttribute('aria-label', passage
        ? `Show ${passage.label}: ${parent?.title || sourceId}`
        : `Show source: ${parent?.title || sourceId}`);
      if (passage) jump.title = `Unicode characters ${passage.start}–${passage.end} (zero-based, end-exclusive) in the retained original.`;
      fragment.append(jump); start = match.index + match.id.length;
    }
    fragment.append(document.createTextNode(node.textContent.slice(start))); node.replaceWith(fragment);
  }
}

function grantChecks(report, update) {
  const fieldName = selectField('Profile field', [['organisation_type', 'Organisation type'], ['location', 'Location'], ['budget', 'Budget']]);
  const actual = field('Your organisation\'s value', 'text', '', 'Use the same currency and units for budget comparisons.');
  const profile = report.profile || report.input_snapshot?.profile || {};
  actual.input.value = profile[fieldName.input.value] ?? '';
  fieldName.input.addEventListener('change', () => { actual.input.value = profile[fieldName.input.value] ?? ''; });
  const operator = selectField('Requirement comparison', [['equals', 'Equals'], ['contains', 'Contains'], ['minimum', 'At least'], ['maximum', 'At most']]);
  const expected = field('Required value', 'text');
  const source = selectField('Requirement source', report.sources.map(item => [item.id, item.title]));
  const quote = field('Exact requirement wording', 'textarea', '', 'Copy the complete relevant wording, without removing exclusions.');
  const confirmed = check('I checked that this is the current official guidance and that this comparison represents the requirement.');
  const output = h('div', {'aria-live': 'polite'});
  const entries = [...(report.screening?.checks || [])];
  const checkButton = button('Check this requirement', async () => {
    checkButton.disabled = true;
    try {
      if (entries.length >= 30) throw new Error('This report already has 30 checks. Start a separate report for another grant.');
      const response = await request('/api/screen', {data: {
        sources: report.sources, profile: {[fieldName.input.value]: actual.input.value},
        criteria: [{field: fieldName.input.value, operator: operator.input.value, value: expected.input.value,
          source_id: source.input.value, quote: quote.input.value, confirmed: confirmed.input.checked}]
      }});
      entries.push(...response.checks);
      report.screening = {status: 'review_required', checks: entries, notice: response.notice, markdown: response.markdown};
      report.markdown += '\n\n' + response.markdown;
      output.append(notice(response.checks[0].status.replaceAll('_', ' ').toUpperCase() + ': ' + response.checks[0].reason));
      update(); announce('Requirement checked. Overall eligibility still needs review.');
    } catch (error) { output.append(notice(error.message, 'error')); }
    finally { checkButton.disabled = false; }
  }, 'primary');
  return h('details', {class: 'card non-print'}, h('summary', {}, 'Screen a grant requirement'),
    notice('Check each grant separately. Passing one rule is not eligibility. Missing, unofficial or fictional evidence stays unknown.'),
    h('div', {class: 'form-grid'}, fieldName.wrap, actual.wrap, operator.wrap, expected.wrap),
    source.wrap, quote.wrap, confirmed.wrap, checkButton, output);
}

function correctionForm(report, onCorrect) {
  const segment = selectField('Transcript segment', report.segments.map(item => [item.id, item.id + ' / ' + item.speaker]));
  const original = field('Original words (preserved)', 'textarea', report.segments[0].text, '', {readOnly: true});
  const replacement = field('Reviewed replacement', 'textarea');
  const reason = field('Why is this correction justified?', 'text', '', 'For example: checked the recording at 03:12. Do not change the speaker\'s meaning.');
  segment.input.addEventListener('change', () => {
    original.input.value = report.segments.find(item => item.id === segment.input.value).text;
    replacement.input.value = ''; reason.input.value = '';
  });
  const errorBox = h('div');
  const apply = button('Apply reviewed correction', async () => {
    if (!replacement.input.value.trim() || !reason.input.value.trim()) {
      errorBox.replaceChildren(notice('Enter corrected text and a reason for the change.', 'error')); return;
    }
    apply.disabled = true;
    const corrections = (report.corrections || []).filter(item => item.segment_id !== segment.input.value);
    corrections.push({segment_id: segment.input.value, original: original.input.value,
      replacement: replacement.input.value, reason: reason.input.value});
    try { await onCorrect(corrections); }
    catch (error) { errorBox.replaceChildren(notice(error.message, 'error')); }
    finally { apply.disabled = false; }
  });
  return h('details', {class: 'card non-print'}, h('summary', {}, 'Make a traceable transcript correction'),
    segment.wrap, original.wrap, replacement.wrap, reason.wrap, apply, errorBox);
}
