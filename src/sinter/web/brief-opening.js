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

/** Describe local document use; format changes never rewrite the entered values. */
export function briefContextCopy(format, campaignSenderReview = false) {
  if (campaignSenderReview === true) {
    return {label: 'Internal notes and evidence context',
      help: 'Campaign notes and reference quotations stay in the evidence pack in every format. Use the opening paragraph and explicit questions for text the recipient should read.'};
  }
  if (format === 'briefing' || format === 'agenda') {
    const name = format === 'briefing' ? 'briefing note' : 'agenda item';
    return {label: 'Background for this ' + name,
      help: 'Selected passages from these notes and references may appear as quoted background in the ' + name + '. Keep private preparation notes out of this field. Changing formats keeps your original text; review it before preparing.'};
  }
  return {label: 'Internal notes and evidence context',
    help: 'Notes and reference text stay in the evidence pack when preparing this enquiry letter; they do not appear in its body. Put text for the recipient in the opening paragraph and explicit questions.'};
}

/** The optional model handoff opens enquiry-letter, not a format-neutral recipe. */
export function enquiryModelDraftProblem(payload = {}) {
  if (payload.workflow !== undefined && payload.workflow !== 'brief') {
    return 'Draft with your model prepares enquiry letters from briefing projects only. Your local inputs are unchanged.';
  }
  if (payload.document_type !== undefined && payload.document_type !== 'enquiry') {
    return 'Draft with your model supports enquiry letters only. Prepare this format locally, or choose Enquiry letter and review the opening and questions first. Your local inputs are unchanged.';
  }
  return '';
}
