import {browserSettingsPage} from './browser-settings.js';
/** Settings are local. API keys stay in process memory, never browser storage. */
import {h, field, selectField, check, button, notice, announce, safeLink} from './ui.js';
import {request} from './api.js';
import {settingsReply, settingsOperations} from './settings-recovery.js';
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
  let current = await request('/api/settings', {acceptResponse: settingsReply});
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
  const accountFeedback = h('div', {'aria-live': 'polite'});
  const accountActions = h('div', {class: 'button-row'});
  const savedAccount = selectField('Saved ChatGPT account', [], '', 'Reconnect an existing registration, or select a signed-in account to use.');
  const accountSelectionState = h('p', {class: 'fine'});
  const accountPanel = h('div', {}, accountState, accountFeedback, savedAccount.wrap, accountSelectionState, accountActions,
    h('p', {class: 'fine'}, 'Set a weekly Sinter allowance in ChatGPT’s Settings → Usage → App limits. Keep credit fallback off to stay within that plan allowance. ',
      safeLink('https://chatgpt.com/settings/usage?tab=overview', 'Manage your ChatGPT app allowance')));
  const operations = settingsOperations();
  let keyEdited = false, keyRevision = 0, draftRevision = 0, checked = false;
  const recoveryHistory = h('div', {'aria-live': 'polite'});
  const heldKeyState = h('p', {class: 'fine'});
  let account = null, authLink = null, accountChoice = '';
  let accountWriting = false, accountEpoch = 0, accountRead = null, accountChoiceRevision = 0;
  const signInPending = () => ['awaiting', 'waiting', 'processing'].includes(account?.pending?.status);
  const draftConnection = () => ({provider, api_url: url.input.value, model: model.input.value, max_tokens: Number(length.input.value)});
  const state = h('div', {'aria-live': 'polite'});

  function updateConnectionState() {
    const status = connectionStatus({saved: s, draft: draftConnection(), keyEdited,
      checking: operations.reading('health'), verified: checked});
    const active = connectionPreset(inferConnectionPreset(s));
    connectionState.replaceChildren(h('p', {}, h('strong', {}, 'Saved connection: ' + active.label)),
      h('p', {class: 'fine'}, 'Saved model: ' + s.model + ' · Answer length setting: ' + s.max_tokens),
      notice(operations.blocked ? 'Check what was saved before making another change.' : status.text,
        operations.blocked ? 'error' : status.kind));
    checkConnection.disabled = !status.canCheck || operations.busy || operations.blocked || accountWriting;
    loadModels.disabled = operations.busy || operations.blocked || accountWriting || operations.reading('catalogue');
    save.disabled = saveConnection.disabled = clear.disabled = operations.busy || operations.blocked || accountWriting;
    refreshSaved.disabled = operations.busy || accountWriting;
    renderAccount();
    heldKeyState.textContent = current.has_session_key
      ? 'An API key is held for the saved connection in this running app.'
      : 'No session API key is held for the saved connection.';
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
    draftRevision++; operations.edit(); checked = false;
    catalogueState.replaceChildren(); connectionFeedback.replaceChildren();
    updateLengthLimit(); updateConnectionState();
  }
  function clearDraftKeyOnDestinationChange() {
    if (connectionDestinationChanged(s, draftConnection())) {
      key.input.value = ''; keyEdited = true; keyRevision++;
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
  key.input.addEventListener('input', () => { keyEdited = true; keyRevision++; markConnectionChanged(); });

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
    const busy = accountWriting || operations.busy || operations.blocked;
    connectAccount.disabled ||= busy; addAccount.disabled ||= busy;
    activateAccount.disabled = cancelSignIn.disabled = disconnectAccount.disabled = busy;
    refreshSignIn.disabled = busy || accountRead !== null;
    accountActions.replaceChildren(connectAccount, refreshSignIn);
    if (profiles.length) accountActions.append(addAccount);
    if (selected?.connected && selected.id !== account.active_profile_id) accountActions.append(activateAccount);
    if (waiting) accountActions.append(cancelSignIn);
    if (account?.connected) accountActions.append(disconnectAccount);
  }
  savedAccount.input.addEventListener('change', () => { accountChoice = savedAccount.input.value; accountChoiceRevision++; renderAccount(); });
  async function refreshAccount() {
    if (accountWriting || operations.busy || operations.blocked) return;
    const token = {epoch: accountEpoch}; accountRead = token; renderAccount();
    try {
      const reply = await request('/api/account');
      if (accountRead !== token || token.epoch !== accountEpoch || accountWriting) return;
      account = reply;
      if (!signInPending()) authLink = null;
      markConnectionChanged(); renderAccount();
    } catch (error) {
      if (accountRead === token && token.epoch === accountEpoch && !accountWriting)
        accountFeedback.replaceChildren(notice(error.message, 'error'));
    } finally {
      if (accountRead === token) { accountRead = null; renderAccount(); }
    }
  }
  function beginAccountWrite() {
    if (accountWriting || operations.busy || operations.blocked) return false;
    accountWriting = true; accountEpoch++; accountRead = null;
    markConnectionChanged(); renderAccount(); return true;
  }
  function finishAccountWrite() {
    accountWriting = false; accountEpoch++; accountRead = null;
    markConnectionChanged(); renderAccount();
  }
  async function beginSignIn(profileId = '') {
    if (!beginAccountWrite()) return;
    const choiceRevision = accountChoiceRevision;
    try {
      const result = await request('/api/account/connect', {data: profileId ? {profile_id: profileId} : {}});
      account = result; authLink = result.auth_url || null;
      if (profileId && accountChoiceRevision === choiceRevision) accountChoice = profileId;
      renderAccount();
    } catch (error) { accountFeedback.replaceChildren(notice(error.message, 'error')); }
    finally { finishAccountWrite(); }
  }
  const connectAccount = button('Sign in with ChatGPT', () => beginSignIn(accountChoice), 'primary');
  const addAccount = button('Add another ChatGPT account', () => beginSignIn(), 'quiet');
  const refreshSignIn = button('Refresh sign-in status', refreshAccount, 'quiet');
  const activateAccount = button('Use selected account', async () => {
    if (!beginAccountWrite()) return;
    try {
      account = await request('/api/account/activate', {data: {profile_id: accountChoice}});
      authLink = null; checked = false; catalogueState.replaceChildren(); renderAccount(); updateConnectionState();
    } catch (error) { accountFeedback.replaceChildren(notice(error.message, 'error')); }
    finally { finishAccountWrite(); }
  }, 'quiet');
  const cancelSignIn = button('Cancel sign-in', async () => {
    if (!beginAccountWrite()) return;
    try { account = await request('/api/account/cancel', {data: {}}); authLink = null; renderAccount(); }
    catch (error) { accountFeedback.replaceChildren(notice(error.message, 'error')); }
    finally { finishAccountWrite(); }
  }, 'quiet');
  const disconnectAccount = button('Disconnect active ChatGPT account', async () => {
    if (!beginAccountWrite()) return;
    try { account = await request('/api/account/disconnect', {data: {}}); authLink = null; checked = false; catalogueState.replaceChildren(); renderAccount(); updateConnectionState(); }
    catch (error) { accountFeedback.replaceChildren(notice(error.message, 'error')); }
    finally { finishAccountWrite(); }
  }, 'quiet');

  const port = field('Local RKC port', 'number', s.rkc_port, 'For an already-running local RKC context service.', {min: 1024, max: 65535});
  const executable = field('Installed RKC executable', 'text', s.rkc_executable, 'Optional absolute path. Used only when you explicitly compile a selected collection.');
  function adoptSettings(reply) {
    current = reply; Object.assign(s, reply.settings); applyAppearance(s);
  }
  function writeFailure(error, label) {
    const unconfirmed = error.requestState?.outcome === 'unconfirmed';
    const needsRefresh = unconfirmed || error.status === 409;
    if (unconfirmed) recoveryHistory.append(notice(label +
      ' has an unconfirmed outcome. It may have reached the app. No request was repeated. ' +
      'Check what was saved; your form and any newer key stay here.', 'error'));
    connectionFeedback.replaceChildren(notice(error.message, 'error'));
    state.replaceChildren(notice(error.message, 'error'));
    return needsRefresh;
  }
  const saveAction = async (connectionOnly = false) => {
    if (operations.busy || operations.blocked || accountWriting) return;
    const fields = connectionOnly ? [url, model, length] : [url, model, port, organisation, length, ...Object.values(profile)];
    if (!fields.every(f => f.input.disabled || f.input.reportValidity())) return;
    const next = connectionOnly ? draftConnection() : {
      ...s, ...Object.fromEntries(Object.entries(profile).map(([name, entry]) => [name, entry.input.value])),
      organisation: organisation.input.value, theme: theme.input.value, text_size: size.input.value,
      density: density.input.value, reduce_motion: motion.input.checked, ...draftConnection(),
      rkc_port: Number(port.input.value), rkc_executable: executable.input.value};
    const sentKeyRevision = keyRevision, sentDraftRevision = draftRevision;
    const token = operations.write(); if (!token) return;
    accountEpoch++; accountRead = null;
    checked = false; catalogueState.replaceChildren(); updateConnectionState();
    let needsRefresh = false;
    try {
      const reply = await request('/api/settings', {data: {
        settings: next, expected_revision: current.revision,
        confirm_endpoint: destination.input.checked, ...(keyEdited ? {api_key: key.input.value} : {})
      }, acceptResponse: settingsReply});
      adoptSettings(reply);
      if (keyRevision === sentKeyRevision) { key.input.value = ''; keyEdited = false; }
      if (draftRevision === sentDraftRevision) destination.input.checked = false;
      state.replaceChildren(notice(connectionOnly
        ? 'Connection saved on this computer. Other preference fields were not saved.'
        : 'Preferences saved on this computer.', 'success'));
      connectionFeedback.replaceChildren(notice('Saved on this computer. Availability has not been checked.', 'success'));
      announce(connectionOnly ? 'Connection saved.' : 'Preferences saved.');
    } catch (error) { needsRefresh = writeFailure(error, connectionOnly ? 'Save connection' : 'Save preferences'); }
    finally { operations.finishWrite(token, needsRefresh); updateConnectionState(); }
  };
  const save = button('Save my preferences', () => saveAction(), 'primary');
  const saveConnection = button('Save connection', () => saveAction(true), 'primary');
  const refreshSaved = button('Check what was saved', async () => {
    if (accountWriting) return;
    const token = operations.recover(); if (!token) return;
    checked = false; catalogueState.replaceChildren(); updateConnectionState();
    let observed = false;
    try {
      const reply = await request('/api/settings', {acceptResponse: settingsReply});
      if (!operations.acceptsRecovery(token)) return;
      adoptSettings(reply); observed = true;
      connectionFeedback.replaceChildren(notice('Saved settings observed. Your form edits are unchanged. ' +
        'Earlier unconfirmed requests remain unconfirmed; none was repeated. ' +
        'A subsequent explicit save is protected against an older delayed request.'));
    } catch (error) {
      if (operations.acceptsRecovery(token)) connectionFeedback.replaceChildren(notice(error.message, 'error'));
    } finally { operations.finishRecovery(token, observed); updateConnectionState(); }
  }, 'quiet');
  const checkConnection = button('Check saved connection', async () => {
    if (operations.busy || operations.blocked || accountWriting ||
        !connectionStatus({saved: s, draft: draftConnection(), keyEdited}).canCheck) return;
    const token = operations.read('health'); if (!token) return;
    const revision = current.revision;
    updateConnectionState();
    try {
      const health = await request('/api/health');
      if (!operations.accepts(token)) return;
      if (health.settings_revision !== revision) {
        connectionFeedback.replaceChildren(notice('Saved settings changed before this check. Check what was saved, then check that connection.', 'error'));
        return;
      }
      checked = health.ok === true;
      connectionFeedback.replaceChildren(notice(health.message, checked ? 'success' : 'error'));
    } catch (error) {
      if (operations.accepts(token)) { checked = false; connectionFeedback.replaceChildren(notice(error.message, 'error')); }
    } finally { operations.finishRead('health', token); updateConnectionState(); }
  }, 'quiet');
  const loadModels = button('Load available models', async () => {
    if (operations.busy || operations.blocked || accountWriting || !url.input.reportValidity()) return;
    if (connectionDestinationChanged(s, draftConnection()) && !destination.input.checked) {
      catalogueState.replaceChildren(notice('Approve the API destination above before requesting its model list.', 'error')); return;
    }
    const token = operations.read('catalogue'); if (!token) return;
    updateConnectionState();
    catalogueState.replaceChildren(notice('Loading the model catalogue. This does not generate an answer or save this connection.'));
    try {
      const result = await request('/api/models', {data: {settings: {provider, api_url: url.input.value},
        confirm_endpoint: destination.input.checked, ...(keyEdited ? {api_key: key.input.value} : {})}});
      if (!operations.accepts(token)) return;
      const ids = availableModelIds(result);
      if (!ids.length) throw new Error('No compatible model identifiers were returned. You can still enter the exact identifier supplied by your provider.');
      const choices = selectField('Available model', [['', 'Choose a model…'], ...ids.map(id => [id, id])], '');
      choices.input.value = '';
      choices.input.addEventListener('change', () => {
        if (!choices.input.value || !operations.accepts(token)) return;
        model.input.value = choices.input.value; markConnectionChanged();
        connectionFeedback.replaceChildren(notice('Model selected in this form. Save connection to use it.'));
      });
      const resultText = ids.length + (ids.length === 1 ? ' model name loaded. ' : ' model names loaded. ') +
        (ids.includes(model.input.value) ? 'Your current selection is unchanged.' :
          'Your selected model is not listed. Nothing has been changed.');
      catalogueState.replaceChildren(notice(resultText), choices.wrap,
        h('small', {}, 'To change the model, choose explicitly, then Save connection. Loading names does not check answer quality.'));
    } catch (error) { if (operations.accepts(token)) catalogueState.replaceChildren(notice(error.message, 'error')); }
    finally { operations.finishRead('catalogue', token); updateConnectionState(); }
  }, 'quiet');
  const clear = button('Forget the session API key', async () => {
    if (accountWriting) return;
    const token = operations.write(); if (!token) return;
    checked = false; catalogueState.replaceChildren(); updateConnectionState();
    let needsRefresh = false;
    try {
      const reply = await request('/api/settings', {data: {
        settings: {}, api_key: '', expected_revision: current.revision
      }, acceptResponse: settingsReply});
      adoptSettings(reply);
      state.replaceChildren(notice('Held session key forgotten. Any replacement key typed in this form is unchanged. ' +
        'Environment or key-file credentials may still apply to the default NeuroForge connection.'));
    } catch (error) { needsRefresh = writeFailure(error, 'Forget session key'); }
    finally { operations.finishWrite(token, needsRefresh); updateConnectionState(); }
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
      connectionState, answerFields, lengthExplanation,
      h('div', {class: 'button-row'}, loadModels), catalogueState,
      key.wrap, heldKeyState, destination.wrap,
      h('div', {class: 'button-row'}, saveConnection, checkConnection, refreshSaved), connectionFeedback, recoveryHistory,
      h('details', {}, h('summary', {}, 'Session credentials'),
        notice('API keys are held by the running Sinter app and never saved to your profile or browser storage. Changing the API address or style clears the previous session key. ChatGPT account access is managed separately.'), clear)),
    h('section', {class: 'card'}, h('h3', {}, 'Reading and appearance'),
      h('div', {class: 'form-grid'}, theme.wrap, size.wrap, density.wrap), motion.wrap),
    h('details', {class: 'card'}, h('summary', {}, 'Optional RKC context service'), port.wrap, executable.wrap),
    h('div', {class: 'button-row'}, save), state);
}
