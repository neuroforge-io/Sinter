import {h, button, notice, markdown, safeLink, download, reportName, field, selectField, check, announce} from './ui.js';
import {request} from './api.js';
import {documentActions, documentMarkdown, plainDocument} from './documents.js';
import {campaignCommunicationFromDraft, campaignDraftLogBlockReason} from './campaign-letter.js';

/** The document is the default view; provenance remains one click away. */
export function renderReport(report, {onCorrect, onEditInputs, onCampaignUpdated} = {}) {
  const result = h('section', {class: 'report-area', 'aria-label': 'Your draft report'});
  const message = h('div', {class: 'non-print', 'aria-live': 'polite'});
  const campaignLog = report.campaign_link ? campaignDraftLog(report, message, onCampaignUpdated) : null;
  const save = button('Save to this computer', async () => {
    save.disabled = true;
    try {
      await request('/api/reports', {data: {report}});
      message.replaceChildren(notice('Saved in My workspace, including your edits and original evidence.', 'success'));
      announce('Report saved to My workspace.');
    } catch (error) { message.replaceChildren(notice(error.message, 'error')); save.disabled = false; }
  }, 'quiet');
  const paper = h('div', {class: 'document-paper'});
  const isCampaign = report.workflow === 'campaign';
  const documentLabel = isCampaign ? 'Decision brief' : 'Document';
  const evidenceLabel = isCampaign ? 'Audit & evidence' : 'Evidence';
  const documentPanel = h('section', {class: 'document-panel', role: 'tabpanel', 'aria-label': documentLabel}, paper);
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
    connectCitations(article, report, sources, () => select('evidence'));
    paper.replaceChildren(h('div', {class: 'paper-label'}, report.workflow === 'campaign'
      ? 'CAMPAIGN DECISION RECORD'
      : report.demo ? 'FICTIONAL EXAMPLE' : report.model_draft ? 'MODEL-GENERATED DRAFT' : report.document_edits ? 'EDITED DRAFT' : 'DRAFT FOR REVIEW'), article);
    completion.replaceChildren(h('div', {}, h('strong', {}, report.document_edits ? 'Check these details' : 'Finish the details'),
      h('p', {}, (report.document_edits ? 'Originally missing: ' : '') + (report.missing_fields || []).map(item => item.label).join(' · '))),
      onEditInputs ? button('Add missing details', onEditInputs) : h('span', {class: 'fine'}, 'Use More options → Edit draft to complete these.'));
    save.disabled = false;
  }
  let evidenceArticle = markdown(report.markdown);
  connectCitations(evidenceArticle, report, sources);
  const campaignEvidence = campaignEvidenceCounts(report.campaign);
  evidencePanel.append(...[h('div', {class: 'evidence-overview'},
    h('div', {}, h('h3', {}, isCampaign ? 'Campaign evidence at a glance' : 'What supports this draft'),
      h('p', {class: 'muted'}, isCampaign
        ? `${campaignEvidence.sources} linked campaign sources · ${campaignEvidence.excerpts} recorded wording excerpts`
        : `${(report.sources || []).length} sources · ${(report.segments || report.excerpts || []).length} ${report.segments ? 'transcript passages' : 'selected excerpts'}`)),
    h('p', {class: 'fine'}, isCampaign
      ? 'Links and excerpts are campaign entries; source records establish provenance, not truth.'
      : 'Source records establish provenance, not truth.')),
    (report.warnings || []).length ? h('details', {class: 'report-notes'}, h('summary', {}, 'Source limits and review notes'), h('ul', {}, report.warnings.map(item => h('li', {}, item)))) : null,
    h('div', {class: 'report-layout'}, evidenceArticle, sources)].filter(Boolean));
  const actions = documentActions(report, {save, onChange: () => { updateDocument(); select('document'); }});
  const missing = report.missing_fields || [];
  result.append(...[h('header', {class: 'report-heading'}, h('div', {}, h('span', {class: 'eyebrow'}, isCampaign ? 'CAMPAIGN PREVIEW' : 'YOUR DOCUMENT'),
    h('h2', {}, isCampaign ? 'Decision brief' : (report.document_title || report.title)), h('p', {class: 'muted'}, isCampaign
      ? 'Review the decision and privacy before sharing. The full audit trail and source notes are in Audit & evidence.'
      : 'Review the wording, make it yours, then copy or download.'))),
    missing.length ? completion : null,
    actions.controls, campaignLog, message, actions.feedback, actions.editor, report.model_review ? h('details', {class: 'model-review non-print'}, h('summary', {}, 'Check the model’s review notes'), h('p', {class: 'fine'}, 'A self-check by the same model; verify against your original source.'), markdown(report.model_review)) : null, tabs, documentPanel, evidencePanel].filter(Boolean));
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

function campaignDraftLog(report, feedback, onCampaignUpdated) {
  const channel = selectField('Draft channel for the campaign log', [
    ['email', 'Email'], ['letter', 'Letter'], ['portal', 'Application portal'], ['other', 'Other'],
  ], 'email');
  const control = button('Save draft to campaign log', async () => {
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
