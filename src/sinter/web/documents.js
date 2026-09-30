/** A usable document is separate from the immutable evidence that produced it. */
import {
  h, button, check, field, markdown, download, reportName, notice, announce,
} from './ui.js';
import {request} from './api.js';
import {insertDocumentPageBreak} from './document-page-break.js';

const REDACTED = '[Redacted from this export]';
const PRIVATE_PACK_NOTICE = 'This export omits communication bodies, subjects, '
  + 'contact names and links, plus campaign signatory and contact details. '
  + 'Edited document text is omitted to prevent hidden copies. This is not a '
  + 'complete privacy scrub: applicant evidence, objectives, answers, budget, '
  + 'action owners and source notes may still contain user-entered personal or '
  + 'sensitive details. Review the whole file before sharing. The saved campaign '
  + 'is unchanged.';

function redactCommunicationMarkdown(value) {
  const heading = '## Communications log · user-entered, unverified';
  const start = value.indexOf(heading);
  if (start < 0) return null;
  // Never locate a suffix using headings from this Markdown: user-pasted
  // correspondence can contain the same heading and create a false boundary.
  // Source records remain available as structured campaign data in the pack.
  return value.slice(0, start) + heading
    + '\n\nCommunication bodies, subject lines, contact names and evidence links '
    + 'are redacted from this export.'
    + '\n\nCharacter counts use Unicode code points, including whitespace.\n';
}

/** Build a detached campaign evidence-pack snapshot with private fields
 * redacted by default.
 */
export function evidencePackForDownload(report, {includePrivate = false} = {}) {
  const pack = JSON.parse(JSON.stringify(report));
  if (pack.workflow !== 'campaign') return pack;
  if (includePrivate) {
    pack.export_privacy = {
      campaign_private_details: 'included_by_user_choice',
      notice: 'Private campaign details were included by explicit choice. '
        + 'Keep this file private.',
    };
    return pack;
  }

  const campaign = pack.campaign;
  if (campaign && typeof campaign === 'object') {
    for (const key of ['signatory', 'contact_details']) {
      if (typeof campaign[key] === 'string' && campaign[key]) campaign[key] = REDACTED;
    }
    if (Array.isArray(campaign.communications)) {
      campaign.communications = campaign.communications.map(row => ({
        ...row,
        counterparty: row.counterparty ? REDACTED : row.counterparty,
        subject: row.subject ? REDACTED : row.subject,
        content: row.content ? REDACTED : row.content,
        evidence_links: [],
      }));
    }
  }

  if (typeof pack.markdown === 'string' && campaign?.communications?.length) {
    pack.markdown = redactCommunicationMarkdown(pack.markdown) ?? PRIVATE_PACK_NOTICE;
  }
  if (typeof pack.document_edits?.markdown === 'string') {
    pack.document_edits.markdown = '[Edited document text omitted from this redacted export.]';
  }
  pack.export_privacy = {
    campaign_private_details: 'redacted',
    notice: PRIVATE_PACK_NOTICE,
  };
  return pack;
}

export function documentMarkdown(report) {
  const content = report.document_edits?.markdown ?? report.document_markdown ?? report.markdown ?? '';
  const marker = '**INCOMPLETE MODEL DRAFT — review the partial text.**';
  return report.incomplete && !content.trimStart().startsWith(marker)
    ? marker + '\n\n' + content : content;
}

/** An unchanged open editor can export; changed wording needs an explicit choice. */
export function hasUnappliedDocumentEdits(current, text, open) {
  return open === true && text !== current;
}

export function plainDocument(value) {
  // Read a detached, safe DOM tree. Copying never exposes Markdown escapes or markup.
  const node = markdown(value);
  function text(element) {
    if (element.nodeType === Node.TEXT_NODE) return element.textContent;
    if (element.className?.split(/\s+/).includes('document-page-break')) return '';
    if (element.tagName === 'BR') return '\n';
    if (element.tagName === 'PRE') return element.textContent;
    if (element.tagName === 'UL' || element.tagName === 'OL') {
      return [...element.children].map((item, at) => {
        const marker = element.tagName === 'OL' ? `${element.start + at}. ` : '• ';
        const content = [...item.childNodes].map(text).join('\n');
        return marker + content.replaceAll('\n', '\n' + ' '.repeat(marker.length));
      }).join('\n');
    }
    if (element.tagName === 'TABLE') {
      return [...element.rows].map(row => [...row.cells].map(cell => {
        const value = text(cell);
        // Quoted TSV preserves multiline cells when pasted into a spreadsheet.
        return /[\t\n"]/.test(value) ? '"' + value.replaceAll('"', '""') + '"' : value;
      }).join('\t')).join('\n');
    }
    const separator = ['DIV', 'BLOCKQUOTE', 'LI'].includes(element.tagName) ? '\n\n' : '';
    const content = [...element.childNodes].map(text).join(separator);
    if (element.tagName === 'A' && content !== element.href) return `${content} (${element.href})`;
    return content;
  }
  return text(node);
}

function escape(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

export function documentExportStyles(report) {
  const shared = 'h1,h2,h3,h4{font-family:system-ui,sans-serif;line-height:1.25}h1{font-size:30px}h2{font-size:23px;margin-top:1.6em}h3{font-size:18px}p{margin:0 0 1em}li{margin:.35em 0}'
    + 'blockquote{margin:1em 0;padding-left:18px;border-left:3px solid #b59a54}pre{white-space:pre-wrap;background:#f5f5f1;padding:18px}code{font-size:.9em}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:8px;text-align:left}.align-center{text-align:center}.align-right{text-align:right}.table-scroll{overflow-x:auto;margin:1em 0}li>p{margin:.35em 0}a{color:#245989}'
    + '.status{font:11px system-ui,sans-serif;letter-spacing:.08em;color:#626b72;text-transform:uppercase;margin-bottom:28px}.document{overflow-wrap:anywhere}'
    + '.document-page-break{border-top:1px dashed #ccc;margin:1.5em 0;padding-top:.5em;color:#626b72;font:11px system-ui,sans-serif}'
    + '@media print{.document-page-break{break-after:page;page-break-after:always;height:0;margin:0;padding:0;border:0;font-size:0;color:transparent}}'
    + '@media(max-width:650px){.sheet{margin:0;padding:28px 22px;border:0}}@media print{body{background:white}.sheet{margin:0;padding:0;border:0}.status{font-size:9px}.table-scroll{overflow:visible}h1,h2,h3,h4{break-after:avoid}tr{break-inside:avoid}}';
  if (report.workflow !== 'campaign') {
    return 'body{margin:0;background:#f3f2ed;color:#202a35;font:17px/1.65 Georgia,serif}.sheet{max-width:720px;margin:40px auto;padding:55px 64px;background:white;border:1px solid #deded6}'
      + shared;
  }
  return 'body{margin:0;background:#f3f2ed;color:#202a35;font:14.56px/1.62 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.sheet{max-width:820px;margin:40px auto;padding:0;background:white;border:1px solid #deded6}'
    + shared
    + '.status{padding:28px 40px 0;margin:0;font-size:10px;letter-spacing:.14em;font-weight:700}.campaign-decision-document{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14.56px;line-height:1.62;padding:26px clamp(22px,4vw,40px) 36px}.campaign-decision-document h1{font-size:24.8px;line-height:1.24;margin:0 0 1em}.campaign-decision-document h2{font-size:18px;margin:1.5em 0 .55em}.campaign-decision-document h3{font-size:15.7px;margin:1.3em 0 .45em}.campaign-decision-document p{margin:0 0 .75em}.campaign-decision-document ul,.campaign-decision-document ol{margin:.5em 0 .9em}.campaign-decision-document li{margin:.24em 0}'
    + '@media(max-width:650px){.sheet{padding:0}.status{padding:20px 22px 0}.campaign-decision-document{padding:20px 22px 28px}}'
    + '@media print{body{font:11pt/1.55 Georgia,"Times New Roman",serif}.sheet{max-width:none;margin:0;padding:0;border:0}.status{display:none}.campaign-decision-document{font:11pt/1.55 Georgia,"Times New Roman",serif;padding:0}}';
}

export function documentHtml(report) {
  const body = markdown(documentMarkdown(report));
  if (report.workflow === 'campaign') body.classList.add('campaign-decision-document');
  const title = report.document_title || report.title || 'Sinter draft';
  // Only nodes constructed by our safe renderer enter this self-contained document.
  return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
    + '<title>' + escape(title) + '</title><style>' + documentExportStyles(report)
    + '</style></head><body><article class="sheet"><div class="status">' + (report.demo ? 'Fictional example · ' : '')
    + (report.workflow === 'campaign' ? 'Campaign decision record'
      : report.incomplete ? 'Incomplete model draft · Review partial text'
        : report.model_draft ? 'Model-generated draft · Review before use' : 'Draft · Review before use') + '</div>'
    + body.outerHTML + '</article></body></html>';
}

export function downloadDocument(report) {
  const html = documentHtml(report);
  const title = report.document_title || report.title || 'Sinter draft';
  download(reportName(title) + '.html', html, 'text/html;charset=utf-8');
}

/** Shared copy, readable export and explicit editing for every kind of document. */
export function documentActions(report, {onChange = () => {}, onEditorChange = () => {}, editorSeed, save} = {}) {
  const isCampaign = report.workflow === 'campaign';
  const feedback = h('div', {class: 'document-feedback', 'aria-live': 'polite'});
  const editor = h('div', {class: 'document-editor non-print', hidden: !editorSeed?.open});
  const privateExport = isCampaign
    ? check('Include full communication records and personal contact details '
      + 'in this download', false)
    : null;
  const word = button(isCampaign ? 'Download Word brief (.docx)' : 'Download Word (.docx)', async () => {
    if (!canUseDocument()) return;
    word.disabled = true;
    try {
      const content = await request('/api/documents/docx', {data: {title: report.document_title || report.title || 'Sinter draft', markdown: documentMarkdown(report)}, responseType: 'blob'});
      download(reportName(report.document_title || report.title || 'Sinter draft') + '.docx', content, content.type);
      feedback.replaceChildren(h('p', {class: 'copy-confirmation'}, 'Word document downloaded. Open it to keep editing.')); announce('Word document downloaded.');
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    finally { word.disabled = false; }
  });
  const input = field(isCampaign ? 'Edit the decision brief' : 'Edit your draft', 'textarea', editorSeed?.text || '', 'Apply edits, then save the draft to keep them after closing Sinter. Use Insert page break at your cursor to start the following content on a new exported page. The original output and source evidence are retained.', {rows: 18, maxLength: 500000});
  function canUseDocument(operation = 'copying, downloading or printing') {
    if (!hasUnappliedDocumentEdits(documentMarkdown(report), input.input.value, !editor.hidden)) return true;
    const message = `Apply or cancel your pending draft edits before ${operation}. Your text is still in the editor.`;
    feedback.replaceChildren(notice(message, 'error'));
    input.input.focus(); announce(message);
    return false;
  }
  input.input.addEventListener('input', () => onEditorChange(input.input.value, true));
  const edit = button(isCampaign ? 'Edit decision brief' : 'Edit draft', () => { if (editor.hidden) input.input.value = documentMarkdown(report); editor.hidden = false; input.input.focus(); }, 'quiet');
  const apply = button('Apply edits', () => {
    if (!input.input.value.trim()) { feedback.replaceChildren(notice('Keep some document text, or cancel to retain the current draft.', 'error')); return; }
    if (input.input.value.length > input.input.maxLength) { feedback.replaceChildren(notice('Keep this draft under 500,000 characters before applying edits.', 'error')); return; }
    report.document_edits = {markdown: input.input.value, edited_at: new Date().toISOString(), author: 'user'};
    editor.hidden = true; onChange(); feedback.replaceChildren(notice('Edits applied. Save this draft to keep them.', 'success')); announce('Draft updated. Original evidence retained.'); exports.querySelector('summary').focus();
  }, 'primary');
  const pageBreak = button('Insert page break', () => {
    const inserted = insertDocumentPageBreak(input.input.value, input.input.selectionStart);
    if (inserted.text.length > input.input.maxLength) {
      feedback.replaceChildren(notice('Keep this draft under 500,000 characters before inserting a page break. Your text is unchanged.', 'error'));
      return;
    }
    // A marker inside a literal code block cannot become a page boundary.
    // Use the same safe renderer as the document instead of a second lexer.
    const boundaries = text => markdown(text).querySelectorAll('.document-page-break').length;
    if (boundaries(inserted.text) !== boundaries(input.input.value) + 1) {
      feedback.replaceChildren(notice('Place the cursor between document paragraphs, outside code or quoted text, before inserting a page break. Your text is unchanged.', 'error'));
      input.input.focus();
      return;
    }
    input.input.value = inserted.text;
    input.input.focus(); input.input.setSelectionRange(inserted.cursor, inserted.cursor);
    onEditorChange(input.input.value, true);
    feedback.replaceChildren(notice('Page break inserted. Apply edits, then save the draft to keep it.'));
    announce('Page break inserted at your cursor. Apply edits to use it.');
  }, 'quiet');
  editor.append(input.wrap, h('div', {class: 'button-row'}, apply, pageBreak, button('Cancel edits', () => { editor.hidden = true; onEditorChange('', false); exports.querySelector('summary').focus(); })));
  const evidencePack = button(
    isCampaign ? 'Download redacted evidence pack' : 'Download evidence pack', () => {
    if (!canUseDocument()) return;
    const includedPrivate = Boolean(privateExport?.input.checked);
    const content = evidencePackForDownload(report, {includePrivate: includedPrivate});
    download(reportName(report.title) + '.json',
      JSON.stringify(content, null, 2), 'application/json');
    if (includedPrivate && privateExport) {
      privateExport.input.checked = false;
      evidencePack.textContent = 'Download redacted evidence pack';
      feedback.replaceChildren(notice(
        'Downloaded with private campaign details. Keep this file private; '
          + 'Sinter did not transmit it.', 'warning'));
    }
  });
  if (privateExport) privateExport.input.addEventListener('change', () => {
    evidencePack.textContent = privateExport.input.checked
      ? 'Download evidence pack with private details' : 'Download redacted evidence pack';
  });
  const exports = h('details', {class: 'export-menu'}, h('summary', {class: 'button'}, 'More options'),
    h('div', {class: 'export-options'},
      privateExport ? h('div', {class: 'private-export-choice'}, privateExport.wrap,
        h('small', {}, 'Off by default. The redacted file omits message text, subjects, '
          + 'contact names and evidence links, plus signatory and contact details. '
          + 'Edited document text is also omitted. Applicant evidence, objectives, '
          + 'answers, budget, action owners and source notes may still contain '
          + 'user-entered personal or sensitive details. Review the whole file '
          + 'before sharing. Sinter downloads it to your device and does not '
          + 'transmit it; the saved campaign is unchanged.')) : null,
      button(isCampaign ? 'Download decision brief' : 'Download document', () => { if (canUseDocument()) downloadDocument(report); }),
      button(isCampaign ? 'Download Markdown brief' : 'Download Markdown', () => { if (canUseDocument()) download(reportName(report.title) + '.md', documentMarkdown(report), 'text/markdown;charset=utf-8'); }),
      evidencePack,
      button('Print / save PDF', () => { if (canUseDocument()) window.print(); }), edit));
  exports.addEventListener('click', event => { if (event.target.closest('button')) exports.open = false; });
  exports.addEventListener('keydown', event => {
    if (event.key === 'Escape' && exports.open) { event.preventDefault(); exports.open = false; exports.querySelector('summary').focus(); }
  });
  const controls = h('div', {class: 'document-toolbar non-print'},
    h('div', {class: 'button-row'}, button(isCampaign ? 'Copy decision brief' : 'Copy draft text', async () => {
      if (!canUseDocument()) return;
      try { await navigator.clipboard.writeText(plainDocument(documentMarkdown(report))); feedback.replaceChildren(h('p', {class: 'copy-confirmation'}, isCampaign
        ? 'Copied. Review the internal decision brief for accuracy and privacy before sharing.'
        : report.incomplete ? 'Incomplete draft copied. Review the partial text before using it.'
          : 'Copied. Ready to paste into your email or document.')); announce(isCampaign ? 'Decision brief copied.' : report.incomplete ? 'Incomplete draft text copied.' : 'Draft text copied.'); }
      catch { feedback.replaceChildren(notice('Clipboard access is unavailable. Download the document instead.', 'error')); }
    }, 'primary'), word, save || null, exports));
  return {controls, feedback, editor, canUseDocument};
}
