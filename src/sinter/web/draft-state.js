/** Keep resumable route state separate from the state that can be lost. */
export function rememberDraft(drafts, dirtyDrafts, kind, value, options = {}) {
  if (value?.demo) return;
  drafts.set(kind, value);
  const dirty = options.dirty ?? value?.dirty ?? true;
  if (dirty) dirtyDrafts.add(kind);
  else dirtyDrafts.delete(kind);
}

export function shouldWarnBeforeExit(dirtyDrafts, busy) {
  return Boolean(busy) || dirtyDrafts.size > 0;
}
