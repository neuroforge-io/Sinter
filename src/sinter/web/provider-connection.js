/** Connection choices are explicit; saved does not mean remotely verified. */
export const CONNECTION_PRESETS = Object.freeze([
  {id: 'chatgpt', label: 'ChatGPT · use your plan', provider: 'chatgpt',
    api_url: 'https://api.openai.com/v1', model: '', max_tokens: 2048,
    description: 'Sign in with ChatGPT, then choose an available model. Plan access depends on your account and the registered Sinter application.',
    keyHelp: 'ChatGPT sign-in supplies access; no API key is needed for this connection.',
    docs: 'https://developers.openai.com/siwc/token-sharing-open-source/sign-in', docsLabel: 'ChatGPT plan connection guide'},
  {id: 'neuroforge', label: 'NeuroForge · ERAIS preview', provider: 'openai-compatible',
    api_url: 'https://neuroforge.io/v1', model: 'auto', max_tokens: 64,
    description: 'Use the ERAIS model served by NeuroForge. The public preview needs no API key; availability and answer limits depend on the live model.',
    keyHelp: 'Optional private NeuroForge key. The public preview works without one.',
    docs: 'https://neuroforge.io/api.md', docsLabel: 'NeuroForge API guide'},
  {id: 'openai', label: 'OpenAI · API key', provider: 'openai-compatible',
    api_url: 'https://api.openai.com/v1', model: '', max_tokens: 2048,
    description: 'Connect an OpenAI API project. Choose an exact model available to your project. API requests use your project billing.',
    keyHelp: 'Use a project API key from the OpenAI Platform. Held for this session only.',
    docs: 'https://developers.openai.com/api/docs/quickstart', docsLabel: 'OpenAI API setup'},
  {id: 'anthropic', label: 'Anthropic · Claude API', provider: 'anthropic',
    api_url: 'https://api.anthropic.com/v1', model: '', max_tokens: 2048,
    description: 'Connect the Claude API using its native Messages connection. Choose an exact model available to your API account.',
    keyHelp: 'Use a Claude Console API key scoped to the intended workspace. Held for this session only.',
    docs: 'https://platform.claude.com/docs/en/api/overview', docsLabel: 'Claude API setup'},
  {id: 'gemini', label: 'Google · Gemini API', provider: 'openai-compatible',
    api_url: 'https://generativelanguage.googleapis.com/v1beta/openai', model: '', max_tokens: 2048,
    description: 'Connect Gemini with a Google AI Studio API key through Google’s OpenAI-compatible endpoint.',
    keyHelp: 'Use a Gemini API key from Google AI Studio. Held for this session only.',
    docs: 'https://ai.google.dev/gemini-api/docs/openai', docsLabel: 'Gemini connection guide'},
  {id: 'local', label: 'Local model · Ollama or compatible server', provider: 'openai-compatible',
    api_url: 'http://127.0.0.1:11434/v1', model: '', max_tokens: 2048,
    description: 'Use a model server on this computer. Start the server and choose an installed model. You can change the address for another compatible local server.',
    keyHelp: 'Usually blank for a local server. Add a key only if your server requires one.',
    docs: 'https://docs.ollama.com/api/openai-compatibility', docsLabel: 'Local Ollama setup'},
  {id: 'custom', label: 'Another provider · custom API address', provider: 'openai-compatible',
    api_url: '', model: '', max_tokens: 2048,
    description: 'Connect another HTTPS API. Choose its API style, base address and an exact model identifier. Compatible text chat and Anthropic Messages connections are supported.',
    keyHelp: 'Use a key supplied by this provider. Held for this session only.'}
]);

export function connectionPreset(id) {
  return CONNECTION_PRESETS.find(preset => preset.id === id) || CONNECTION_PRESETS.at(-1);
}

function canonicalEndpoint(value) {
  try {
    if (typeof value !== 'string' || /[\u0000-\u001f\u007f]/.test(value)) return '';
    const input = value.trim();
    // The client binds credentials to the literal API path. URL's dot-segment
    // normalisation must not make a different destination look like a preset.
    if (/\\|[\u0000-\u0020\u007f]|(?:^|\/)\.{1,2}(?:\/|$)|%2e/i.test(input)) return '';
    const parsed = new URL(input);
    if (parsed.search || parsed.hash || parsed.username || parsed.password) return '';
    return `${parsed.origin}${parsed.pathname.replace(/\/+$/, '')}`;
  } catch { return ''; }
}

export function inferConnectionPreset(settings = {}) {
  const endpoint = canonicalEndpoint(settings.api_url);
  const provider = settings.provider || 'openai-compatible';
  const known = CONNECTION_PRESETS.find(preset => preset.id !== 'custom'
    && preset.provider === provider && canonicalEndpoint(preset.api_url) === endpoint);
  if (known) return known.id;
  try {
    const parsed = new URL(settings.api_url);
    if (provider === 'openai-compatible' && ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname)
      && ['http:', 'https:'].includes(parsed.protocol) && !parsed.search && !parsed.hash
      && !parsed.username && !parsed.password) return 'local';
  } catch { /* Invalid destinations are shown as custom and validated on save. */ }
  return 'custom';
}

export function connectionTokenLimits(settings = {}) {
  if (settings.provider === 'chatgpt') return {min: 32, max: 8192, disabled: true,
    help: 'ChatGPT plan access controls response length. This connection does not accept Sinter’s output-token setting.'};
  if ((settings.provider || 'openai-compatible') !== 'openai-compatible'
    || canonicalEndpoint(settings.api_url) !== 'https://neuroforge.io/v1') {
    return {min: 32, max: 8192, help: 'Maximum output tokens per step. Longer drafts may need a larger limit; your provider may apply a lower cap.'};
  }
  const model = String(settings.model || '').trim();
  if (model === 'erais-native-qwen3') return {min: 1, max: 2048, effectiveMax: 128,
    help: 'Your saved output cap is retained. Native ERAIS applies at most 128 output tokens per request, even when the saved cap is higher. Use a short question; this preview is unqualified for general chat.'};
  if (model === 'auto') return {min: 32, max: 2048,
    help: 'Your saved output cap is retained. Discovery applies the exact live model’s lower limit: native ERAIS up to 128 tokens; dense up to 512; hybrid up to 2,048. Long drafts may remain incomplete.'};
  if (model === 'erais-dense-gemma4-e4b') return {min: 32, max: 2048, effectiveMax: 512,
    help: 'Your saved output cap is retained. The dense NeuroForge preview applies at most 512 output tokens per step, even when the saved cap is higher.'};
  return {min: 32, max: 2048, help: 'The public NeuroForge preview allows up to 2,048 output tokens per step; individual models may use a lower cap.'};
}

export function connectionChanged(saved = {}, draft = {}) {
  return (saved.provider || 'openai-compatible') !== (draft.provider || 'openai-compatible')
    || canonicalEndpoint(saved.api_url) !== canonicalEndpoint(draft.api_url)
    || String(saved.model || '').trim() !== String(draft.model || '').trim()
    || Number(saved.max_tokens) !== Number(draft.max_tokens);
}

export function connectionDestinationChanged(saved = {}, draft = {}) {
  return (saved.provider || 'openai-compatible') !== (draft.provider || 'openai-compatible')
    || canonicalEndpoint(saved.api_url) !== canonicalEndpoint(draft.api_url);
}

export function connectionStatus({saved = {}, draft = {}, keyEdited = false, checking = false, verified = false} = {}) {
  if (connectionChanged(saved, draft) || keyEdited) return {kind: '', text: 'Connection changes are not saved yet.', canCheck: false};
  if (checking) return {kind: '', text: 'Checking the saved connection…', canCheck: false};
  if (verified) return {kind: 'success', text: 'Model connection checked. A catalogue check does not test answer quality.', canCheck: true};
  return {kind: '', text: 'Connection saved. Check availability before starting assistant work.', canCheck: true};
}

export function availableModelIds(payload) {
  const source = Array.isArray(payload?.models) ? payload.models : [];
  return [...new Set(source.map(item => typeof item === 'string' ? item : item?.id)
    .filter(value => typeof value === 'string' && /^[A-Za-z0-9_./:@+\-]{1,200}$/.test(value)))].slice(0, 256);
}
