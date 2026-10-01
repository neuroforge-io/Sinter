/** Explicit local inspection; never expands report quotations or draft context. */
import {casebookQuestionEvidence} from './casebook-question-evidence.js';

const CONTEXT_CHARACTERS = 600;
const unique = (rows, id) => {
  if (!Array.isArray(rows) || rows.length > 300) return null;
  const found = rows.filter(row => row && typeof row === 'object' && row.id === id);
  return found.length === 1 ? found[0] : null;
};

export async function retainedCasebookSource(report, sourceId) {
  if (!casebookQuestionEvidence(report)) throw new Error('Only a complete source-only casebook report can be inspected here.');
  const source = unique(report.sources, sourceId), record = unique(report.source_register, sourceId);
  if (typeof sourceId !== 'string' || !sourceId.trim() || !source || !record
      || typeof source.content !== 'string') {
    throw new Error('The exact original text is not retained unambiguously in this report. No current project source was substituted.');
  }
  // Strings are immutable snapshots: a later render must not change what was
  // checked while the browser computes this local digest.
  const content = source.content, sha256 = record.sha256;
  const characters = Array.from(content);
  if (characters.length > 200000 || characters.some(char => char === '\0'
      || (char.codePointAt(0) >= 0xd800 && char.codePointAt(0) <= 0xdfff))) {
    throw new Error('The retained original contains unsupported text. Nothing was changed.');
  }
  if (typeof sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(sha256)
      || source.sha256 !== sha256) {
    throw new Error('The original’s recorded source hash is unavailable or inconsistent. No substitute was used.');
  }
  if (!globalThis.crypto?.subtle) throw new Error('This browser cannot check the retained original locally. Inspect the matching project backup instead.');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(content));
  const actual = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  if (actual !== sha256) throw new Error('The retained original does not match its recorded source hash. Nothing was changed.');
  return {sourceId, content, title: typeof record.title === 'string' ? record.title : null};
}

export async function retainedQuestionContext(report, questionIndex, excerptId) {
  const rows = casebookQuestionEvidence(report);
  if (!Number.isSafeInteger(questionIndex) || questionIndex < 0 || !rows?.[questionIndex]?.questionAvailable) {
    throw new Error('The recorded question is unavailable. No current question was substituted.');
  }
  const passage = rows[questionIndex].matches.find(row => row.excerptId === excerptId && row.available);
  if (!passage) throw new Error('This question’s exact retained passage is unavailable. Nothing was substituted.');
  const {sourceId, quote, start, end} = passage;
  const source = await retainedCasebookSource(report, sourceId);
  const characters = Array.from(source.content);
  if (characters.slice(start, end).join('') !== quote) {
    throw new Error('The retained quotation does not match the original. Nothing was changed.');
  }
  const beforeStart = Math.max(0, start - CONTEXT_CHARACTERS);
  const afterEnd = Math.min(characters.length, end + CONTEXT_CHARACTERS);
  return {sourceId, start, end, quote, beforeStart, afterEnd,
    before: characters.slice(beforeStart, start).join(''),
    after: characters.slice(end, afterEnd).join(''),
    originalCharacters: characters.length};
}
