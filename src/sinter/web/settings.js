/** Settings are local. API credentials stay in process memory, never browser storage. */
import {h, field, selectField, check, button, notice, announce} from './ui.js';
import {request} from './api.js';

export function applyAppearance(settings) {
  const root = document.documentElement;
  root.dataset.theme = settings.theme;
  root.dataset.textSize = settings.text_size;
  root.dataset.density = settings.density;
  root.dataset.reduceMotion = String(settings.reduce_motion);
  const toggle = document.getElementById('theme-toggle');
  toggle.textContent = settings.theme === 'dark' ? 'Light theme' : 'Dark theme';
  toggle.setAttribute('aria-label', `Switch to ${settings.theme === 'dark' ? 'light' : 'dark'} theme`);
}

export async function settingsPage() {
  let current = await request('/api/settings');
  const s = current.settings;
  const organisation = field('Your group or organisation', 'text', s.organisation, 'A local preference; no account is created.', {maxLength: 200});
  const theme = selectField('Colour theme', [['dark', 'Dark'], ['light', 'Light']], s.theme);
  const size = selectField('Reading size', [['normal', 'Standard'], ['large', 'Larger text']], s.text_size);
  const density = selectField('Layout', [['comfortable', 'Comfortable'], ['compact', 'Compact']], s.density);
  const motion = check('Reduce movement and animation', s.reduce_motion);
  const url = field('API address', 'url', s.api_url, 'Default: NeuroForge Fracture. Remote connections must use HTTPS.');
  const model = field('Model identifier', 'text', s.model);
  const length = field('Maximum answer length', 'number', s.max_tokens,
    'Output tokens per step. The public API accepts 32–2,048; some custom providers allow up to 8,192. Small limits can leave drafts incomplete.',
    {min: 32, max: 8192, step: 1, required: true});
  function updateLengthLimit() {
    try { const parsed = new URL(url.input.value); length.input.max = parsed.hostname === 'neuroforge.io' && parsed.pathname.replace(/\/$/, '') === '/v1' ? '2048' : '8192'; }
    catch { length.input.max = '8192'; }
  }
  url.input.addEventListener('input', updateLengthLimit); updateLengthLimit();
  const key = field('Optional API key for this session', 'password', '', 'Not saved to disk. Leave untouched to retain the current session key.', {autocomplete: 'off'});
  const port = field('Local RKC port', 'number', s.rkc_port, 'For an already-running local RKC context service.', {min: 1024, max: 65535});
  const executable = field('Installed RKC executable', 'text', s.rkc_executable, 'Optional absolute path. Used only when you explicitly compile a selected collection.');
  const destination = check('I approve sending requests to the API address above.');
  const state = h('div', {'aria-live': 'polite'});
  let keyEdited = false;
  key.input.addEventListener('input', () => { keyEdited = true; });
  const save = button('Save my preferences', async () => {
    if (![url, model, port, organisation, length].every(f => f.input.reportValidity())) return;
    save.disabled = true;
    try {
      const next = {...s, organisation: organisation.input.value, theme: theme.input.value, text_size: size.input.value,
        density: density.input.value, reduce_motion: motion.input.checked, api_url: url.input.value,
        model: model.input.value, max_tokens: Number(length.input.value), rkc_port: Number(port.input.value), rkc_executable: executable.input.value};
      current = await request('/api/settings', {data: {settings: next, confirm_endpoint: destination.input.checked,
        ...(keyEdited ? {api_key: key.input.value} : {})}});
      Object.assign(s, current.settings); applyAppearance(s); key.input.value = ''; keyEdited = false;
      state.replaceChildren(notice('Preferences saved on this computer. '+(current.has_session_key ? 'A key is held for this session only.' : 'No session key is stored.'), 'success'));
      announce('Preferences saved.');
    } catch (error) { state.replaceChildren(notice(error.message, 'error')); }
    finally { save.disabled = false; }
  }, 'primary');
  const clear = button('Forget the session API key', async () => {
    try { current = await request('/api/settings', {data: {settings: s, api_key: ''}}); state.replaceChildren(notice('Session key forgotten. Environment/key-file credentials may still apply to the default NeuroForge endpoint.')); }
    catch (error) { state.replaceChildren(notice(error.message, 'error')); }
  }, 'quiet');
  return h('div', {class: 'stack'}, h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'MAKE IT YOURS'),
    h('h2', {}, 'Comfortable to read. Simple to use.'), h('p', {}, 'Choose how Sinter looks and where optional AI requests go. No account required.')),
    current.warning ? notice(current.warning, 'error') : null,
    current.environment_override ? notice('An environment variable overrides the API address or model. Change that launcher configuration to use the values below.') : null,
    h('section', {class: 'card'}, h('h3', {}, 'Your workspace'), organisation.wrap,
      h('div', {class: 'form-grid'}, theme.wrap, size.wrap, density.wrap), motion.wrap),
    h('details', {class: 'card'}, h('summary', {}, 'Advanced: API and optional RKC connection'),
      notice('Only change these when using another compatible deployment. Search may not be supported by every provider. Changing the destination clears the previous session key.'),
      url.wrap, model.wrap, length.wrap, key.wrap, destination.wrap, clear, h('hr'), port.wrap, executable.wrap),
    h('div', {class: 'button-row'}, save), state);
}
