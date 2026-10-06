import {browserSettingsPage} from './browser-settings.js';
/** Settings are local. API keys stay in process memory, never browser storage. */
import {h, field, selectField, check, button, notice, announce, safeLink} from './ui.js';
import {request} from './api.js';
import {CONNECTION_PRESETS, connectionPreset, inferConnectionPreset, connectionTokenLimits,
  connectionDestinationChanged, connectionStatus, availableModelIds} from './provider-connection.js';

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
  if (globalThis.sinterBrowser) return browserSettingsPage(applyAppearance);
  let current = await request('/api/settings');
  const s = current.settings;
  const organisation = field('Your group or organisation', 'text', s.organisation, 'A local preference; no account is created.', {maxLength: 200});
  const profile = {
    full_name: field('Your full name', 'text', s.full_name || '', '', {maxLength: 200, autocomplete: 'name'}),
    role: field('Your role', 'text', s.role || '', '', {maxLength: 200, autocomplete: 'organization-title'}),
    email: field('Email address', 'email', s.email || '', '', {maxLength: 254, autocomplete: 'email'}),
    phone: field('Phone number', 'tel', s.phone || '', '', {maxLength: 80, autocomplete: 'tel'}),
    website: field('Website', 'url', s.website || '', '', {maxLength: 2048, autocomplete: 'url'}),
    location: field('Location', 'text', s.location || '', 'Used to prefill funding searches and your organisation profile.', {maxLength: 200}),
    organisation_type: field('Organisation type', 'text', s.organisation_type || '', 'For example, incorporated association or community group.', {maxLength: 200})
  };
  const signature = h('div', {class: 'signature-preview'});
  function preview() {
    signature.replaceChildren(h('span', {class: 'eyebrow'}, 'YOUR SIGN-OFF'),
      h('strong', {}, profile.full_name.input.value || 'Add your name above'),
      ...[profile.role.input.value, organisation.input.value, profile.email.input.value, profile.phone.input.value, profile.website.input.value].filter(Boolean).map(value => h('span', {}, value)));
  }
  [organisation, ...Object.values(profile)].forEach(entry => entry.input.addEventListener('input', preview)); preview();
  const theme = selectField('Colour theme', [['dark', 'Dark'], ['light', 'Light']], s.theme);
  const size = selectField('Reading size', [['normal', 'Standard'], ['large', 'Larger text']], s.text_size);
  const density = selectField('Layout', [['comfortable', 'Comfortable'], ['compact', 'Compact']], s.density);
  const motion = check('Reduce movement and animation', s.reduce_motion);

  const route = selectField('Assistant connection', CONNECTION_PRESETS.map(preset => [preset.id, preset.label]), inferConnectionPreset(s));
  const transport = selectField('API style', [['openai-compatible', 'OpenAI-compatible chat'], ['anthropic', 'Anthropic Messages']], s.provider || 'openai-compatible');
  let provider = s.provider || 'openai-compatible';
  const url = field('API base address', 'url', s.api_url, 'Remote connections require HTTPS. Local model servers can use HTTP on this computer.', {required: true});
  const model = field('Model identifier', 'text', s.model, 'Choose a model below or enter its exact identifier. NeuroForge also accepts auto.', {required: true, maxLength: 200});
  const length = field('Maximum answer length', 'number', s.max_tokens, '', {min: 32, max: 8192, step: 1, required: true});
  const lengthHelp = h('small', {id: `${length.input.id}-help`});
  length.input.setAttribute('aria-describedby', lengthHelp.id); length.wrap.append(lengthHelp);
  const answerFields = h('div', {class: 'form-grid'}, model.wrap, length.wrap);
  const lengthExplanation = h('p', {class: 'muted'});
  const key = field('API key for this session', 'password', '', '', {autocomplete: 'off'});
  const keyHelp = h('small', {id: `${key.input.id}-help`});
  key.input.setAttribute('aria-describedby', keyHelp.id); key.wrap.append(keyHelp);
  const destination = check('I approve sending model requests to the address shown above.');
  const addressDetails = h('details', {}, h('summary', {}, 'Connection address and API style'), url.wrap, transport.wrap);
  const description = h('p', {class: 'muted'});
  const setupLink = h('div');
  const connectionState = h('div', {'aria-live': 'polite'});
  const catalogueState = h('div', {'aria-live': 'polite'});
  const connectionFeedback = h('div', {'aria-live': 'polite'});
  const accountState = h('div', {'aria-live': 'polite'});
  const accountActions = h('div', {class: 'button-row'});
  const savedAccount = selectField('Saved ChatGPT account', [], '', 'Reconnect an existing registration, or select a signed-in account to use.');
  const accountSelectionState = h('p', {class: 'fine'});
  const accountPanel = h('div', {}, accountState, savedAccount.wrap, accountSelectionState, accountActions,
    h('p', {class: 'fine'}, 'Set a weekly Sinter allowance in ChatGPT’s Settings → Usage → App limits. Keep credit fallback off to stay within that plan allowance. ',
      safeLink('https://chatgpt.com/settings/usage?tab=overview', 'Manage your ChatGPT app allowance')));
  let keyEdited = false, checked = false, checking = false;
  let account = null, authLink = null, accountChoice = '';
  const signInPending = () => ['awaiting', 'waiting', 'processing'].includes(account?.pending?.status);
  const draftConnection = () => ({provider, api_url: url.input.value, model: model.input.value, max_tokens: Number(length.input.value)});
  const state = h('div', {'aria-live': 'polite'});

  function updateConnectionState() {
    const status = connectionStatus({saved: s, draft: draftConnection(), keyEdited, checking, verified: checked});
    const active = connectionPreset(inferConnectionPreset(s));
    connectionState.replaceChildren(h('p', {}, h('strong', {}, `Saved connection: ${active.label}`)), notice(status.text, status.kind));
    checkConnection.disabled = !status.canCheck;
  }
  function updateLengthLimit() {
    const limits = connectionTokenLimits(draftConnection());
    length.input.min = String(limits.min); length.input.max = String(limits.max);
    length.input.disabled = !!limits.disabled;
    length.wrap.hidden = !!limits.disabled;
    answerFields.className = limits.disabled ? '' : 'form-grid';
    lengthExplanation.hidden = !limits.disabled;
    lengthExplanation.textContent = limits.disabled ? limits.help : '';
    lengthHelp.textContent = limits.help;
  }
  function updateRouteDetails() {
    const preset = connectionPreset(route.input.value);
    addressDetails.open = ['local', 'custom'].includes(route.input.value);
    description.textContent = preset.description;
    keyHelp.textContent = preset.keyHelp;
    setupLink.replaceChildren(...(preset.docs ? [safeLink(preset.docs, preset.docsLabel)] : []));
    key.wrap.hidden = provider === 'chatgpt';
    url.input.disabled = provider === 'chatgpt';
    destination.wrap.children[1].textContent = `I approve sending model requests to ${url.input.value || 'the API address I enter'}.`;
    accountPanel.hidden = provider !== 'chatgpt';
    transport.wrap.hidden = route.input.value !== 'custom';
    updateLengthLimit();
  }
  function markConnectionChanged() {
    checked = false;
    catalogueState.replaceChildren(); connectionFeedback.replaceChildren();
    updateLengthLimit(); updateConnectionState();
  }
  function clearDraftKeyOnDestinationChange() {
    if (connectionDestinationChanged(s, draftConnection())) {
      key.input.value = ''; keyEdited = true;
    }
    destination.input.checked = false;
    markConnectionChanged();
  }
  route.input.addEventListener('change', () => {
    const preset = connectionPreset(route.input.value);
    provider = preset.provider;
    transport.input.value = provider === 'anthropic' ? 'anthropic' : 'openai-compatible';
    url.input.value = preset.api_url; model.input.value = preset.model;
    length.input.value = String(preset.max_tokens);
    clearDraftKeyOnDestinationChange(); updateRouteDetails();
    if (provider === 'chatgpt') refreshAccount();
  });
  transport.input.addEventListener('change', () => { provider = transport.input.value; clearDraftKeyOnDestinationChange(); updateRouteDetails(); });
  url.input.addEventListener('input', () => {
    if (provider === 'chatgpt') return;
    route.input.value = inferConnectionPreset(draftConnection());
    clearDraftKeyOnDestinationChange(); updateRouteDetails();
  });
  [model, length].forEach(entry => entry.input.addEventListener('input', markConnectionChanged));
  key.input.addEventListener('input', () => { keyEdited = true; markConnectionChanged(); });

  function renderAccount() {
    const profiles = Array.isArray(account?.profiles) ? account.profiles : [];
    const active = profiles.find(item => item.id === account.active_profile_id);
    const name = active?.name || active?.label || active?.email || account?.display_name;
    const pending = account?.pending, waiting = signInPending();
    if (!profiles.some(item => item.id === accountChoice)) accountChoice = active?.id || profiles[0]?.id || '';
    savedAccount.input.replaceChildren(...profiles.map(item => h('option', {value: item.id},
      `${item.name || item.email || item.label || 'ChatGPT account'} · ${item.connected ? item.plan_usage ? 'plan enabled' : 'identity only' : 'disconnected'}`)));
    savedAccount.input.value = accountChoice;
    savedAccount.wrap.hidden = !profiles.length; savedAccount.input.disabled = waiting;
    const selected = profiles.find(item => item.id === accountChoice);
    accountSelectionState.hidden = !selected;
    accountSelectionState.textContent = !selected ? '' : selected.id === account.active_profile_id
      ? 'This registration is selected for ChatGPT requests.'
      : selected.connected ? 'This account is signed in. Choose “Use selected account” to make it active for ChatGPT requests.'
        : 'This registration is retained but signed out. Reconnect it to use the same account again.';
    const planDenied = account?.connected && account.plan_usage === false;
    const message = account?.connected
      ? `Signed in to ChatGPT${name ? ` as ${name}` : ''}. ${planDenied ? 'Plan usage was not enabled. Allow it in ChatGPT settings before using this connection.' : 'Save this connection to use it in Sinter.'}`
      : waiting ? 'ChatGPT sign-in is waiting. Continue in ChatGPT, then refresh the sign-in status here.'
        : 'Sign in to connect your ChatGPT plan. Signing in does not change your saved assistant connection.';
    accountState.replaceChildren(...[notice(message, planDenied ? 'error' : account?.connected ? 'success' : ''),
      waiting && account?.connected ? notice('Another sign-in is waiting. Continue in ChatGPT, then refresh the status here.') : null,
      account?.warning ? notice(account.warning, 'error') : null,
      account?.available === false && account.message ? notice(account.message, 'error') : null,
      pending?.message && !waiting ? notice(pending.message, pending.status === 'failed' ? 'error' : '') : null,
      authLink && waiting ? safeLink(authLink, 'Continue sign-in with ChatGPT') : null,
      profiles.length >= 20 ? h('p', {class: 'fine'}, 'This workspace has 20 registrations. Reconnect one of the saved accounts.') : null].filter(Boolean));
    connectAccount.textContent = selected ? 'Reconnect selected account' : 'Sign in with ChatGPT';
    connectAccount.disabled = account?.available === false || waiting;
    addAccount.disabled = account?.available === false || waiting || profiles.length >= 20;
    accountActions.replaceChildren(connectAccount, refreshSignIn);
    if (profiles.length) accountActions.append(addAccount);
    if (selected?.connected && selected.id !== account.active_profile_id) accountActions.append(activateAccount);
    if (waiting) accountActions.append(cancelSignIn);
    if (account?.connected) accountActions.append(disconnectAccount);
  }
  savedAccount.input.addEventListener('change', () => { accountChoice = savedAccount.input.value; renderAccount(); });
  async function refreshAccount() {
    refreshSignIn.disabled = true;
    try {
      account = await request('/api/account');
      if (!signInPending()) authLink = null;
      if (account.pending?.status === 'complete') accountChoice = account.active_profile_id || '';
      renderAccount();
    } catch (error) { accountState.replaceChildren(notice(error.message, 'error')); }
    finally { refreshSignIn.disabled = false; }
  }
  async function beginSignIn(profileId = '') {
    connectAccount.disabled = true; addAccount.disabled = true;
    try {
      const result = await request('/api/account/connect', {data: profileId ? {profile_id: profileId} : {}});
      account = result; authLink = result.auth_url || null; accountChoice = profileId;
      renderAccount();
    } catch (error) { accountState.replaceChildren(notice(error.message, 'error')); }
    finally { connectAccount.disabled = account?.available === false || signInPending(); addAccount.disabled = account?.available === false || signInPending() || (account?.profiles?.length || 0) >= 20; }
  }
  const connectAccount = button('Sign in with ChatGPT', () => beginSignIn(accountChoice), 'primary');
  const addAccount = button('Add another ChatGPT account', () => beginSignIn(), 'quiet');
  const refreshSignIn = button('Refresh sign-in status', refreshAccount, 'quiet');
  const activateAccount = button('Use selected account', async () => {
    activateAccount.disabled = true;
    try {
      account = await request('/api/account/activate', {data: {profile_id: accountChoice}});
      authLink = null; checked = false; catalogueState.replaceChildren(); renderAccount(); updateConnectionState();
    } catch (error) { accountState.replaceChildren(notice(error.message, 'error')); }
    finally { activateAccount.disabled = false; }
  }, 'quiet');
  const cancelSignIn = button('Cancel sign-in', async () => {
    try { account = await request('/api/account/cancel', {data: {}}); authLink = null; renderAccount(); }
    catch (error) { accountState.replaceChildren(notice(error.message, 'error')); }
  }, 'quiet');
  const disconnectAccount = button('Disconnect active ChatGPT account', async () => {
    try { account = await request('/api/account/disconnect', {data: {}}); authLink = null; checked = false; catalogueState.replaceChildren(); renderAccount(); updateConnectionState(); }
    catch (error) { accountState.replaceChildren(notice(error.message, 'error')); }
  }, 'quiet');

  const port = field('Local RKC port', 'number', s.rkc_port, 'For an already-running local RKC context service.', {min: 1024, max: 65535});
  const executable = field('Installed RKC executable', 'text', s.rkc_executable, 'Optional absolute path. Used only when you explicitly compile a selected collection.');
  const saveAction = async () => {
    if (![url, model, port, organisation, length, ...Object.values(profile)].every(f => f.input.disabled || f.input.reportValidity())) return;
    save.disabled = true; saveConnection.disabled = true;
    try {
      const next = {...s, ...Object.fromEntries(Object.entries(profile).map(([name, entry]) => [name, entry.input.value])),
        organisation: organisation.input.value, theme: theme.input.value, text_size: size.input.value,
        density: density.input.value, reduce_motion: motion.input.checked, ...draftConnection(),
        rkc_port: Number(port.input.value), rkc_executable: executable.input.value};
      current = await request('/api/settings', {data: {settings: next, confirm_endpoint: destination.input.checked,
        ...(keyEdited ? {api_key: key.input.value} : {})}});
      Object.assign(s, current.settings); applyAppearance(s); key.input.value = ''; keyEdited = false; checked = false;
      destination.input.checked = false; updateConnectionState();
      state.replaceChildren(notice('Preferences saved on this computer. '+(current.has_session_key ? 'An API key is held for this session only.' : 'No session API key is stored.'), 'success'));
      connectionFeedback.replaceChildren(notice('Connection saved. You can check it now or start an assistant task.', 'success'));
      announce('Preferences saved.');
    } catch (error) { connectionFeedback.replaceChildren(notice(error.message, 'error')); state.replaceChildren(notice(error.message, 'error')); }
    finally { save.disabled = false; saveConnection.disabled = false; }
  };
  const save = button('Save my preferences', saveAction, 'primary');
  const saveConnection = button('Save connection', saveAction, 'primary');
  const checkConnection = button('Check saved connection', async () => {
    checking = true; updateConnectionState();
    try { const health = await request('/api/health'); checked = !!health.ok; connectionFeedback.replaceChildren(notice(health.message, checked ? 'success' : 'error')); }
    catch (error) { checked = false; connectionFeedback.replaceChildren(notice(error.message, 'error')); }
    finally { checking = false; updateConnectionState(); }
  }, 'quiet');
  const loadModels = button('Load available models', async () => {
    if (!url.input.reportValidity()) return;
    if (connectionDestinationChanged(s, draftConnection()) && !destination.input.checked) {
      catalogueState.replaceChildren(notice('Approve the API destination above before requesting its model list.', 'error')); return;
    }
    loadModels.disabled = true;
    catalogueState.replaceChildren(notice('Loading the model catalogue. This does not generate an answer or save this connection.'));
    try {
      const result = await request('/api/models', {data: {settings: {...draftConnection(), model: 'probe-placeholder'},
        confirm_endpoint: destination.input.checked, ...(keyEdited ? {api_key: key.input.value} : {})}});
      const ids = availableModelIds(result);
      if (!ids.length) throw new Error('No compatible model identifiers were returned. You can still enter the exact identifier supplied by your provider.');
      const choices = selectField('Available model', [['', 'Choose a model…'], ...ids.map(id => [id, id])], '');
      // selectField defaults empty values to the first option; selecting is always explicit.
      choices.input.value = '';
      choices.input.addEventListener('change', () => {
        if (!choices.input.value) return;
        model.input.value = choices.input.value; checked = false; updateLengthLimit(); updateConnectionState();
      });
      catalogueState.replaceChildren(choices.wrap, h('small', {}, 'The catalogue confirms model names; availability and answer quality are tested when you run a task.'));
    } catch (error) { catalogueState.replaceChildren(notice(error.message, 'error')); }
    finally { loadModels.disabled = false; }
  }, 'quiet');
  const clear = button('Forget the session API key', async () => {
    try {
      current = await request('/api/settings', {data: {settings: s, api_key: ''}});
      key.input.value = ''; keyEdited = false; checked = false; updateConnectionState();
      state.replaceChildren(notice('Session key forgotten. Environment or key-file credentials may still apply to the default NeuroForge connection.'));
    } catch (error) { state.replaceChildren(notice(error.message, 'error')); }
  }, 'quiet');
  updateRouteDetails(); updateConnectionState(); renderAccount();
  if (provider === 'chatgpt') await refreshAccount();

  return h('div', {class: 'stack'}, h('header', {class: 'page-intro'}, h('span', {class: 'eyebrow'}, 'MAKE IT YOURS'),
    h('h2', {}, 'Your details. Your assistant. Your workspace.'),
    h('p', {}, 'Save your details once to fill new drafts. Choose optional intelligence for assistant work, or keep using Sinter’s local planning and records.')),
    current.warning ? notice(current.warning, 'error') : null,
    current.environment_override ? notice('A launcher environment variable overrides the API address or model. Change that launcher configuration to use the connection selected here.') : null,
    h('section', {class: 'card profile-settings'}, h('div', {}, h('h3', {}, 'Your profile'),
      h('p', {class: 'muted'}, 'Saved on this computer. You can change or remove these details in each draft.'),
      h('div', {class: 'form-grid'}, profile.full_name.wrap, profile.role.wrap), organisation.wrap,
      h('div', {class: 'form-grid'}, profile.email.wrap, profile.phone.wrap), profile.website.wrap,
      h('details', {}, h('summary', {}, 'Funding and organisation defaults'), profile.location.wrap, profile.organisation_type.wrap)), signature),
    h('section', {class: 'card'}, h('span', {class: 'eyebrow'}, 'OPTIONAL INTELLIGENCE'), h('h3', {}, 'Connect your assistant'),
      h('p', {class: 'muted'}, 'Use NeuroForge’s ERAIS preview, your ChatGPT plan, a provider API, or a compatible model on this computer. Only the content you choose for a model task is sent to that connection.'),
      route.wrap, description, setupLink, accountPanel,
      addressDetails,
      answerFields, lengthExplanation, key.wrap, destination.wrap,
      h('div', {class: 'button-row'}, loadModels, saveConnection, checkConnection), catalogueState, connectionState, connectionFeedback,
      h('details', {}, h('summary', {}, 'Session credentials'),
        notice('API keys are held by the running Sinter app and never saved to your profile or browser storage. Changing the API address or style clears the previous session key. ChatGPT account access is managed separately.'), clear)),
    h('section', {class: 'card'}, h('h3', {}, 'Reading and appearance'),
      h('div', {class: 'form-grid'}, theme.wrap, size.wrap, density.wrap), motion.wrap),
    h('details', {class: 'card'}, h('summary', {}, 'Optional RKC context service'), port.wrap, executable.wrap),
    h('div', {class: 'button-row'}, save), state);
}
