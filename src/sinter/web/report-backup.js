/** Admit a complete report backup without repairing or projecting its evidence. */
export const REPORT_BACKUP_MAX_BYTES = 2_000_000;
const fail = message => { throw new Error(message); };

export function checkReportBackupSize(size) {
  if (!Number.isSafeInteger(size) || size < 1 || size > REPORT_BACKUP_MAX_BYTES) {
    fail('Choose a non-empty draft JSON file no larger than 2,000,000 bytes. Your local work is unchanged.');
  }
}

function wellFormed(value) {
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
    } else if (code >= 0xdc00 && code <= 0xdfff) return false;
  }
  return true;
}

function decimalIdentity(token) {
  const [, sign, whole, fraction = '', power = '0'] =
    /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(token);
  const digits = (whole + fraction).replace(/^0+/, '');
  if (!digits) return '0';
  const coefficient = digits.replace(/0+$/, '');
  const exponent = Number(power) - fraction.length + digits.length - coefficient.length;
  if (!Number.isSafeInteger(exponent)) fail('A number in this backup cannot be preserved exactly.');
  return sign + coefficient + 'e' + exponent;
}

/** JSON.parse owns grammar; this pass rejects information it would silently lose. */
function checkIntegrity(text) {
  const stack = [], number = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
  for (let i = 0; i < text.length;) {
    const char = text[i], top = stack.at(-1);
    if (char === '"') {
      let end = i + 1;
      while (end < text.length && text[end] !== '"') end += text[end] === '\\' ? 2 : 1;
      if (end >= text.length) fail('The draft JSON contains an unfinished string.');
      const value = JSON.parse(text.slice(i, end + 1));
      if (!wellFormed(value)) fail('This backup contains incomplete Unicode characters. Keep the original file; no text was repaired.');
      if (top?.keys && top.expectKey) {
        if (top.keys.has(value)) fail('This backup repeats a JSON key. Keep the original file; no evidence was discarded.');
        top.keys.add(value); top.expectKey = false;
      }
      i = end + 1; continue;
    }
    if (char === '{' || char === '[') {
      if (stack.length >= 64) fail('This backup is nested too deeply to restore safely.');
      stack.push(char === '{' ? {keys: new Set(), expectKey: true} : {}); i++; continue;
    }
    if (char === '}' || char === ']') { stack.pop(); i++; continue; }
    if (char === ',' && top?.keys) top.expectKey = true;
    if (char === '-' || /[0-9]/.test(char)) {
      number.lastIndex = i;
      const match = number.exec(text);
      if (!match) fail('This backup contains an unreadable number.');
      const token = match[0], value = Number(token);
      if (!Number.isFinite(value) || Object.is(value, -0)
          || (Number.isInteger(value) && !Number.isSafeInteger(value))
          || decimalIdentity(token) !== decimalIdentity(JSON.stringify(value))) {
        fail('A number in this backup cannot be preserved exactly. Keep the original file; no value was rounded.');
      }
      i = number.lastIndex; continue;
    }
    i++;
  }
}

export function decodeReportBackup(bytes) {
  if (!(bytes instanceof Uint8Array)) fail('Read the original draft JSON bytes before restoring.');
  checkReportBackupSize(bytes.byteLength);
  let text, report;
  try { text = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes); }
  catch { fail('This file is not valid UTF-8. Keep the original file; no text was repaired.'); }
  try { report = JSON.parse(text); }
  catch { fail('This file is not valid draft JSON. Your local work is unchanged.'); }
  checkIntegrity(text);
  if (!report || typeof report !== 'object' || Array.isArray(report)) fail('Choose an exported draft JSON object.');
  if (typeof report.schema === 'string'
      && /^sinter-(?:casebook|campaign|workspace)\/v\d+$/.test(report.schema)) {
    fail('This is a project or workspace backup. Use its matching restore controls; this control restores one draft JSON.');
  }
  if (typeof report.title !== 'string' || [...report.title].length > 200
      || /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u.test(report.title)
      || typeof report.markdown !== 'string') {
    fail('A draft backup needs a non-empty title of at most 200 characters and its original markdown.');
  }
  if (report.document_markdown != null && typeof report.document_markdown !== 'string') {
    fail('This backup has unreadable document wording. Keep the original file; nothing was removed.');
  }
  if (report.document_edits != null && (typeof report.document_edits !== 'object'
      || Array.isArray(report.document_edits) || typeof report.document_edits.markdown !== 'string')) {
    fail('This backup has unreadable document edits. Keep the original file; nothing was removed.');
  }
  return report;
}
