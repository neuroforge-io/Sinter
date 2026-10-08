import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash, webcrypto} from 'node:crypto';
import {compileHandoverSummary, handoverSummaryQuote, applyHandoverSummary, handoverSummaryAvailable, handoverSummaryEditor} from '../src/sinter/web/handover-summary.js';
import {applyDocumentEdit, documentMarkdown} from '../src/sinter/web/documents.js';
import {registerReportDraft, trackReportEdits, trackReportEditor, markReportSaved, isReportDraftUnsaved, clearReportDrafts, trackReportForm, reportFormDraft, clearReportForm, hasUnsavedReportDrafts, unsavedReportDrafts, reportDraftNotice} from '../src/sinter/web/report-drafts.js';
if (!globalThis.crypto) Object.defineProperty(globalThis, 'crypto', {configurable: true, value: webcrypto});
const oracle = JSON.parse(readFileSync(new URL('fixtures/handover_pre_recipient_v1.json', import.meta.url)));
const fixture = (name = 'installed_garden') => structuredClone(oracle.fixtures[name].report);
const sha = value => createHash('sha256').update(value).digest('hex');
function row(fields = {}) {
  return {item: 'Equipment quote', status: 'Not received', proposedAction: 'Obtain an itemised quote and confirm a named owner',
    period: 'as_recorded', ownerType: 'unknown', ownerName: '', ownerAcceptance: 'unconfirmed', targetDate: '', evidence: null, ...fields};
}
function selection(report, quote, passage = 0) {
  const excerpt = report.excerpts[passage];
  const index = excerpt.quote.indexOf(quote); assert.ok(index >= 0, quote);
  const questionIndex = report.question_index.findIndex(question => question.excerpt_ids.includes(excerpt.id));
  const start = excerpt.start + Array.from(excerpt.quote.slice(0, index)).length;
  return {questionIndex, excerptId: excerpt.id, start, end: start + Array.from(quote).length, quote};
}
function exampleRows(report) {
  return [row({evidence: selection(report, 'The equipment quote has not been received.')}),
    row({item: 'Funding checks', status: 'Applicant conditions, current window and supported costs have not been checked',
      proposedAction: 'Name an owner and check current official guidance', ownerType: 'unassigned',
      evidence: selection(report, 'The guideline-checking action has no assigned owner.')}),
    row({item: 'Watering', status: 'No named volunteer has accepted', proposedAction: 'Ask a named volunteer to accept',
      ownerType: 'role', ownerName: 'Volunteer coordinator', evidence: selection(report, 'A volunteer coordinator is only a suggested role.')}),
    row({item: 'Timing', status: 'Practice target, not a confirmed closing date', proposedAction: 'Agree responsibility before confirming an appropriate target',
      targetDate: '2026-10-09', evidence: selection(report, 'The 9 October 2026 date is a proposed practice target, not a confirmed deadline or grant closing date.')}),
    row({item: 'Earlier round', period: 'historical', status: 'Recorded closed in the earlier notes',
      proposedAction: 'Retain old wording; check current guidance before reuse', evidence: selection(report, 'That round is recorded closed.')}),
    row({item: 'Insurance excess', status: 'Not supplied in these originals', proposedAction: 'Ask for the relevant policy record'})];
}

if (process.argv.includes('--sample-json')) {
  const report = fixture();
  if (process.argv.includes('--stale')) report.review_status = 'stale';
  const before = structuredClone(report);
  const compiled = await compileHandoverSummary(report, exampleRows(report));
  applyDocumentEdit(report, compiled.markdown, '2026-10-03T00:00:00.000Z');
  console.log(JSON.stringify({original: before, applied: report, quotations: compiled.quotations}));
} else {
  test('recipient opening contains explicit statuses and proposals before questions; historical originals/references remain exact', async () => {
    const report = fixture(), before = structuredClone(report);
    const result = await compileHandoverSummary(report, exampleRows(report));
    assert.ok(result.markdown.indexOf('## At a glance') < result.markdown.indexOf('## Handover next steps'));
    assert.match(result.markdown, /\| Equipment quote \| As recorded: Not received/);
    assert.match(result.markdown, /\| Funding checks \|.*Unassigned; no owner has been recorded/);
    assert.match(result.markdown, /Suggested role: Volunteer coordinator; acceptance unconfirmed/);
    assert.match(result.markdown, /Owner type unknown; acceptance unconfirmed/);
    assert.match(result.markdown, /Proposed target 2026-10-09 \(unconfirmed; not a funder deadline\)/);
    assert.match(result.markdown, /Historical wording: Recorded closed in the earlier notes/);
    assert.match(result.markdown, /\| Insurance excess \|[^\n]*\| Missing supporting record; answer remains unknown \|/);
    assert.equal(result.quotations.length, 5);
    assert.deepEqual(result.quotations.map(quote => quote.position), [1, 2, 3, 4, 5]);
    assert.ok(result.markdown.endsWith(before.document_markdown.slice(before.document_markdown.indexOf('## Handover next steps\n'))));
    assert.ok(result.markdown.includes('in\\_progress'));
    assert.equal(result.markdown.split('## Passage reference key').length, 2);
    assert.deepEqual(report, before);
  });

  test('a table stays one contiguous block and literal user text cannot inject links, HTML or columns', async () => {
    const report = fixture();
    const result = await compileHandoverSummary(report, [row({item: '<script>|[fake](https://example.invalid)', status: 'Unknown & not zero'})]);
    assert.match(result.markdown, /\| Item[^\n]*\n\| ---[^\n]*\n\| &lt;script&gt;\\\|\\\[fake\\\]/);
    assert.match(result.markdown, /Unknown &amp; not zero/);
    assert.doesNotMatch(result.openingMarkdown, /\|[^\n]*\n\n\|/);
  });

  test('generated status separators preserve entered punctuation and leave source evidence and row inputs unchanged', async () => {
    const report = fixture(), before = structuredClone(report);
    const entered = [row({status: 'Not received.  Keep café 🐝 & <wording>| exactly.',
      evidence: selection(report, 'The equipment quote has not been received.')})];
    const originalRows = structuredClone(entered);
    const result = await compileHandoverSummary(report, entered);
    assert.match(result.openingMarkdown, /Not received\.  Keep café 🐝 &amp; &lt;wording&gt;\\\| exactly\. · Owner type unknown; acceptance unconfirmed · Proposed target not supplied/);
    assert.doesNotMatch(result.openingMarkdown, /exactly\.;/);
    assert.deepEqual(entered, originalRows);
    assert.deepEqual(report, before);
    assert.equal(result.quotations[0].quote, entered[0].evidence.quote);
    assert.ok(result.markdown.endsWith(before.document_markdown.slice(before.document_markdown.indexOf('## Handover next steps\n'))));
  });

  test('Unicode literal selection binds code points, exact quote and admitted Passage alias', async () => {
    const report = fixture('unscoped_golden'), quote = 'No supplier quote, approval or availability was received. 🐝';
    const evidence = selection(report, quote);
    const selected = await handoverSummaryQuote(report, evidence);
    assert.equal(selected.quote, quote); assert.equal(selected.label, 'Passage 1'); assert.ok(Object.isFrozen(selected));
    const unicode = '🐝e\u0301 prefix. ' + quote;
    report.sources[0].content = unicode; report.sources[0].sha256 = report.source_register[0].sha256 = sha(unicode);
    report.excerpts[0] = {...report.excerpts[0], start: 0, end: Array.from(unicode).length, quote: unicode};
    report.document_references[0] = {...report.document_references[0], start: 0, end: Array.from(unicode).length};
    const bound = selection(report, quote);
    assert.equal(bound.start, Array.from('🐝e\u0301 prefix. ').length);
    assert.equal((await handoverSummaryQuote(report, bound)).quote, quote);
  });

  test('wrong offsets, modified quote, wrong question, foreign excerpt and forged alias are refused without mutation', async () => {
    const report = fixture(), evidence = selection(report, 'The equipment quote has not been received.');
    for (const fields of [{start: evidence.start + 1}, {end: evidence.end + 1}, {start: true},
      {quote: 'A quote was received'}, {questionIndex: -1}, {excerptId: 'foreign'}, {quote: evidence.quote.slice(0, -1)}]) {
      const before = structuredClone(report);
      await assert.rejects(handoverSummaryQuote(report, {...evidence, ...fields})); assert.deepEqual(report, before);
    }
    report.document_references[0].label = 'Passage 99';
    await assert.rejects(handoverSummaryQuote(report, evidence), /Passage reference/);
  });

  test('changed surrounding source, ambiguous identities and unavailable source hashes never borrow newer project data', async () => {
    for (const change of [r => {r.sources.find(source => source.id === r.excerpts[0].source_id).content += '\nLater unrelated wording';},
      r => r.sources.push({...r.sources.find(source => source.id === r.excerpts[0].source_id)}), r => {delete r.source_register.find(source => source.id === r.excerpts[0].source_id).sha256;},
      r => {r.source_register.find(source => source.id === r.excerpts[0].source_id).sha256 = '0'.repeat(64);}]) {
      const report = fixture(), evidence = selection(report, 'The equipment quote has not been received.');
      change(report); const before = structuredClone(report);
      await assert.rejects(compileHandoverSummary(report, [row({evidence})])); assert.deepEqual(report, before);
    }
  });

  test('selection from a different question scope is unavailable even when the same original text exists', async () => {
    const report = fixture(), evidence = selection(report, 'The equipment quote has not been received.');
    const question = report.question_index[evidence.questionIndex];
    report.question_scopes = [{question_index: evidence.questionIndex, question: question.question, source_ids: []}];
    await assert.rejects(handoverSummaryQuote(report, evidence), /passage is unavailable/);
  });

  test('unsupported model/partial/campaign/malformed checklist reports cannot gain a source-only summary', async () => {
    for (const fields of [{model_draft: true}, {incomplete: true}, {workflow: 'campaign'}, {document_type: 'brief'},
      {document_markdown: 'Only an edited fragment'}, {question_index: undefined}]) {
      const report = {...fixture(), ...fields}; assert.equal(handoverSummaryAvailable(report), false);
      await assert.rejects(compileHandoverSummary(report, [row()]));
    }
  });

  test('unknown, unassigned, role and named-person acceptance stay distinct; unsupported commitments are refused', async () => {
    const report = fixture();
    for (const fields of [{ownerType: 'unknown', ownerName: 'Invented person'}, {ownerType: 'unassigned', ownerAcceptance: 'user_marked_accepted'},
      {ownerType: 'role', ownerName: 'Coordinator', ownerAcceptance: 'user_marked_accepted'}, {ownerType: 'person', ownerName: ''},
      {ownerType: 'bogus'}, {ownerAcceptance: true}]) await assert.rejects(compileHandoverSummary(report, [row(fields)]));
    const result = await compileHandoverSummary(report, [row({ownerType: 'person', ownerName: 'Fictional named volunteer', ownerAcceptance: 'user_marked_accepted'})]);
    assert.match(result.markdown, /Named person: Fictional named volunteer; acceptance marked by the user \(not independently verified\)/);
  });

  test('dates cannot become confirmed deadlines or malformed calendar dates; absent date/cost are not zero', async () => {
    const report = fixture();
    for (const date of ['0000-01-01', '2026-02-29', '2026-13-01', 'tomorrow', null, true]) await assert.rejects(compileHandoverSummary(report, [row({targetDate: date})]));
    const result = await compileHandoverSummary(report, [row({status: 'Cost and date unknown'})]);
    assert.match(result.markdown, /Cost and date unknown/); assert.match(result.markdown, /Proposed target not supplied/);
    assert.doesNotMatch(result.openingMarkdown, /\$0|confirmed deadline/);
  });

  test('missing-answer rows cannot manufacture a citation by typing a registered Passage or source ID', async () => {
    const report = fixture();
    for (const fields of [{item: 'Passage 1'}, {status: report.sources[0].id}, {proposedAction: report.excerpts[0].id}]) {
      await assert.rejects(compileHandoverSummary(report, [row(fields)]), /Choose evidence/);
    }
    const result = await compileHandoverSummary(report, [row()]);
    assert.equal(result.quotations.length, 0); assert.doesNotMatch(result.openingMarkdown, /Passage \d+/);
  });

  test('unselected original metadata is not promoted to full text/history; compact reference key remains unchanged', async () => {
    const report = fixture('appendix_compact'), before = structuredClone(report);
    report.source_register.push({id: 'SmetadataOnly', title: 'Unselected historical record', sha256: sha('Not retained text')});
    const result = await compileHandoverSummary(report, [row()]);
    assert.match(result.openingMarkdown, /not full supplied history/);
    assert.doesNotMatch(result.markdown, /Not retained text/);
    assert.ok(result.markdown.endsWith(before.document_markdown.slice(before.document_markdown.indexOf('## Handover next steps\n'))));
  });

  test('explicit cancellation keeps an edited draft and original evidence; approved replacement uses only normal document_edits', async () => {
    const report = fixture(); applyDocumentEdit(report, 'Existing human draft', '2026-10-02T00:00:00.000Z');
    const before = structuredClone(report), compiled = await compileHandoverSummary(report, [row()]); let calls = 0;
    const options = {currentMarkdown: () => documentMarkdown(report), confirm: async () => false,
      apply: value => {calls++; applyDocumentEdit(report, value, '2026-10-03T00:00:00.000Z');}};
    assert.equal(await applyHandoverSummary(report, compiled, options), false); assert.equal(calls, 0); assert.deepEqual(report, before);
    assert.equal(await applyHandoverSummary(report, compiled, {...options, confirm: async () => true}), true);
    assert.equal(calls, 1); assert.equal(report.document_edits.author, 'user');
    assert.deepEqual({...report, document_edits: before.document_edits}, before);
  });

  test('source/report changes after compilation and edits made during replacement confirmation are never overwritten', async () => {
    const report = fixture(), compiled = await compileHandoverSummary(report, [row()]);
    report.review_status = 'stale'; let called = false;
    await assert.rejects(applyHandoverSummary(report, compiled, {currentMarkdown: () => documentMarkdown(report),
      confirm: async () => true, apply: () => {called = true;}}), /changed during review/); assert.equal(called, false);
    const edited = fixture(); applyDocumentEdit(edited, 'Earlier edit');
    const next = await compileHandoverSummary(edited, [row()]);
    await assert.rejects(applyHandoverSummary(edited, next, {currentMarkdown: () => documentMarkdown(edited),
      confirm: async () => {applyDocumentEdit(edited, 'Newer edit'); return true;}, apply: () => {called = true;}}), /newer wording is kept/);
    assert.equal(documentMarkdown(edited), 'Newer edit'); assert.equal(called, false);
  });

  test('invalid or oversized edits leave local work intact, with no truncation or summary application', async () => {
    const report = fixture(), before = structuredClone(report);
    for (const value of ['', '   ', null, 'x'.repeat(500001)]) {
      assert.throws(() => applyDocumentEdit(report, value)); assert.deepEqual(report, before);
    }
    for (const fields of [{status: ''}, {proposedAction: ''}, {period: 'current_verified'}, {item: 'x'.repeat(1001)}, {status: 'first\nsecond'}]) {
      await assert.rejects(compileHandoverSummary(report, [row(fields)])); assert.deepEqual(report, before);
    }
    report.document_markdown = report.document_markdown.replace('## Handover next steps\n', 'x'.repeat(500000) + '\n## Handover next steps\n');
    const large = structuredClone(report); await assert.rejects(compileHandoverSummary(report, [row()]), /limit/); assert.deepEqual(report, large);
  });

  test('summary applies through the existing unsaved/save/reopen document route; stale review and evidence survive', async () => {
    clearReportDrafts(); const report = fixture(); report.review_status = 'stale';
    const original = structuredClone(report); registerReportDraft(report, documentMarkdown(report));
    const result = await compileHandoverSummary(report, exampleRows(report));
    await applyHandoverSummary(report, result, {currentMarkdown: () => documentMarkdown(report), confirm: async () => true,
      apply: text => {applyDocumentEdit(report, text); trackReportEdits(report, documentMarkdown(report));}});
    assert.equal(isReportDraftUnsaved(report), true); markReportSaved(report, documentMarkdown(report));
    assert.equal(isReportDraftUnsaved(report), false);
    const reopened = JSON.parse(JSON.stringify(report)); assert.equal(documentMarkdown(reopened), result.markdown);
    for (const key of ['markdown','sources','excerpts','source_register','casebook_fingerprint','document_references','review_status']) assert.deepEqual(reopened[key], original[key]);
    assert.equal(Object.hasOwn(reopened, 'handover_summary'), false); clearReportDrafts();
  });
  test('unapplied summary rows join the existing navigation/quit guard and restore independently of ordinary text edits', () => {
    clearReportDrafts(); const report = fixture(); registerReportDraft(report, documentMarkdown(report));
    const rows = {rows: [row({status: 'Unfinished local wording'})], open: true};
    trackReportForm(report, 'handover-summary', rows);
    assert.equal(hasUnsavedReportDrafts(), true); assert.equal(unsavedReportDrafts()[0].report, report);
    registerReportDraft(report, documentMarkdown(report));
    const restored = reportFormDraft(report, 'handover-summary'); assert.deepEqual(restored, rows);
    restored.rows[0].status = 'Detached local copy'; assert.equal(reportFormDraft(report, 'handover-summary').rows[0].status, 'Unfinished local wording');
    markReportSaved(report, documentMarkdown(report)); assert.equal(hasUnsavedReportDrafts(), true);
    trackReportEdits(report, 'Ordinary draft edited'); assert.deepEqual(reportFormDraft(report, 'handover-summary'), rows);
    clearReportForm(report, 'handover-summary'); assert.equal(hasUnsavedReportDrafts(), true);
    markReportSaved(report, 'Ordinary draft edited'); assert.equal(hasUnsavedReportDrafts(), false); clearReportDrafts();
  });

  test('size/source refusal keeps unapplied row inputs and applied draft under the same unsaved guard', async () => {
    clearReportDrafts(); const report = fixture(); applyDocumentEdit(report, 'Existing applied draft');
    registerReportDraft(report, documentMarkdown(report));
    const entered = {rows: [row({status: 'x'.repeat(1001)})], open: true};
    trackReportForm(report, 'handover-summary', entered);
    await assert.rejects(compileHandoverSummary(report, entered.rows));
    assert.equal(documentMarkdown(report), 'Existing applied draft');
    assert.deepEqual(reportFormDraft(report, 'handover-summary'), entered); assert.equal(hasUnsavedReportDrafts(), true);
    clearReportDrafts();
  });

  test('applied summary clears only its own pending form; saving cannot erase another unapplied editor', async () => {
    clearReportDrafts(); const report = fixture(); registerReportDraft(report, documentMarkdown(report));
    trackReportForm(report, 'handover-summary', {rows: [row()], open: true});
    trackReportForm(report, 'separate-local-form', {text: 'Other pending work'});
    const compiled = await compileHandoverSummary(report, [row()]);
    applyDocumentEdit(report, compiled.markdown); trackReportEdits(report, documentMarkdown(report));
    clearReportForm(report, 'handover-summary'); markReportSaved(report, documentMarkdown(report));
    assert.equal(reportFormDraft(report, 'handover-summary'), undefined);
    assert.deepEqual(reportFormDraft(report, 'separate-local-form'), {text: 'Other pending work'});
    assert.equal(hasUnsavedReportDrafts(), true); clearReportForm(report, 'separate-local-form'); assert.equal(hasUnsavedReportDrafts(), false);
    assert.equal(Object.hasOwn(report, 'forms'), false); clearReportDrafts();
  });

  // A small inert DOM checks actual editor event wiring without a browser/app.
  function inertDOM() {
    const previous = {document: globalThis.document, Node: globalThis.Node, window: globalThis.window};
    class Element {
      constructor(tag = '') { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map();
        this.value = ''; this.hidden = false; this.disabled = false; this.checked = false; this.open = false;
        this.selectionStart = 0; this.selectionEnd = 0; this.className = ''; this._text = ''; }
      set textContent(value) { this._text = String(value); this.children = []; }
      get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
      append(...children) { for (const child of children) { this.children.push(child); child.parentElement = this; } }
      replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
      setAttribute(key, value) { this[key] = value; }
      addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(fn); }
      async fire(type) { for (const fn of this.listeners.get(type) || []) await fn({currentTarget: this, preventDefault() {}}); }
      focus() { document.activeElement = this; } showModal() { this.open = true; } close() { this.open = false; }
      remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this); }
      get classList() { return {add: value => {this.className += ' ' + value;}}; }
    }
    globalThis.Node = Element;
    globalThis.document = {createElement: tag => new Element(tag), createTextNode: text => {const n = new Element(); n.textContent = text; return n;}, body: new Element('body')};
    globalThis.window = {addEventListener() {}};
    const all = (node, tag) => [node, ...node.children.flatMap(child => all(child, tag))].filter(row => !tag || row.tagName === tag.toUpperCase());
    const button = (node, name) => all(node, 'button').find(row => row.textContent === name);
    return {all, button, restore: () => {Object.assign(globalThis, previous);}};
  }

  test('actual editor events retain invalid/unapplied rows on navigation and refusal; they restore under quit protection', async () => {
    const dom = inertDOM(); clearReportDrafts();
    try {
      const report = fixture(); registerReportDraft(report, documentMarkdown(report));
      const actions = {canUseDocument: () => true, currentMarkdown: () => documentMarkdown(report),
        applyMarkdown: text => {applyDocumentEdit(report, text); trackReportEdits(report, text);}};
      const first = handoverSummaryEditor(report, {actions});
      assert.equal(hasUnsavedReportDrafts(), false);
      const inputs = dom.all(first, 'input').filter(input => input.type !== 'checkbox');
      inputs[0].value = 'Insurance excess'; inputs[1].value = 'x'.repeat(1001); inputs[2].value = 'Ask for the policy';
      await first.fire('input'); assert.equal(hasUnsavedReportDrafts(), true);
      await dom.button(first, 'Preview opening summary').fire('click');
      assert.equal(documentMarkdown(report), report.document_markdown);
      assert.equal(reportFormDraft(report, 'handover-summary').rows[0].status.length, 1001);
      const restored = handoverSummaryEditor(report, {actions});
      assert.equal(restored.open, true); assert.equal(dom.all(restored, 'input')[1].value.length, 1001);
      assert.equal(hasUnsavedReportDrafts(), true);
      const restoredInputs = dom.all(restored, 'input'); restoredInputs[1].value = 'Not supplied'; await restored.fire('input');
      await dom.button(restored, 'Preview opening summary').fire('click');
      const apply = dom.button(restored, 'Apply reviewed opening summary'); assert.equal(apply.hidden, false);
      await apply.fire('click'); assert.equal(reportFormDraft(report, 'handover-summary'), undefined);
      assert.match(documentMarkdown(report), /At a glance/); assert.equal(hasUnsavedReportDrafts(), true);
      markReportSaved(report, documentMarkdown(report)); assert.equal(hasUnsavedReportDrafts(), false);
    } finally {dom.restore(); clearReportDrafts();}
  });

  test('actual editor replacement cancellation and a changed form during approval preserve newer input', async () => {
    const dom = inertDOM(); clearReportDrafts();
    try {
      const report = fixture(); applyDocumentEdit(report, 'Existing human draft'); registerReportDraft(report, documentMarkdown(report));
      const actions = {canUseDocument: () => true, currentMarkdown: () => documentMarkdown(report),
        applyMarkdown: text => {applyDocumentEdit(report, text); trackReportEdits(report, text);}};
      const editor = handoverSummaryEditor(report, {actions}), inputs = dom.all(editor, 'input');
      inputs[0].value = 'Insurance excess'; inputs[1].value = 'Not supplied'; inputs[2].value = 'Ask for the policy'; await editor.fire('input');
      await dom.button(editor, 'Preview opening summary').fire('click');
      let operation = dom.button(editor, 'Apply reviewed opening summary').fire('click');
      await dom.button(document.body, 'Cancel').fire('click'); await operation;
      assert.equal(documentMarkdown(report), 'Existing human draft'); assert.ok(reportFormDraft(report, 'handover-summary'));
      operation = dom.button(editor, 'Apply reviewed opening summary').fire('click');
      inputs[1].value = 'Newer status entered during approval'; await editor.fire('input');
      await dom.button(document.body, 'Replace edited draft').fire('click'); await operation;
      assert.equal(documentMarkdown(report), 'Existing human draft');
      assert.equal(reportFormDraft(report, 'handover-summary').rows[0].status, 'Newer status entered during approval');
      assert.equal(hasUnsavedReportDrafts(), true);
    } finally {dom.restore(); clearReportDrafts();}
  });

  test('explicit removal drops only the chosen form item; other rows and the applied document remain intact', async () => {
    const dom = inertDOM(); clearReportDrafts();
    try {
      const report = fixture(); registerReportDraft(report, documentMarkdown(report));
      const before = structuredClone(report), actions = {canUseDocument: () => true, currentMarkdown: () => documentMarkdown(report), applyMarkdown: value => applyDocumentEdit(report, value)};
      const editor = handoverSummaryEditor(report, {actions});
      dom.all(editor, 'input')[0].value = 'First user-entered item'; await editor.fire('input');
      await dom.button(editor, 'Add summary item').fire('click');
      const second = dom.all(editor, 'fieldset')[1]; dom.all(second, 'input')[0].value = 'Second item retained'; await editor.fire('input');
      await dom.button(editor, 'Remove this summary item').fire('click');
      assert.equal(reportFormDraft(report, 'handover-summary').rows.length, 1);
      assert.equal(reportFormDraft(report, 'handover-summary').rows[0].item, 'Second item retained');
      assert.deepEqual(report, before); assert.equal(hasUnsavedReportDrafts(), true);
      await dom.button(editor, 'Remove this summary item').fire('click');
      assert.equal(reportFormDraft(report, 'handover-summary'), undefined); assert.equal(hasUnsavedReportDrafts(), false);
      assert.equal(dom.all(editor, 'fieldset').length, 1); assert.deepEqual(report, before);
    } finally {dom.restore(); clearReportDrafts();}
  });


  test('collapsed item captions retain full values; Add opens and focuses only the new Item', async () => {
    const dom = inertDOM(); clearReportDrafts();
    try {
      const report = fixture(); registerReportDraft(report, documentMarkdown(report));
      const editor = handoverSummaryEditor(report, {actions: {canUseDocument: () => true, currentMarkdown: () => documentMarkdown(report), applyMarkdown() {}}});
      const itemPanels = () => dom.all(editor, 'details').filter(node => node.className === 'handover-summary-item');
      const first = itemPanels()[0], inputs = dom.all(first, 'input');
      inputs[0].value = 'First complete item'; inputs[1].value = 'x'.repeat(500); inputs[2].value = 'Keep this whole proposed step';
      await editor.fire('input');
      assert.match(dom.all(first, 'summary')[0].textContent, /First complete item/);
      assert.ok(dom.all(first, 'summary')[0].textContent.length < 250);
      await dom.button(editor, 'Add summary item').fire('click');
      const second = itemPanels()[1];
      assert.equal(first.open, false); assert.equal(second.open, true);
      assert.equal(document.activeElement, dom.all(second, 'input')[0]);
      assert.equal(reportFormDraft(report, 'handover-summary').rows[0].status, 'x'.repeat(500));
      assert.equal(reportFormDraft(report, 'handover-summary').rows[0].open, false);
      assert.equal(reportFormDraft(report, 'handover-summary').rows[1].open, true);
      second.open = false; await second.fire('toggle'); first.open = true; await first.fire('toggle');
      const restored = handoverSummaryEditor(report, {actions: {canUseDocument: () => true, currentMarkdown: () => documentMarkdown(report), applyMarkdown() {}}});
      const restoredPanels = dom.all(restored, 'details').filter(node => node.className === 'handover-summary-item');
      assert.equal(restoredPanels[0].open, true); assert.equal(restoredPanels[1].open, false);
      assert.equal(dom.all(restoredPanels[0], 'input')[1].value, 'x'.repeat(500));
      assert.equal(hasUnsavedReportDrafts(), true);
    } finally {dom.restore(); clearReportDrafts();}
  });

  test('caption distinguishes missing, unselected and literal evidence; only actual selected wording is stored', async () => {
    const dom = inertDOM(); clearReportDrafts();
    try {
      const report = fixture(); registerReportDraft(report, documentMarkdown(report));
      const editor = handoverSummaryEditor(report, {actions: {canUseDocument: () => true, currentMarkdown: () => documentMarkdown(report), applyMarkdown() {}}});
      const panel = dom.all(editor, 'details').find(node => node.className === 'handover-summary-item');
      const caption = dom.all(panel, 'summary')[0], source = dom.all(panel, 'select')[2];
      assert.match(caption.textContent, /No supporting record; no citation/);
      source.value = source.children[1].value; await source.fire('change');
      assert.match(caption.textContent, /Exact wording still needed/);
      const original = dom.all(panel, 'textarea')[0]; original.selectionStart = 0; original.selectionEnd = 20;
      await dom.button(panel, 'Use selected wording').fire('click');
      assert.match(caption.textContent, /Literal wording selected/);
      assert.equal(reportFormDraft(report, 'handover-summary').rows[0].evidence.quote, original.value.slice(0, 20));
      source.value = ''; await source.fire('change');
      assert.match(caption.textContent, /No supporting record; no citation/);
      assert.equal(reportFormDraft(report, 'handover-summary').rows[0].evidence, null);
    } finally {dom.restore(); clearReportDrafts();}
  });

  test('Apply follows the rendered preview; a view-only collapse preserves the reviewed semantic rows', async () => {
    const dom = inertDOM(); clearReportDrafts();
    try {
      const report = fixture(); registerReportDraft(report, documentMarkdown(report));
      const editor = handoverSummaryEditor(report, {actions: {canUseDocument: () => true, currentMarkdown: () => documentMarkdown(report),
        applyMarkdown: value => {applyDocumentEdit(report, value); trackReportEdits(report, value);}}});
      const panel = dom.all(editor, 'details').find(node => node.className === 'handover-summary-item'), inputs = dom.all(panel, 'input');
      inputs[0].value = 'Insurance excess'; inputs[1].value = 'Unknown'; inputs[2].value = 'Ask for the policy'; await editor.fire('input');
      await dom.button(editor, 'Preview opening summary').fire('click');
      const flattened = dom.all(editor), title = flattened.find(node => node.tagName === 'H3' && node.textContent === 'Opening summary preview');
      const apply = dom.button(editor, 'Apply reviewed opening summary');
      assert.ok(flattened.indexOf(apply) > flattened.indexOf(title)); assert.equal(apply.hidden, false);
      panel.open = false; await panel.fire('toggle'); await apply.fire('click');
      assert.match(documentMarkdown(report), /At a glance/); assert.equal(reportFormDraft(report, 'handover-summary'), undefined);
    } finally {dom.restore(); clearReportDrafts();}
  });

  test('pending messages distinguish summary forms, text editors and applied unsaved edits after an exact save', () => {
    clearReportDrafts(); const report = fixture(); registerReportDraft(report, documentMarkdown(report));
    trackReportForm(report, 'handover-summary', {rows: [row()], open: true});
    assert.equal(reportDraftNotice(report), 'Summary rows have not been applied; they are kept in this session only.');
    markReportSaved(report, documentMarkdown(report));
    assert.equal(reportDraftNotice(report), 'Summary rows have not been applied; they are kept in this session only.');
    assert.equal(hasUnsavedReportDrafts(), true);
    trackReportEditor(report, 'Pending typed text');
    assert.match(reportDraftNotice(report), /Draft text is waiting to be applied/);
    trackReportEdits(report, 'Applied changed document');
    assert.match(reportDraftNotice(report), /Applied document edits have not been saved/);
    assert.doesNotMatch(reportDraftNotice(report), /Draft text is waiting/);
    markReportSaved(report, 'Applied changed document');
    assert.doesNotMatch(reportDraftNotice(report), /Applied document edits/);
    assert.match(reportDraftNotice(report), /Summary rows have not been applied/);
    clearReportForm(report, 'handover-summary'); assert.equal(reportDraftNotice(report), ''); clearReportDrafts();
  });

  test('stale saved review is explicit in the recipient opening, without changing original status or evidence', async () => {
    const report = fixture(); report.review_status = 'stale'; const before = structuredClone(report);
    const compiled = await compileHandoverSummary(report, [row()]);
    assert.match(compiled.openingMarkdown, /Review status: stale/);
    assert.ok(compiled.openingMarkdown.indexOf('Review status: stale') < compiled.openingMarkdown.indexOf('| Item |'));
    assert.deepEqual(report, before);
    const current = fixture(); current.review_status = 'draft';
    assert.doesNotMatch((await compileHandoverSummary(current, [row()])).openingMarkdown, /Review status: stale/);
  });

}
