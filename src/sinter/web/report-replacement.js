/** View replacement policy; no persistence, requests or document merging. */
import {reportReplacementState, reportReplacementUnchanged} from './report-drafts.js';

/** Every result owns the inputs which produced it, independent of later attempts. */
export function retainReportResult(report, input, number) {
  const payload = structuredClone(input);
  return {report, payload, inputKey: reportPreparationInputKey(payload), number, shown: false};
}

/** Compare editable project inputs, retaining derived provenance in the payload. */
export function reportPreparationInputKey(input) {
  const fields = {...input};
  if (fields.workflow === 'meeting') delete fields.transcript_source;
  return JSON.stringify(fields);
}

export function reportCorrectionPayload(entry, corrections) {
  const payload = {...structuredClone(entry.payload), corrections: structuredClone(corrections)};
  if (payload.workflow === 'meeting') {
    payload.transcript_source = correctionTranscriptPin(payload.notes, entry.report.sources);
  }
  return payload;
}

/** Select historical metadata; the backend recomputes identity from raw notes. */
function correctionTranscriptPin(notes, sources) {
  const original = Array.isArray(sources) && sources.length === 1 ? sources[0] : null;
  if (typeof notes !== 'string' || !original || original.kind !== 'transcript'
      || original.title !== 'Original transcript' || original.url !== ''
      || original.content !== notes || typeof original.id !== 'string'
      || !/^S[a-f0-9]{16}$/.test(original.id)
      || typeof original.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(original.sha256)
      || typeof original.retrieved_at !== 'string' || !original.retrieved_at) {
    throw new Error("This report's original transcript snapshot is missing or inconsistent. "
      + 'Reopen the original report, or prepare changed notes as a new transcript.');
  }
  return {id: original.id, sha256: original.sha256, retrieved_at: original.retrieved_at};
}

export async function authorizeReportReplacement(report, {confirm, isActive}) {
  if (!isActive()) return null;
  const state = report ? reportReplacementState(report) : null;
  if (state?.saving) throw new Error('Wait for this document’s save to finish before changing drafts. No preparation was started.');
  if (state?.needsDecision && !await confirm()) return null;
  if (!isActive()) return null;
  if (report && !reportReplacementUnchanged(report, state)) {
    throw new Error('This draft or its save state changed while the decision was open. Your work is kept; review it before trying again.');
  }
  return Object.freeze({report, state});
}

/** Recheck at result arrival; approval never covers later edits or saves. */
export function reportReplacementStillAllowed(report, authorization) {
  return Boolean(authorization && report === authorization.report
    && (!report || reportReplacementUnchanged(report, authorization.state)));
}
