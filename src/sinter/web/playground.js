import {h, button, field, selectField, notice, markdown, safeLink, announce, download} from './ui.js';
import {request, stream} from './api.js';
import {senderFields, senderContext} from './profile.js';
import {renderReport} from './reports.js';

/** Free-form model output is deliberately separate from evidence-only reports. */
export async function playground({setBusy, seed = {}, remember}) {
  const preferences = await request('/api/settings');
  const mode = selectField('Tool', [['chat', 'Chat with Fracture'], ['search', 'Search the web'], ['templates', 'Multi-step templates']], seed.mode || 'chat');
  const view = h('div');
  const root = h('div', {}, h('header', {class: 'page-intro'}, h('h2', {}, 'From your context to a useful draft.'),
    h('p', {}, 'Write, summarise, research or ask a question. Your source material stays visible alongside the result.')),
    h('p', {class: 'workspace-hint'}, 'Uses your configured model service. Review the result before using it.'), mode.wrap, view);
  const history = [];
  let active = false, controller;
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
    const form = h('form', {class: 'card'}, input.wrap,
      h('div', {class: 'button-row'}, h('button', {type: 'submit', class: 'button primary'}, 'Send message'),
        button('Stop', () => controller?.abort()), button('Clear conversation', () => { if (!active) { history.length = 0; log.replaceChildren(); } })));
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (active || !input.input.value.trim()) return;
      const content = input.input.value.trim();
      const messages = [...history, {role: 'user', content}];
      if (messages.length > 63 || messages.reduce((size, item) => size + item.content.length, 0) > 64000) {
        log.append(notice('This conversation reached the context limit. Start a new conversation; context is never silently dropped.', 'error')); return;
      }
      log.append(h('article', {class: 'chat-entry user'}, h('div', {class: 'chat-role'}, 'You'), h('p', {}, content)));
      const body = h('div');
      log.append(h('article', {class: 'chat-entry'}, h('div', {class: 'chat-role'}, 'Fracture / unverified'), body));
      let full = '', scheduled = false;
      input.input.disabled = true;
      await execute('/api/chat/stream', {messages, max_tokens: 768}, event => {
        if (event.type === 'token') {
          full += event.t;
          if (!scheduled) { scheduled = true; requestAnimationFrame(() => { body.replaceChildren(markdown(full)); scheduled = false; }); }
        }
      }, () => { history.push({role: 'user', content}, {role: 'assistant', content: full}); input.input.value = ''; });
      input.input.disabled = false;
    });
    view.replaceChildren(log, form);
  }
  function searchView() {
    const query = field('Search query', 'text', '', 'This exact query is sent to NeuroForge search.', {required: true, maxLength: 1024});
    const output = h('div', {class: 'stack'});
    const form = h('form', {class: 'card'}, query.wrap, h('button', {type: 'submit', class: 'button primary'}, 'Search'));
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (active) return;
      active = true; setBusy(true); mode.input.disabled = true; output.replaceChildren(notice('Searching...'));
      try {
        const result = await request('/api/search', {data: {query: query.input.value}});
        output.replaceChildren(h('p', {class: 'muted'}, 'Retrieved: ' + (result.retrieved_at || 'Not supplied')),
          ...result.results.map(item => h('article', {class: 'card'}, h('h3', {}, safeLink(item.url, item.title)), h('p', {}, item.content))));
        if (!result.results.length) output.append(notice('No results returned. Try a more specific query.'));
      } catch (error) { output.replaceChildren(notice(error.message, 'error')); }
      finally { active = false; setBusy(false); mode.input.disabled = false; }
    });
    view.replaceChildren(form, output);
  }
  async function templateView() {
    const {templates} = await request('/api/templates');
    if (mode.input.value !== 'templates') return;
    const choice = selectField('Template', templates.map(template => [template.id, template.name]), seed.template || 'enquiry-letter');
    const fields = h('div'), output = h('div', {class: 'template-output'});
    const sender = senderFields(seed, preferences.settings);
    let inputs = {}, selected;
    function rememberInput() {
      remember?.('explore', {mode: 'templates', template: choice.input.value, variables: Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value])), ...sender.values()});
    }
    function choose() {
      inputs = {}; fields.replaceChildren();
      selected = templates.find(item => item.id === choice.input.value);
      fields.append(h('p', {class: 'muted'}, selected.description));
      const defaults = {format: 'Concise bullet points', level: 'Plain language', language: 'Identify from the code', organisation: preferences.settings.organisation || ''};
      for (const variable of selected.variables) {
        const value = seed.template === selected.id ? seed.variables?.[variable.name] ?? defaults[variable.name] ?? '' : defaults[variable.name] || '';
        const entry = field(variable.label, ['recipient', 'audience', 'format', 'level', 'language', 'topic'].includes(variable.name) ? 'text' : 'textarea', value, '', {maxLength: 60000, rows: ['context', 'guidelines', 'code', 'text', 'prompt'].includes(variable.name) ? 7 : 3});
        inputs[variable.name] = entry.input; fields.append(entry.wrap);
      }
      sender.panel.hidden = !['enquiry-letter', 'consultation-questions', 'newsletter'].includes(selected.id);
    }
    choice.input.addEventListener('change', () => { choose(); rememberInput(); }); choose();
    const stop = button('Stop', () => controller?.abort()); stop.hidden = true;
    const submit = h('button', {type: 'submit', class: 'button primary'}, 'Run template');
    const form = h('form', {class: 'card template-form'}, choice.wrap, fields, sender.panel,
      h('div', {class: 'prepare-bar'}, h('p', {class: 'run-scope'}, 'Sends the entered context and displayed sender details to your configured model service.'), submit, stop));
    const inputSummary = h('summary', {hidden: true}, 'Review or edit template inputs');
    const inputPanel = h('details', {class: 'project-inputs', open: true}, inputSummary, form);
    form.addEventListener('input', rememberInput);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (active) return;
      output.replaceChildren(); choice.input.disabled = true; submit.disabled = true; stop.hidden = false;
      const formFields = [...form.querySelectorAll('input,textarea')]; formFields.forEach(input => { input.disabled = true; });
      const progress = h('div', {class: 'template-progress', role: 'status'}, 'Starting your draft…');
      const liveBody = h('div', {class: 'template-live'}); output.append(progress, liveBody);
      let content = '', body, stepName = '', scheduled = false;
      const saved = {results: [], sources: [], complete: false};
      const variables = Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value]));
      if (!sender.panel.hidden) variables.sender = senderContext(sender.values());
      await execute('/api/template/stream', {template: selected.id, variables}, event => {
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
        const subject = variables.recipient || variables.topic || variables.audience || '';
        const draftTitle = (selected.name + (subject ? ' — ' + subject.trim() : '')).slice(0, 200);
        const report = {workflow: 'template', title: draftTitle, document_title: draftTitle,
          markdown: saved.results.map(item => '## ' + item.step + '\n\n' + item.content).join('\n\n'),
          document_markdown: document, model_draft: true, review_status: 'draft', created_at: new Date().toISOString(),
          model_review: selected.review_step != null ? saved.results[selected.review_step]?.content : '',
          sources: saved.sources.flatMap(event => event.sources || []).map((source, index) => ({...source, id: 'template-source-' + index, kind: 'search_excerpt'})),
          excerpts: [], warnings: ['Model-generated. Check names, dates and claims against your original context.'],
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
      formFields.forEach(input => { input.disabled = false; }); rememberInput();
    });
    view.replaceChildren(inputPanel, output);
  }
  mode.input.addEventListener('change', () => {
    if (mode.input.value === 'chat') chatView();
    else if (mode.input.value === 'search') searchView();
    else templateView().catch(error => view.replaceChildren(notice(error.message, 'error')));
  });
  if (mode.input.value === 'templates') await templateView(); else if (mode.input.value === 'search') searchView(); else chatView();
  return root;
}
