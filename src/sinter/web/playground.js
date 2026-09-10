import {h, button, field, selectField, notice, markdown, safeLink, announce} from './ui.js';
import {request, stream} from './api.js';

/** Free-form model output is deliberately separate from evidence-only reports. */
export async function playground({setBusy}) {
  const mode = selectField('Tool', [['chat', 'Chat with Fracture'], ['search', 'Search the web'], ['templates', 'Multi-step templates']]);
  const view = h('div');
  const root = h('div', {}, h('header', {class: 'page-intro'}, h('h2', {}, 'Explore the engine.'),
    h('p', {}, 'Try the public Fracture and search APIs directly.')),
    notice('Exploration output is model-generated, not verified. It can be wrong. For official work, use the source-linked community workflows.'), mode.wrap, view);
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
      await execute('/api/chat/stream', {messages, max_tokens: 768}, event => {
        if (event.type === 'token') {
          full += event.t;
          if (!scheduled) { scheduled = true; requestAnimationFrame(() => { body.replaceChildren(markdown(full)); scheduled = false; }); }
        }
      }, () => { history.push({role: 'user', content}, {role: 'assistant', content: full}); input.input.value = ''; });
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
    const choice = selectField('Template', templates.map(template => [template.id, template.name]));
    const fields = h('div'), output = h('div', {class: 'stack'});
    let inputs = {};
    function choose() {
      inputs = {}; fields.replaceChildren();
      const template = templates.find(item => item.id === choice.input.value);
      fields.append(h('p', {}, template.description));
      for (const variable of template.variables) {
        const entry = field(variable.label, 'textarea', '', '', {maxLength: 60000, rows: 3});
        inputs[variable.name] = entry.input; fields.append(entry.wrap);
      }
    }
    choice.input.addEventListener('change', choose); choose();
    const form = h('form', {class: 'card'}, choice.wrap, fields,
      h('div', {class: 'button-row'}, h('button', {type: 'submit', class: 'button primary'}, 'Run template'), button('Stop', () => controller?.abort())));
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (active) return;
      output.replaceChildren(); choice.input.disabled = true;
      let current, content = '', body;
      await execute('/api/template/stream', {template: choice.input.value,
        variables: Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value]))}, event => {
        if (event.type === 'step') {
          content = ''; body = h('div'); current = h('article', {class: 'card'}, h('h3', {}, event.name), body); output.append(current);
        }
        if (event.type === 'token' && body) { content += event.t; body.textContent = content; }
        if (event.type === 'step_done') body?.replaceChildren(markdown(event.content));
        if (event.type === 'sources') for (const item of event.sources || []) output.append(h('p', {}, safeLink(item.url, item.title)));
      });
      choice.input.disabled = false;
    });
    view.replaceChildren(form, output);
  }
  mode.input.addEventListener('change', () => {
    if (mode.input.value === 'chat') chatView();
    else if (mode.input.value === 'search') searchView();
    else templateView().catch(error => view.replaceChildren(notice(error.message, 'error')));
  });
  chatView();
  return root;
}
