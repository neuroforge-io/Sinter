import {h, button, check, field, selectField, notice, markdown, safeLink, announce, download} from './ui.js';
import {request, stream} from './api.js';
import {senderFields, senderContext} from './profile.js';
import {renderReport} from './reports.js';
import {campaignAssistant} from './assistant.js';

/** Free-form model output is deliberately separate from evidence-only reports. */
export async function playground({setBusy, seed = {}, remember, pageId = "explore", onUseSearchResults}) {
  const preferences = await request('/api/settings');
  const mode = selectField('Tool', [['assistant', 'Campaign assistant'], ['chat', 'Chat with your model'], ['search', 'Search the web'], ['templates', 'Multi-step templates']], seed.mode || 'assistant');
  const view = h('div');
  const root = h('div', {}, h('header', {class: 'page-intro'}, h('h2', {}, pageId === 'search' ? 'Find a source. Keep the evidence.' : 'From your context to a useful draft.'),
    h('p', {}, pageId === 'search' ? 'Search a public topic, inspect the links, then bring useful snippets into a research brief.' : 'Write, summarise, research or ask a question. Your source material stays visible alongside the result.')),
    h('p', {class: 'workspace-hint'}, pageId === 'search' ? 'Only your search query is sent. Search snippets are not verified source facts.' : globalThis.sinterBrowser ? 'The public native model supports short text. Optional Sinter-managed search lets it request one approved public lookup; native function-calling is not supported.' : 'Uses your configured model service. Review the result before using it.'), mode.wrap, view);
  mode.wrap.hidden = pageId === 'search';
  const history = [];
  const templateDrafts = new Map();
  let lastTemplate = seed.template || 'enquiry-letter', senderDraft = seed;
  let active = false, controller;
  const assistantBusy = value => { mode.input.disabled = value; setBusy(value); };
  async function execute(path, data, onEvent, done) {
    if (active) return;
    active = true; mode.input.disabled = true; setBusy(true); controller = new AbortController();
    try { await stream(path, data, onEvent, controller.signal); done?.(); }
    catch (error) { view.append(notice(error.name === 'AbortError' ? 'Stopped. Partial output is not complete.' : error.message, 'error')); }
    finally { active = false; mode.input.disabled = false; setBusy(false); controller = null; announce('Request finished. Review the output and any errors.'); }
  }
  function chatView() {
    const log = h('div', {class: 'chat-log', 'aria-label': 'Conversation'});
    const input = field('Your message', 'textarea', '', 'Your message and this conversation are sent to the model service. Avoid sensitive information.', {required: true, maxLength: 12000, rows: 3});
    const searchPermit = check('Let the model request web search for this question');
    const searchTopic = field('Public search topic', 'text', '', 'This exact topic may be sent to public web search. Edit it to remove personal or confidential details. Private project documents are never added automatically.', {minLength:3,maxLength:160});
    searchTopic.wrap.hidden = true;
    let topicEdited = false;
    searchTopic.input.addEventListener('input', () => { topicEdited = true; });
    input.input.addEventListener('input', () => { if (!topicEdited) searchTopic.input.value = input.input.value.trim().length <= 160 ? input.input.value.trim() : ''; });
    searchPermit.input.addEventListener('change', () => { searchTopic.wrap.hidden = !searchPermit.input.checked; searchTopic.input.required = searchPermit.input.checked; });
    const toolHelp = h('p', {class:'fine'}, 'Sinter-managed tool: the model chooses SEARCH or ANSWER. At most one web lookup and two model calls. Search-assisted answers use a bounded snippet pack; sources and failures stay visible.');
    const form = h('form', {class: 'card'}, input.wrap,
      ...(globalThis.sinterBrowser ? [searchPermit.wrap,searchTopic.wrap,toolHelp] : []),
      h('div', {class: 'button-row'}, h('button', {type: 'submit', class: 'button primary'}, 'Send message'),
        button('Stop', () => controller?.abort()), button('Clear conversation', () => { if (!active) { history.length = 0; log.replaceChildren(); } })));
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (active || !input.input.value.trim()) return;
      const content = input.input.value.trim();
      if (globalThis.sinterBrowser && searchPermit.input.checked && !searchTopic.input.reportValidity()) return;
      const messages = [...history, {role: 'user', content}];
      if (messages.length > 63 || messages.reduce((size, item) => size + item.content.length, 0) > 64000) {
        log.append(notice('This conversation reached the context limit. Start a new conversation; context is never silently dropped.', 'error')); return;
      }
      log.append(h('article', {class: 'chat-entry user'}, h('div', {class: 'chat-role'}, 'You'), h('p', {}, content)));
      const body = h('div');
      log.append(h('article', {class: 'chat-entry'}, h('div', {class: 'chat-role'}, 'Model / unverified'), body));
      let full = '', scheduled = false;
      input.input.disabled = true;
      await execute('/api/chat/stream', {messages, max_tokens: preferences.settings.max_tokens,
        ...(globalThis.sinterBrowser && searchPermit.input.checked ? {allow_search:true, approved_search_query:searchTopic.input.value.trim()} : {})}, event => {
        if (event.type === 'search_tool') {
          const failed = ['unavailable','no_answer','citation_warning'].includes(event.status);
          const item = h('article', {class:'chat-entry'}, h('div',{class:'chat-role'},'Sinter-managed search'),
            notice(event.message, failed?'warning':''), event.query ? h('p',{},'Query: '+event.query) : null,
            event.notice ? notice(event.notice,'warning') : null,
            event.elapsed_ms ? h('p',{class:'fine'},'Elapsed: '+(event.elapsed_ms/1000).toFixed(1)+' seconds') : null,
            ...(event.sources || []).map(source=>h('div',{class:'source'},safeLink(source.url,`[${source.citation}] ${source.title}`),h('p',{},source.content))));
          if (event.sources?.length && onUseSearchResults) item.append(button('Use these sources in a research brief',()=>onUseSearchResults({query:event.query,result:{retrieved_at:event.retrieved_at,results:event.sources}}),'quiet'));
          log.append(item);
        }
        if (event.type === 'token') {
          full += event.t;
          if (!scheduled) { scheduled = true; requestAnimationFrame(() => { body.replaceChildren(markdown(full)); scheduled = false; }); }
        }
      }, () => { if (full.trim()) { history.push({role: 'user', content}, {role: 'assistant', content: full}); input.input.value = ''; if (!topicEdited) searchTopic.input.value = ''; } });
      input.input.disabled = false;
    });
    view.replaceChildren(log, form);
  }
  function searchView() {
    const query = field('Search query', 'text', seed.query || '', 'Use a public topic, organisation or place: 3–160 characters, at most 24 words. Avoid personal or confidential details.', {required: true, minLength: 3, maxLength: 160});
    const output = h('div', {class: 'stack'});
    const submit = h('button', {type: 'submit', class: 'button primary'}, 'Search');
    const form = h('form', {class: 'card'}, query.wrap, submit);
    const keep = (result) => remember?.(pageId, {mode: 'search', query: query.input.value, ...(result ? {searchResult: result} : {})}, {dirty: false});
    function render(result, searched) {
      const partial = result.source_status === 'partial' || result.source_status === 'related';
      output.replaceChildren(...[h('p', {class: 'muted'}, 'Search: ' + searched + ' · Retrieved: ' + (result.retrieved_at || 'Not supplied')),
        result.notice ? notice(result.notice, partial ? 'warning' : '') : partial ? notice('Some sources could not be checked. Results may be incomplete.', 'warning') : null,
        ...result.results.map((item, index) => h('article', {class: 'card'}, h('h3', {}, safeLink(item.url, `[${index + 1}] ${item.title}`)), h('p', {}, item.content), h('p', {class:'fine'}, item.url)))].filter(Boolean));
      if (!result.results.length) output.append(notice('No usable results came back for this query. This does not show that the organisation or information is absent. Try its full name and location, or add an original source to your project.', 'warning'));
      else output.append(notice('These are search snippets. Open the originals and check their date and relevance before relying on them.'),
        h('div', {class:'button-row'}, onUseSearchResults ? button('Use these sources in a research brief', () => onUseSearchResults({query: searched, result}), 'primary') : null,
          button('Download search results', () => download('sinter-search-results.json', JSON.stringify({query: searched, ...result}, null, 2), 'application/json'), 'quiet')));
    }
    query.input.addEventListener('input', () => keep());
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (active) return;
      const searched = query.input.value.trim();
      active = true; setBusy(true); mode.input.disabled = true; submit.disabled = true; query.input.disabled = true; output.replaceChildren(notice('Searching public sources…'));
      try {
        const result = await request('/api/search', {data: {query: searched}});
        render(result, searched); keep(result);
      } catch (error) { output.replaceChildren(notice(error.message, 'error')); }
      finally { active = false; setBusy(false); mode.input.disabled = false; submit.disabled = false; query.input.disabled = false; }
    });
    view.replaceChildren(form, output);
    if (seed.searchResult?.results) render(seed.searchResult, seed.query || 'Previous query');
  }
  async function templateView() {
    const {templates} = await request('/api/templates');
    if (mode.input.value !== 'templates') return;
    const choice = selectField('Template', templates.map(template => [template.id, template.name]), lastTemplate);
    const fields = h('div'), output = h('div', {class: 'template-output'});
    const sender = senderFields(senderDraft, preferences.settings);
    let inputs = {}, selected, prepared, previewButton, submit, previewRevision = 0;
    const transmission = h('div', {class: 'stack'});
    const approval = check('I approve sending exactly this selected material to the displayed model service.');
    function variablesNow() {
      const values = Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value]));
      if (!sender.panel.hidden) values.sender = senderContext(sender.values());
      return values;
    }
    function invalidatePreview() {
      previewRevision++;
      prepared = null; approval.input.checked = false;
      transmission.replaceChildren();
      approval.wrap.hidden = !selected?.compact_source;
      if (previewButton) previewButton.hidden = !selected?.compact_source;
      if (submit) submit.disabled = !!selected?.compact_source;
    }
    function rememberInput() {
      templateDrafts.set(choice.input.value, Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value])));
      lastTemplate = choice.input.value; senderDraft = sender.values();
      remember?.('explore', {mode: 'templates', template: choice.input.value, variables: Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value])), ...sender.values()});
    }
    function choose() {
      if (selected) templateDrafts.set(selected.id, Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value])));
      inputs = {}; fields.replaceChildren();
      selected = templates.find(item => item.id === choice.input.value);
      fields.append(h('p', {class: 'muted'}, selected.description));
      const defaults = {format: 'Concise bullet points', level: 'Plain language', language: 'Identify from the code', organisation: preferences.settings.organisation || ''};
      for (const variable of selected.variables) {
        const value = templateDrafts.get(selected.id)?.[variable.name] ??
          (seed.template === selected.id ? seed.variables?.[variable.name] ?? defaults[variable.name] ?? '' : defaults[variable.name] || '');
        const entry = field(variable.label, ['recipient', 'audience', 'format', 'level', 'language', 'topic'].includes(variable.name) ? 'text' : 'textarea', value, '', {maxLength: 60000, rows: ['context', 'guidelines', 'code', 'text', 'prompt'].includes(variable.name) ? 7 : 3});
        inputs[variable.name] = entry.input; fields.append(entry.wrap);
      }
      sender.panel.hidden = !['enquiry-letter', 'consultation-questions', 'newsletter'].includes(selected.id);
      invalidatePreview();
    }
    choice.input.addEventListener('change', () => { choose(); rememberInput(); }); choose();
    const stop = button('Stop', () => controller?.abort()); stop.hidden = true;
    submit = h('button', {type: 'submit', class: 'button primary'}, 'Run template');
    previewButton = button('Preview exact source request', async () => {
      const requestedRevision = previewRevision;
      previewButton.disabled = true; submit.disabled = true;
      try {
        const result = await request('/api/template/preview', {data: {template: selected.id, variables: variablesNow()}});
        if (requestedRevision !== previewRevision) return;
        prepared = result; approval.input.checked = false;
        transmission.replaceChildren(notice(result.notice),
          h('p', {}, 'Destination: ' + result.connection.api_url + ' · Model: ' + result.request.model),
          h('details', {open: true, class: 'card'}, h('summary', {}, 'Exact material selected for transmission'),
            h('pre', {class: 'plain-wrap'}, JSON.stringify(result.request, null, 2))),
          h('p', {class: 'muted'}, 'Source snapshot: ' + result.sources[0].sha256));
      } catch (error) { if (requestedRevision === previewRevision) { prepared = null; transmission.replaceChildren(notice(error.message, 'error')); } }
      finally { previewButton.disabled = false; }
    });
    approval.input.addEventListener('change', () => { submit.disabled = !prepared || !approval.input.checked; });
    invalidatePreview();
    const form = h('form', {class: 'card template-form'}, choice.wrap, fields, sender.panel,
      previewButton, transmission, approval.wrap,
      h('div', {class: 'prepare-bar'}, h('p', {class: 'run-scope'}, 'Sends the entered context and displayed sender details to your configured model service.'), submit, stop));
    const inputSummary = h('summary', {hidden: true}, 'Review or edit template inputs');
    const inputPanel = h('details', {class: 'project-inputs', open: true}, inputSummary, form);
    form.addEventListener('input', event => {
      if (event.target === choice.input) return; // Selection's change handler first loads its own fields.
      rememberInput();
      if (event.target !== approval.input) invalidatePreview();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (active) return;
      if (selected.compact_source && (!prepared || !approval.input.checked)) {
        transmission.append(notice('Preview this source request and approve its exact material first.', 'error')); return;
      }
      output.replaceChildren(); choice.input.disabled = true; submit.disabled = true; stop.hidden = false;
      const formFields = [...form.querySelectorAll('input,textarea')]; formFields.forEach(input => { input.disabled = true; });
      const progress = h('div', {class: 'template-progress', role: 'status'}, 'Starting your draft…');
      const liveBody = h('div', {class: 'template-live'}); output.append(progress, liveBody);
      let content = '', body, stepName = '', scheduled = false;
      const variables = variablesNow();
      const saved = {results: [], sources: [], complete: false, template_inputs: {template: selected.id, variables}};
      const data = {template: selected.id, variables};
      if (selected.compact_source) Object.assign(data, {context_hash: prepared.context_hash, consent: true});
      await execute('/api/template/stream', data, event => {
        if (event.type === 'step') {
          content = ''; stepName = event.name;
          progress.replaceChildren(h('span', {class: 'progress-dot'}), h('strong', {}, `Step ${saved.results.length + 1} of ${selected.steps}`), h('span', {}, event.name));
          body = h('div'); liveBody.replaceChildren(body);
        }
        if (event.type === 'token' && body) {
          content += event.t;
          if (!scheduled) { scheduled = true; requestAnimationFrame(() => { body.replaceChildren(markdown(content)); scheduled = false; }); }
        }
        if (event.type === 'step_done') { body?.replaceChildren(markdown(event.content)); saved.results.push(event); }
        if (event.type === 'step_partial') { saved.partial = event; body?.replaceChildren(notice('This step is incomplete. Later steps were not run.', 'error'), markdown(event.content)); }
        if (event.type === 'sources') saved.sources.push(event);
      }, () => { saved.complete = true; });
      if (!saved.complete && !saved.partial && content) saved.partial = {content, step: stepName, complete: false};
      if (saved.complete && saved.results.length) {
        const selectedStep = selected.output_step ?? saved.results.length - 1;
        let document = saved.results[selectedStep]?.content || saved.results.at(-1).content;
        if (selected.id === 'research' && saved.results[2]) document += '\n\n## Next actions\n\n' + saved.results[2].content;
        const subject = variables.source_title || variables.recipient || variables.topic || variables.audience || '';
        const draftTitle = (selected.name + (subject ? ' — ' + subject.trim() : '')).slice(0, 200);
        const report = {workflow: 'template', title: draftTitle, document_title: draftTitle,
          markdown: saved.results.map(item => '## ' + item.step + '\n\n' + item.content).join('\n\n'),
          document_markdown: document, model_draft: true, review_status: 'draft', created_at: new Date().toISOString(),
          model_review: selected.review_step != null ? saved.results[selected.review_step]?.content : '',
          sources: saved.sources.flatMap(event => event.sources || []).map((source, index) => ({...source, id: source.id || 'template-source-' + index, kind: source.kind || 'search_excerpt'})),
          excerpts: saved.sources.flatMap(event => event.excerpts || []), warnings: ['Model-generated. Check names, dates and claims against your original context.', ...(selected.compact_source ? ['A short selected-source answer; the complete source was not reviewed.'] : [])],
          template_run: saved, template_inputs: {template: selected.id, variables}};
        output.replaceChildren(renderReport(report)); inputSummary.hidden = false; inputPanel.open = false;
        output.scrollIntoView({block: 'start'});
      } else if (saved.results.length || saved.partial) {
        progress.textContent = 'Stopped with partial output';
        const details = h('details', {class: 'card', open: true}, h('summary', {}, 'Completed steps and partial output'));
        for (const result of saved.results) details.append(h('h3', {}, result.step), markdown(result.content));
        if (saved.partial) details.append(notice('Incomplete: ' + (saved.partial.step || stepName) + '. Dependent steps were not run.', 'error'), markdown(saved.partial.content));
        liveBody.replaceChildren(details, button('Download partial output', () => download('sinter-template-INCOMPLETE.json', JSON.stringify(saved, null, 2), 'application/json')));
      }
      choice.input.disabled = false; submit.disabled = false; stop.hidden = true;
      if (selected.compact_source) { prepared = null; approval.input.checked = false; submit.disabled = true; }
      formFields.forEach(input => { input.disabled = false; }); rememberInput();
    });
    view.replaceChildren(inputPanel, output);
  }
  mode.input.addEventListener('change', () => {
    if (mode.input.value === 'assistant') campaignAssistant({setBusy: assistantBusy}).then(page => { if (mode.input.value === 'assistant') view.replaceChildren(page); }).catch(error => view.replaceChildren(notice(error.message, 'error')));
    else if (mode.input.value === 'chat') chatView();
    else if (mode.input.value === 'search') searchView();
    else templateView().catch(error => view.replaceChildren(notice(error.message, 'error')));
  });
  if (mode.input.value === 'assistant') view.replaceChildren(await campaignAssistant({setBusy: assistantBusy}));
  else if (mode.input.value === 'templates') await templateView(); else if (mode.input.value === 'search') searchView(); else chatView();
  return root;
}
