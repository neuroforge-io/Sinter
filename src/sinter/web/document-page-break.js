/** Explicit user-authored boundaries; quoted or nested material stays literal. */
export const DOCUMENT_PAGE_BREAK_MARKER = '<!-- sinter-page-break -->';

export function isDocumentPageBreak(lines, index, depth = 0) {
  return depth === 0 && lines[index] === DOCUMENT_PAGE_BREAK_MARKER
    && (index === 0 || !lines[index - 1].trim())
    && (index + 1 === lines.length || !lines[index + 1].trim());
}

export function insertDocumentPageBreak(text, offset = text.length) {
  let at = Math.max(0, Math.min(text.length, Number.isInteger(offset) ? offset : text.length));
  // Textarea offsets use UTF-16. Never divide a supplementary source character.
  if (at > 0 && /[\uD800-\uDBFF]/.test(text[at - 1])
      && /[\uDC00-\uDFFF]/.test(text[at] || '')) at--;
  const before = text.slice(0, at), after = text.slice(at);
  const leading = !before || before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n';
  const trailing = !after || after.startsWith('\n\n') ? '' : after.startsWith('\n') ? '\n' : '\n\n';
  const insertion = leading + DOCUMENT_PAGE_BREAK_MARKER + trailing;
  return {text: before + insertion + after, cursor: at + insertion.length};
}
