/** Secret-free observations for the local settings editor; no request is replayed. */
export function settingsReply(value) {
  const s = value?.settings;
  const strings = ['api_url', 'provider', 'model', 'organisation', 'theme', 'text_size',
    'density', 'rkc_executable', 'full_name', 'role', 'email', 'phone', 'website', 'location', 'organisation_type'];
  if (!s || typeof s !== 'object' || Array.isArray(s) ||
      !strings.every(name => typeof s[name] === 'string') ||
      !Number.isInteger(s.max_tokens) || s.max_tokens < 1 || s.max_tokens > 8192 ||
      !Number.isInteger(s.rkc_port) || s.rkc_port < 1024 || s.rkc_port > 65535 || s.schema_version !== 1 ||
      !['openai-compatible', 'anthropic', 'chatgpt'].includes(s.provider) ||
      !/^[-A-Za-z0-9_./:@+]{1,200}$/.test(s.model) || !s.api_url.trim() ||
      typeof s.reduce_motion !== 'boolean' || typeof value.has_session_key !== 'boolean' ||
      typeof value.revision !== 'string' || !/^[0-9a-f]{32}$/.test(value.revision)) {
    throw new Error('The app returned incomplete settings. Keep your form and check what was saved.');
  }
  return value;
}

export function settingsOperations() {
  let epoch = 0, writeEpoch = 0, writer = null, recovery = null, blocked = false;
  const reads = new Map(), latest = new Map();
  const invalidate = () => { epoch++; reads.clear(); latest.clear(); };
  return {
    edit: invalidate,
    get epoch() { return epoch; },
    get busy() { return writer !== null || recovery !== null; },
    get blocked() { return blocked; },
    reading(kind) { return reads.has(kind); },
    read(kind) {
      if (writer || recovery || blocked || reads.has(kind)) return null;
      const token = {epoch, kind}; reads.set(kind, token); latest.set(kind, token); return token;
    },
    accepts(token) { return !!token && latest.get(token.kind) === token && token.epoch === epoch && !writer && !recovery && !blocked; },
    finishRead(kind, token) { if (reads.get(kind) === token) reads.delete(kind); },
    write() {
      if (writer || recovery || blocked) return null;
      invalidate(); writeEpoch++; writer = {}; return writer;
    },
    finishWrite(token, needsRefresh) {
      if (writer !== token) return;
      writer = null; blocked = needsRefresh; writeEpoch++; invalidate();
    },
    recover() {
      if (writer || recovery) return null;
      recovery = {writeEpoch}; return recovery;
    },
    acceptsRecovery(token) { return recovery === token && token.writeEpoch === writeEpoch; },
    finishRecovery(token, observed) {
      if (!this.acceptsRecovery(token)) return;
      recovery = null;
      if (observed) { blocked = false; invalidate(); }
    }
  };
}
