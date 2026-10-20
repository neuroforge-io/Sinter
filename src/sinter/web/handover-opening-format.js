/** Exact editable handover opening syntax. Shape admission never verifies facts. */
import {createMarkdownIndex} from './markdown.js';
export const OPENING_INTRO = 'Statuses and next steps below are user-entered for review. Next steps are proposals, not accepted commitments. A retained quotation establishes supplied wording, not independent verification.';
export const OPENING_STALE = '**Review status: stale.** Review this saved record again before current use. Original evidence and historical wording remain unchanged; no current source was substituted.';
export const OPENING_COVERAGE = '**Evidence coverage:** this opening uses selected wording from this saved report. The unchanged checklist and selected evidence follow. This is not full supplied history; request the matching original project backup for unselected text. Later project or campaign changes are not included.';
export const MISSING_EVIDENCE = 'Missing supporting record; answer remains unknown';
export const OPENING_FIELDS = ['Next step — proposed', 'Evidence', 'Recorded status — user-entered',
  'Wording period', 'Responsibility', 'Timing'];
const MARKER = '## Handover next steps\n';
const MAX_ROWS = 12, MAX_TEXT = 1000;

export const openingLiteral = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replace(/[\\\x60*_{}\[\]#!|]/g, '\\$&');

export function openingQuote(value) {
  let longest = 0;
  for (const run of value.matchAll(/\x60+/g)) longest = Math.max(longest, run[0].length);
  const fence = '\x60'.repeat(Math.max(3, longest + 1));
  return '> ' + fence + 'text\n> ' + value.replace(/\r\n|[\r\n\v\f\x85\u2028\u2029]/g, '\n')
    .replaceAll('\n', '\n> ') + '\n> ' + fence;
}

export function formatOpeningItem({number, item, action, evidence, status, period, responsibility, timing}) {
  return ['### Summary item ' + number + ': ' + openingLiteral(item),
    ...[action, evidence, status, period, responsibility, timing]
      .map((value, index) => '**' + OPENING_FIELDS[index] + ':** ' + openingLiteral(value))].join('\n\n');
}

function decode(value, limit = MAX_TEXT) {
  const plain = value.replace(/\\([\\\x60*_{}\[\]#!|])/g, '$1')
    .replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&amp;', '&');
  if (!plain.trim() || plain.length > limit || /[\x00-\x1f\x7f-\x9f\u2028\u2029]/u.test(plain)
      || Array.from(plain).some(char => char.codePointAt(0) >= 0xd800 && char.codePointAt(0) <= 0xdfff)
      || openingLiteral(plain) !== value) return null;
  return plain;
}

/** Admit one whole canonical opening, including every selected-quotation binding.
 * The caller separately admits the actual DOM and any generated cover.
 */
export function parseHandoverOpening(markdown) {
  if (typeof markdown !== 'string' || markdown.length > 500000) return null;
  const source = markdown.replace(/\r\n?/g, '\n');
  const headings = createMarkdownIndex(source).blocks.filter(block => block.kind === 'heading');
  const named = label => headings.filter(block => source.slice(block.start, block.end).replace(/\n$/, '') === '## ' + label);
  const starts = named('At a glance'), tails = named('Handover next steps');
  if (starts.length !== 1 || tails.length > 1) return null;
  const start = starts[0].start;
  if (tails.length && tails[0].start <= start) return null;
  const end = tails.length ? tails[0].start : source.length;
  const raw = source.slice(start, end).replace(/\n+$/, '');
  const parts = raw.split('\n\n');
  if (parts[0] !== '## At a glance' || parts[1] !== OPENING_INTRO) return null;
  let at = 2;
  const stale = parts[at] === OPENING_STALE;
  if (stale) at++;
  const items = [];
  while (parts[at]?.startsWith('### Summary item ')) {
    const number = items.length + 1, prefix = '### Summary item ' + number + ': ';
    const heading = parts[at++];
    if (number > MAX_ROWS || !heading.startsWith(prefix)) return null;
    const item = decode(heading.slice(prefix.length));
    if (item === null) return null;
    const values = [];
    for (const [index, label] of OPENING_FIELDS.entries()) {
      const field = '**' + label + ':** ';
      const line = parts[at++];
      if (!line?.startsWith(field)) return null;
      const value = decode(line.slice(field.length), index === 4 ? MAX_TEXT + 160 : MAX_TEXT);
      if (value === null) return null;
      values.push(value);
    }
    if (!/^Passage [1-9][0-9]*$/.test(values[1]) && values[1] !== MISSING_EVIDENCE) return null;
    if (!['As recorded', 'Historical wording'].includes(values[3])) return null;
    const responsibility = values[4];
    if (!['Owner type unknown; acceptance unconfirmed', 'Unassigned; no owner has been recorded'].includes(responsibility)) {
      const namedOwner = /^Named person: (.+); (?:acceptance unconfirmed|acceptance marked by the user \(not independently verified\))$/.exec(responsibility);
      const role = /^Suggested role: (.+); acceptance unconfirmed$/.exec(responsibility);
      const name = namedOwner?.[1] ?? role?.[1];
      if (!name?.trim() || name.length > MAX_TEXT) return null;
    }
    if (values[5] !== 'Proposed target not supplied') {
      const date = /^Proposed target (\d{4}-\d{2}-\d{2}) \(unconfirmed; not a funder deadline\)$/.exec(values[5]);
      if (!date || date[1].startsWith('0000-') || !Number.isFinite(Date.parse(date[1]))
          || new Date(date[1]).toISOString().slice(0, 10) !== date[1]) return null;
    }
    items.push({number, item, values, heading, fields: parts.slice(at - OPENING_FIELDS.length, at)});
  }
  if (!items.length || parts[at++] !== OPENING_COVERAGE) return null;
  const supported = items.filter(row => row.values[1] !== MISSING_EVIDENCE);
  const quotations = [];
  if (supported.length) {
    if (parts[at++] !== '### Wording selected for this summary') return null;
    for (const row of supported) {
      const caption = '**Summary item ' + row.number + ': ' + openingLiteral(row.item) + '** — ' + row.values[1];
      if (parts[at++] !== caption) return null;
      const block = parts[at++], lines = block?.split('\n');
      const fence = /^> (\x60{3,})text$/.exec(lines?.[0] || '');
      if (!fence || lines.length < 3 || lines.at(-1) !== '> ' + fence[1]
          || lines.slice(1, -1).some(line => !line.startsWith('> '))) return null;
      const quote = lines.slice(1, -1).map(line => line.slice(2)).join('\n');
      if (!quote || openingQuote(quote) !== block) return null;
      quotations.push({number: row.number, item: row.item, label: row.values[1], quote});
    }
  }
  if (at !== parts.length) return null;
  // A complete document has a separate unchanged tail; a preview may end here.
  if (tails.length && source.slice(end, end + MARKER.length) !== MARKER) return null;
  return {raw, start, end, hasTail: Boolean(tails.length), stale, items, quotations};
}
