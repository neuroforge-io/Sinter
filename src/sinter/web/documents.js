/** A usable document is separate from the immutable evidence that produced it. */
import {h, button, field, markdown, download, reportName, notice, announce} from './ui.js';
import {request} from './api.js';

export function documentMarkdown(report) {
  return report.document_edits?.markdown ?? report.document_markdown ?? report.markdown ?? '';
}

export function plainDocument(value) {
  // Read a detached, safe DOM tree. Copying never exposes Markdown escapes or markup.
  const node = markdown(value);
  function text(element) {
    if (element.nodeType === Node.TEXT_NODE) return element.textContent;
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

export function downloadDocument(report) {
  const body = markdown(documentMarkdown(report));
  const title = report.document_title || report.title || 'Sinter draft';
  // Only nodes constructed by our safe renderer enter this self-contained document.
  const html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
    + '<title>' + escape(title) + '</title><style>'
    + 'body{margin:0;background:#f3f2ed;color:#202a35;font:17px/1.65 Georgia,serif}.sheet{max-width:720px;margin:40px auto;padding:55px 64px;background:white;border:1px solid #deded6}'
    + 'h1,h2,h3,h4{font-family:system-ui,sans-serif;line-height:1.25}h1{font-size:30px}h2{font-size:23px;margin-top:1.6em}h3{font-size:18px}p{margin:0 0 1em}li{margin:.35em 0}'
    + 'blockquote{margin:1em 0;padding-left:18px;border-left:3px solid #b59a54}pre{white-space:pre-wrap;background:#f5f5f1;padding:18px}code{font-size:.9em}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:8px;text-align:left}.align-center{text-align:center}.align-right{text-align:right}.table-scroll{overflow-x:auto;margin:1em 0}li>p{margin:.35em 0}a{color:#245989}'
    + '.status{font:11px system-ui,sans-serif;letter-spacing:.08em;color:#626b72;text-transform:uppercase;margin-bottom:28px}.document{overflow-wrap:anywhere}'
    + '@media(max-width:650px){.sheet{margin:0;padding:28px 22px;border:0}}@media print{body{background:white}.sheet{margin:0;padding:0;border:0}.status{font-size:9px}.table-scroll{overflow:visible}h1,h2,h3,h4{break-after:avoid}tr{break-inside:avoid}}'
    + '</style></head><body><article class="sheet"><div class="status">' + (report.demo ? 'Fictional example · ' : '')
    + (report.model_draft ? 'Model-generated draft · Review before use' : 'Draft · Review before use') + '</div>'
    + body.outerHTML + '</article></body></html>';
  download(reportName(title) + '.html', html, 'text/html;charset=utf-8');
}

/** Shared copy, readable export and explicit editing for every kind of document. */
export function documentActions(report, {onChange = () => {}, save} = {}) {
  const feedback = h('div', {class: 'document-feedback', 'aria-live': 'polite'});
  const editor = h('div', {class: 'document-editor non-print', hidden: true});
  const word = button('Download Word (.docx)', async () => {
    word.disabled = true;
    try {
      const content = await request('/api/documents/docx', {data: {title: report.document_title || report.title || 'Sinter draft', markdown: documentMarkdown(report)}, responseType: 'blob'});
      download(reportName(report.document_title || report.title || 'Sinter draft') + '.docx', content, content.type);
      feedback.replaceChildren(h('p', {class: 'copy-confirmation'}, 'Word document downloaded. Open it to keep editing.')); announce('Word document downloaded.');
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    finally { word.disabled = false; }
  });
  const input = field('Edit your draft', 'textarea', '', 'Changes are saved with the draft. The original output and source evidence are retained.', {rows: 18, maxLength: 500000});
  const edit = button('Edit draft', () => { input.input.value = documentMarkdown(report); editor.hidden = false; input.input.focus(); }, 'quiet');
  const apply = button('Apply edits', () => {
    if (!input.input.value.trim()) { feedback.replaceChildren(notice('Keep some document text, or cancel to retain the current draft.', 'error')); return; }
    if (input.input.value.length > input.input.maxLength) { feedback.replaceChildren(notice('Keep this draft under 500,000 characters before applying edits.', 'error')); return; }
    report.document_edits = {markdown: input.input.value, edited_at: new Date().toISOString(), author: 'user'};
    editor.hidden = true; onChange(); feedback.replaceChildren(notice('Edits applied. Save this draft to keep them.', 'success')); announce('Draft updated. Original evidence retained.'); exports.querySelector('summary').focus();
  }, 'primary');
  editor.append(input.wrap, h('div', {class: 'button-row'}, apply, button('Cancel edits', () => { editor.hidden = true; exports.querySelector('summary').focus(); })));
  const exports = h('details', {class: 'export-menu'}, h('summary', {class: 'button'}, 'More options'),
    h('div', {class: 'export-options'},
      button('Download document', () => downloadDocument(report)),
      button('Download Markdown', () => download(reportName(report.title) + '.md', documentMarkdown(report), 'text/markdown;charset=utf-8')),
      button('Download evidence pack', () => download(reportName(report.title) + '.json', JSON.stringify(report, null, 2), 'application/json')),
      button('Print / save PDF', () => window.print()), edit));
  exports.addEventListener('click', event => { if (event.target.closest('button')) exports.open = false; });
  exports.addEventListener('keydown', event => {
    if (event.key === 'Escape' && exports.open) { event.preventDefault(); exports.open = false; exports.querySelector('summary').focus(); }
  });
  const controls = h('div', {class: 'document-toolbar non-print'},
    h('div', {class: 'button-row'}, button('Copy draft text', async () => {
      try { await navigator.clipboard.writeText(plainDocument(documentMarkdown(report))); feedback.replaceChildren(h('p', {class: 'copy-confirmation'}, 'Copied. Ready to paste into your email or document.')); announce('Draft text copied.'); }
      catch { feedback.replaceChildren(notice('Clipboard access is unavailable. Download the document instead.', 'error')); }
    }, 'primary'), word, save || null, exports));
  return {controls, feedback, editor};
}
