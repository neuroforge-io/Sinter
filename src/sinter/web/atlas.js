/** Optional knowledge tools; selected data never leaves this app without consent. */
import {h, field, check, button, notice, markdown, download, announce, safeLink} from './ui.js';
import {request, waitForJob} from './api.js';

export function atlasPage({setBusy, remember, seed = {}}) {
  let document = seed.document || null, job = null;
  const question = field('What would you like to find out?', 'text', seed.question || '', 'Use names and terms likely to occur in your sources.', {maxLength: 2000});
  const input = field('Import an RKC atlas or context packet', 'file', '', 'Choose bundle.json or an RKC context JSON export. Up to 4 MB; no paths or scripts inside it are executed.', {accept: '.json,application/json'});
  const summary = h('div', {'aria-live': 'polite'}, notice('Start with an exported atlas, or connect to RKC running on this computer.'));
  const result = h('section', {'aria-label': 'Knowledge results', class: 'stack'});
  const consent = check('Send selected source excerpts and my question to my configured Fracture API for an unverified draft.');
  const root = h('div', {class: 'stack'});
  const controls = [];
  const rememberNow = () => remember('atlas', {title: 'Knowledge atlas', document, question: question.input.value});
  question.input.addEventListener('input', rememberNow);
  async function accept(value) {
    const info = await request('/api/atlas/inspect', {data: {document: value}});
    document = value; rememberNow();
    summary.replaceChildren(notice(`${info.item_count} indexed items. Snapshot: ${info.snapshot_id}. Producer integrity: ${info.producer_integrity}.`),
      h('details', {}, h('summary', {}, 'Provenance and limitations'), ...info.warnings.map(w => h('p', {}, w))));
    result.replaceChildren();
  }
  async function task(action) {
    controls.forEach(b => { b.disabled = true; }); setBusy(true);
    try { await action(); }
    catch (error) { result.replaceChildren(notice(error.message, 'error')); }
    finally { controls.forEach(b => { b.disabled = false; }); setBusy(false); job = null; }
  }
  function show(value) {
    result.replaceChildren(value.review_status === 'unverified_model_draft' ? notice('AI draft, not verified. Check every claim against the cited material.') : notice('Source packet only. No factual answer has been inferred.'),
      h('div', {class: 'button-row'}, button('Download context JSON', () => download('sinter-atlas-context.json', JSON.stringify(value, null, 2), 'application/json')),
        button('Download Markdown', () => download('sinter-atlas-context.md', value.markdown))), markdown(value.markdown));
    announce('Knowledge context ready for review.');
  }
  input.input.addEventListener('change', () => task(async () => {
    const file = input.input.files[0];
    if (!file || file.size > 4194304) throw new Error('Choose a JSON export smaller than 4 MB.');
    await accept(JSON.parse(await file.text()));
  }));
  const search = button('Find supporting material', () => task(async () => {
    if (!document) throw new Error('Import an atlas or read a local RKC context packet first.');
    show(await request('/api/atlas/context', {data: {document, question: question.input.value}}));
  }), 'primary');
  const local = button('Read context from local RKC', () => task(async () => {
    const value = await request('/api/atlas/retrieve', {data: {question: question.input.value}});
    await accept(value.document); show(await request('/api/atlas/context', {data: {document, question: question.input.value}}));
  }), 'quiet');
  const draft = button('Draft with Fracture', () => task(async () => {
    if (!document || !consent.input.checked) throw new Error('Import sources and approve the excerpt transfer before generating a draft.');
    job = (await request('/api/atlas/answer', {data: {document, question: question.input.value, consent: true}})).id;
    show(await waitForJob(job, status => { result.replaceChildren(notice(status.message || 'Preparing a draft...')); }));
  }));
  const cancel = button('Cancel current knowledge task', async () => {
    if (job) await request('/api/jobs/cancel', {data: {id: job}}).catch(error => result.replaceChildren(notice(error.message, 'error')));
  }, 'quiet');
  const files = field('Text files for a new atlas', 'file', '', 'Selected files only; maximum 60 files and 500 KB combined. RKC must be installed separately.', {multiple: true, accept: '.txt,.md,.json,.csv,.py,.js,.ts'});
  const compileConsent = check('Run my installed RKC to compile these selected files locally.');
  const compile = button('Create an atlas from these files', () => task(async () => {
    const chosen = [...files.input.files];
    if (!compileConsent.input.checked) throw new Error('Confirm local RKC compilation first.');
    if (!chosen.length || chosen.length > 60 || chosen.reduce((sum, file) => sum+file.size, 0) > 500000) throw new Error('Select 1 to 60 text files totalling at most 500 KB.');
    const rows = await Promise.all(chosen.map(async file => ({name: file.name, content: await file.text()})));
    job = (await request('/api/atlas/compile', {data: {files: rows, consent: true}})).id;
    const output = await waitForJob(job, status => { result.replaceChildren(notice(status.message || 'Compiling locally...')); });
    await accept(output.document);
    result.append(notice('RKC produced this bundle locally. Download it to keep it.'), button('Download RKC bundle', () => download('bundle.json', JSON.stringify(document, null, 2), 'application/json')));
  }));
  controls.push(search, local, draft, compile, input.input, files.input);
  root.append(h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'OPTIONAL RKC CONNECTION'), h('h2', {}, 'Make your shared knowledge useful.'),
    h('p', {}, 'Find source material across an atlas. Create a cited context pack, or ask Fracture for a clearly labelled draft.')),
    h('div', {class: 'card'}, input.wrap, summary, question.wrap, h('div', {class: 'button-row'}, search, local), consent.wrap,
      h('div', {class: 'button-row'}, draft, cancel)),
    h('details', {class: 'card'}, h('summary', {}, 'Create a new atlas with an installed RKC'), files.wrap, compileConsent.wrap, compile,
      h('p', {}, 'Set the absolute RKC executable path in Settings. RKC controls its own compilation and resource limits. No model is needed to compile.'),
      safeLink('https://github.com/neuroforge-io/RKC', 'RKC installation and documentation')),
    result);
  if (document) accept(document).catch(error => summary.replaceChildren(notice(error.message, 'error')));
  return root;
}
