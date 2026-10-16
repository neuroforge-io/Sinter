/** Explicit recipient prose, separate from internal notes and source evidence. */
export const OPENING_LIMIT = 1200;

export function openingParagraphProblem(value) {
  if (typeof value !== 'string') return 'Opening paragraph must be text.';
  if (Array.from(value).length > OPENING_LIMIT) {
    return 'Opening paragraph exceeds 1,200 characters. Shorten it or move detail into your notes; your text is retained.';
  }
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) {
    return 'Opening paragraph contains unsupported control characters.';
  }
  if (Array.from(value).some(character => {
    const point = character.codePointAt(0);
    return point >= 0xd800 && point <= 0xdfff;
  })) return 'Opening paragraph contains invalid Unicode text.';
  return '';
}

export function briefOpeningCopy(format) {
  return format === 'agenda'
    ? {label: 'Purpose paragraph for this agenda',
      help: 'Optional. Used as the agenda’s purpose. Review it after changing formats; an email opening may need rewriting.'}
    : {label: 'Opening paragraph for the recipient',
      help: 'Optional. Replaces the standard letter opening or introduces a briefing note. Your wording and line breaks are kept when preparing locally.'};
}
