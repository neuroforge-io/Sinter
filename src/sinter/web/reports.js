import {h, button, notice, markdown, safeLink, download, reportName, field, selectField, check, announce} from './ui.js';
import {request} from './api.js';

/** Display and export share one report, including subsequent reviewed checks. */
export function renderReport(report, {onCorrect} = {}) {
  const message = h('div', {class: 'non-print', 'aria-live': 'polite'});
  let article = markdown(report.markdown);
  const result = h('section', {class: 'report-area', 'aria-label': 'Your draft report'});
  const save = button('Save to this computer', async () => {
    save.disabled = true;
    try {
      await request('/api/reports', {data: {report}});
      message.replaceChildren(notice('Saved in My workspace. Local storage is not encrypted; use a trusted computer.', 'success'));
      announce('Report saved to My workspace.');
    } catch (error) { message.replaceChildren(notice(error.message, 'error')); save.disabled = false; }
  }, 'primary');
  const controls = h('div', {class: 'button-row non-print'},
    button('Download document', () => download(reportName(report.title) + '.md', report.markdown, 'text/markdown;charset=utf-8')),
    button('Copy draft text', async () => {
      try { await navigator.clipboard.writeText(report.markdown); announce('Draft text copied.'); }
      catch { message.replaceChildren(notice('Clipboard access is unavailable. Use Download document instead.', 'error')); }
    }),
    button('Download evidence pack', () => download(reportName(report.title) + '.json', JSON.stringify(report, null, 2), 'application/json')),
    button('Print / save PDF', () => window.print()), save);
  const sources = h('aside', {class: 'sources-panel non-print', 'aria-label': 'Source register'},
    h('h3', {}, 'Follow the evidence'), h('p', {class: 'muted'}, 'A citation shows where text came from, not that it is true.'));
  for (const source of report.sources || []) {
    sources.append(h('details', {class: 'source'}, h('summary', {}, source.title),
      h('p', {class: 'source-id'}, source.id + ' / ' + source.kind),
      source.url ? safeLink(source.url, 'Open the source') : h('p', {}, 'Supplied locally; no public link.'),
      h('p', {class: 'muted'}, 'Retrieved / imported: ' + source.retrieved_at),
      h('pre', {}, source.content), h('p', {class: 'source-id'}, 'SHA-256: ' + source.sha256)));
  }
  result.append(h('header', {class: 'report-header'},
    h('div', {}, h('span', {class: 'badge warm'}, 'DRAFT / REVIEW REQUIRED'), h('h2', {}, 'Your work, with the receipts.')), controls),
    message, h('div', {class: 'non-print stack'}, (report.warnings || []).map(item => notice(item))),
    h('div', {class: 'report-layout'}, article, sources));
  if (report.workflow === 'grants' && report.sources?.length) {
    result.append(grantChecks(report, () => {
      const updated = markdown(report.markdown); article.replaceWith(updated); article = updated;
      save.disabled = false; message.replaceChildren(notice('The report changed. Save a new copy to retain these checks.'));
    }));
  }
  if (onCorrect && report.segments?.length) result.append(correctionForm(report, onCorrect));
  return result;
}

function grantChecks(report, update) {
  const fieldName = selectField('Profile field', [['organisation_type', 'Organisation type'], ['location', 'Location'], ['budget', 'Budget']]);
  const actual = field('Your organisation\'s value', 'text', '', 'Use the same currency and units for budget comparisons.');
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
      report.screening = {status: 'review_required', checks: entries, notice: response.notice};
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
