/** View replacement policy; no persistence, requests or document merging. */
import {reportReplacementState, reportReplacementUnchanged} from './report-drafts.js';

/** Every result owns the inputs which produced it, independent of later attempts. */
export function retainReportResult(report, input, number) {
  const payload = structuredClone(input);
  return {report, payload, inputKey: JSON.stringify(payload), number, shown: false};
}

export function reportCorrectionPayload(entry, corrections) {
  return {...structuredClone(entry.payload), corrections: structuredClone(corrections)};
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
