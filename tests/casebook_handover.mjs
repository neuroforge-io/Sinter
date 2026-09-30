import assert from 'node:assert/strict';
import test from 'node:test';
import {HANDOVER_EVIDENCE_OPTIONS, handoverEvidenceMode,
  handoverExportNotice} from '../src/sinter/web/casebook-handover.js';

test('saved explicit appendix scope is preserved and absent legacy scope stays compact', () => {
  assert.equal(handoverEvidenceMode(), 'compact');
  assert.equal(handoverEvidenceMode({}), 'compact');
  assert.equal(handoverEvidenceMode({handover_evidence: 'compact'}), 'compact');
  assert.equal(handoverEvidenceMode({handover_evidence: 'selected_appendix'}), 'selected_appendix');
  assert.deepEqual(HANDOVER_EVIDENCE_OPTIONS.map(([value]) => value), ['compact', 'selected_appendix']);
  for (const value of [null, true, 1, [], {}, '', 'all_sources']) {
    assert.throws(() => handoverEvidenceMode({handover_evidence: value}), /compact handover notes/);
  }
});

test('export guidance states actual selected coverage without claiming whole-source answers', () => {
  const report = {document_type: 'handover', excerpts: Array.from({length: 9}, () => ({}))};
  const compact = handoverExportNotice(report);
  assert.match(compact, /includes 4 of 9 selected passages/);
  assert.match(compact, /Additional passages stay in Evidence/);
  const full = handoverExportNotice({...report, handover_evidence: 'selected_appendix'});
  assert.match(full, /includes all 9 selected passages/);
  assert.match(full, /Passages after the first four are in its appendix/);
  for (const notice of [compact, full]) {
    assert.match(notice, /not answered questions or a whole-source review/);
    assert.match(notice, /current document text.*edits can change/);
  }
});

test('richer model drafts never receive a source-only appendix guarantee', () => {
  assert.equal(handoverExportNotice({document_type: 'brief'}), '');
  assert.equal(handoverExportNotice({document_type: 'handover', model_draft: true,
    handover_evidence: 'selected_appendix', excerpts: [{}]}), '');
  assert.match(handoverExportNotice({document_type: 'handover', excerpts: []}), /includes 0 of 0/);
  const empty = handoverExportNotice({document_type: 'handover', handover_evidence: 'selected_appendix', excerpts: []});
  assert.match(empty, /all 0 selected passages/);
  assert.doesNotMatch(empty, /in its appendix/);
});
