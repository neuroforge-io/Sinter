import {h, button, notice, markdown, safeLink, download, reportName, field, selectField, check, announce} from './ui.js';
import {request} from './api.js';
import {documentActions, documentMarkdown} from './documents.js';

/** The document is the default view; provenance remains one click away. */
export function renderReport(report, {onCorrect, onEditInputs} = {}) {
  const result = h('section', {class: 'report-area', 'aria-label': 'Your draft report'});
  const message = h('div', {class: 'non-print', 'aria-live': 'polite'});
  const save = button('Save to this computer', async () => {
    save.disabled = true;
    try {
      await request('/api/reports', {data: {report}});
      message.replaceChildren(notice('Saved in My workspace, including your edits and original evidence.', 'success'));
      announce('Report saved to My workspace.');
    } catch (error) { message.replaceChildren(notice(error.message, 'error')); save.disabled = false; }
  }, 'quiet');
  const paper = h('div', {class: 'document-paper'});
  const documentPanel = h('section', {class: 'document-panel', role: 'tabpanel', 'aria-label': 'Document'}, paper);
  const evidencePanel = h('section', {class: 'evidence-panel non-print', role: 'tabpanel', 'aria-label': 'Evidence', hidden: true});
  const tabs = h('div', {class: 'report-tabs non-print', role: 'tablist', 'aria-label': 'Draft views'});
  const completion = h('div', {class: 'completion-panel non-print'});
  function select(view) {
    documentPanel.hidden = view !== 'document'; evidencePanel.hidden = view !== 'evidence';
    for (const tab of tabs.children) { const selected = tab.dataset.view === view; tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1; }
  }
  for (const [id, label] of [['document', 'Document'], ['evidence', 'Evidence']]) {
    const tab = button(label, () => select(id), 'report-tab');
    tab.setAttribute('role', 'tab'); tab.dataset.view = id;
    tab.addEventListener('keydown', event => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 'document' : event.key === 'End' ? 'evidence' : id === 'document' ? 'evidence' : 'document'; select(next); [...tabs.children].find(item => item.dataset.view === next).focus(); }
    });
    tabs.append(tab);
  }
  const sources = h('aside', {class: 'sources-panel', 'aria-label': 'Source register'},
    h('h3', {}, 'Original sources'), h('p', {class: 'muted'}, 'Open a source to check its full supplied wording.'));
  for (const source of report.sources || []) {
    sources.append(h('details', {class: 'source source-jump', 'data-source-id': source.id}, h('summary', {}, source.title),
      source.url ? safeLink(source.url, 'Open the source') : h('p', {class: 'fine'}, 'Added on this computer'),
      h('pre', {}, source.content), h('details', {class: 'source-metadata'}, h('summary', {}, 'Source record'),
        h('p', {class: 'source-id'}, (source.id || '') + ' / ' + (source.kind || 'source')), h('p', {class: 'fine'}, 'Retrieved / imported: ' + (source.retrieved_at || 'Not supplied')),
        source.sha256 ? h('p', {class: 'source-id'}, 'SHA-256: ' + source.sha256) : null)));
  }
  function updateDocument() {
    const article = markdown(documentMarkdown(report));
    connectCitations(article, report, sources, () => select('evidence'));
    paper.replaceChildren(h('div', {class: 'paper-label'}, report.demo ? 'FICTIONAL EXAMPLE' : report.model_draft ? 'MODEL-GENERATED DRAFT' : report.document_edits ? 'EDITED DRAFT' : 'DRAFT FOR REVIEW'), article);
    completion.replaceChildren(h('div', {}, h('strong', {}, report.document_edits ? 'Check these details' : 'Finish the details'),
      h('p', {}, (report.document_edits ? 'Originally missing: ' : '') + (report.missing_fields || []).map(item => item.label).join(' · '))),
      onEditInputs ? button('Add missing details', onEditInputs) : h('span', {class: 'fine'}, 'Use More options → Edit draft to complete these.'));
    save.disabled = false;
  }
  let evidenceArticle = markdown(report.markdown);
  connectCitations(evidenceArticle, report, sources);
  evidencePanel.append(...[h('div', {class: 'evidence-overview'},
    h('div', {}, h('h3', {}, 'What supports this draft'), h('p', {class: 'muted'}, `${(report.sources || []).length} sources · ${(report.segments || report.excerpts || []).length} ${report.segments ? 'transcript passages' : 'selected excerpts'}`)),
    h('p', {class: 'fine'}, 'Source records establish provenance, not truth.')),
    (report.warnings || []).length ? h('details', {class: 'report-notes'}, h('summary', {}, 'Source limits and review notes'), h('ul', {}, report.warnings.map(item => h('li', {}, item)))) : null,
    h('div', {class: 'report-layout'}, evidenceArticle, sources)].filter(Boolean));
  const actions = documentActions(report, {save, onChange: () => { updateDocument(); select('document'); }});
  const missing = report.missing_fields || [];
  result.append(...[h('header', {class: 'report-heading'}, h('div', {}, h('span', {class: 'eyebrow'}, 'YOUR DOCUMENT'),
    h('h2', {}, report.document_title || report.title), h('p', {class: 'muted'}, 'Review the wording, make it yours, then copy or download.'))),
    missing.length ? completion : null,
    actions.controls, message, actions.feedback, actions.editor, report.model_review ? h('details', {class: 'model-review non-print'}, h('summary', {}, 'Check the model’s review notes'), h('p', {class: 'fine'}, 'A self-check by the same model; verify against your original source.'), markdown(report.model_review)) : null, tabs, documentPanel, evidencePanel].filter(Boolean));
  select('document'); updateDocument();
  if (report.workflow === 'grants' && report.sources?.length) {
    documentPanel.append(grantChecks(report, () => {
      const updated = markdown(report.markdown); connectCitations(updated, report, sources); evidenceArticle.replaceWith(updated); evidenceArticle = updated;
      const last = report.screening.checks.at(-1);
      const cleanCheck = '\n\n### Requirement check\n\n' + last.field.replaceAll('_', ' ') + ': **' + last.status.replaceAll('_', ' ') + '**. ' + last.reason;
      if (report.document_edits) report.document_edits.markdown += cleanCheck;
      else if (report.document_markdown) report.document_markdown += cleanCheck;
      updateDocument(); message.replaceChildren(notice('Requirement checks updated. Save a copy to keep them.'));
    }));
  }
  if (onCorrect && report.segments?.length) documentPanel.append(correctionForm(report, onCorrect));
  return result;
}

/** Source IDs become local disclosure controls; no navigation or HTML parsing. */
function connectCitations(article, report, sources, beforeJump = () => {}) {
  const references = new Map((report.sources || []).map(item => [item.id, item.id]));
  for (const item of report.excerpts || []) references.set(item.id, item.source_id);
  for (const question of report.question_index || []) for (const item of question.matches || []) references.set(item.excerpt_id, item.source_id);
  const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
  const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    if (node.parentElement?.closest('code,pre,blockquote,a,button')) continue;
    const matches = [...node.textContent.matchAll(/\b[SE][a-f0-9]{16}\b/g)].filter(match => references.has(match[0]) && (report.sources || []).some(item => item.id === references.get(match[0])));
    if (!matches.length) continue;
    const fragment = document.createDocumentFragment(); let start = 0;
    for (const match of matches) {
      fragment.append(document.createTextNode(node.textContent.slice(start, match.index)));
      const sourceId = references.get(match[0]);
      const parent = (report.sources || []).find(item => item.id === sourceId);
      const sourceNumber = (report.sources || []).findIndex(item => item.id === sourceId) + 1;
      const jump = button('Source ' + sourceNumber, () => {
        beforeJump();
        const source = [...sources.querySelectorAll('details')].find(item => item.dataset.sourceId === sourceId);
        if (source) { source.open = true; source.scrollIntoView({block: 'center'}); source.querySelector('summary').focus({preventScroll: true}); }
      }, 'citation-link');
      jump.setAttribute('aria-label', `Show source: ${parent?.title || sourceId}`);
      fragment.append(jump); start = match.index + match[0].length;
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
