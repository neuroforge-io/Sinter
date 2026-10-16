import {h, button, field, selectField, check, notice, announce} from './ui.js';
import {request, waitForJob} from './api.js';
import {renderReport} from './reports.js';
import {audioForm} from './audio.js';
import {senderFields} from './profile.js';
import {campaignLetterReviewCopy} from './campaign-letter.js';
import {briefOpeningCopy, openingParagraphProblem, OPENING_LIMIT} from './brief-opening.js';
import {confirmAction} from './confirm-action.js';
import {registerReportDraft} from './report-drafts.js';
import {documentMarkdown} from './documents.js';
import {authorizeReportReplacement, reportReplacementStillAllowed,
  retainReportResult, reportCorrectionPayload} from './report-replacement.js';

const titles = {research: 'Research a topic.', grants: 'Find funding for good ideas.', brief: 'Prepare a letter for review.', meeting: 'Prepare a clear meeting record.'};
const descriptions = {
  research: 'Explore a topic through source highlights, citations and gaps to investigate. Keep the original wording within reach.',
  grants: 'Discover opportunities, then check actual requirements. No invented deadlines or automatic eligibility decisions.',
  brief: 'Add the context and what you need to know. Your saved details complete the sign-off; supporting sources stay attached.',
  meeting: 'Import a transcript or transcribe audio locally. Confirm speakers and corrections before preparing draft minutes.'
};

export async function workbench(kind, {example = false, seed = {}, setBusy, remember, onDraftWithModel}) {
  const [data, preferences] = await Promise.all([example ? request(`/api/example?workflow=${kind}`) : seed, request('/api/settings')]);
  const settings = example ? {} : preferences.settings;
  const root = h('div', {class: 'workbench-page'});
  const demo = Boolean(data.demo);
  const campaignSenderReview = data.campaign_sender_review === true;
  const sources = [...(data.sources || [])];
  let speakerMap = {...(data.speaker_map || {})}, corrections = [...(data.corrections || [])];
  let running = false, jobId, preparedInputKey = null, currentResult = null, decisionController;
  const retainedResults = new Map();
  const title = field(kind === 'research' ? 'Research topic' : 'Project name', 'text', data.title || '', 'A name you will recognise later.', {required: true, maxLength: 200});
  const campaignNotes = kind === 'brief' && campaignSenderReview;
  const notes = field(kind === 'meeting' ? 'Transcript' : campaignNotes ? 'Internal notes and evidence context' : 'Your notes and context', 'textarea', data.notes || '',
    kind === 'meeting' ? 'Paste Speaker: words, or import TXT, SRT, VTT or JSON segments. Unlabelled turns remain unidentified.'
      : campaignNotes ? 'When preparing locally, campaign notes and reference quotations stay in the evidence pack in every format. Use the opening paragraph and explicit questions for text the recipient should read.'
        + (onDraftWithModel && !demo ? ' Draft with your model lets you review this context before sending it to the model.' : '')
      : 'Keep original wording where it matters. Notes are labelled as notes, not verified facts.', {rows: 7, maxLength: kind === 'meeting' ? 1000000 : 200000});
  const questions = field('Questions you need answered', 'textarea', data.questions || '', 'One question per line works well.', {rows: 4, maxLength: 12000});
  const query = field('Exact web search query', 'text', data.query || '', 'Only this query is sent to NeuroForge search. Avoid names and private details.', {maxLength: 1024});
  const search = check('Search the web for related material', !demo && (data.use_search ?? ['grants', 'research'].includes(kind)));
  if (kind === 'research' && !data.query) query.input.value = data.title || '';
  let queryEdited = Boolean(data.query && data.query !== data.title);
  query.input.addEventListener('input', () => { queryEdited = true; });
  title.input.addEventListener('input', () => {
    if (kind === 'research' && !queryEdited) query.input.value = title.input.value;
  });
  const ranking = check('Let the model rank a small set of source excerpts', !demo && Boolean(data.use_model));
  const org = field('Organisation type', 'text', data.profile?.organisation_type ?? settings.organisation_type ?? '', 'Use your actual legal structure, such as a state-school P&C association.');
  const location = field('Location', 'text', data.profile?.location ?? settings.location ?? '');
  const budget = field('Project budget', 'number', data.profile?.budget || '', 'Numbers only; record currency in your notes.', {min: '0', step: 'any'});
  const state = () => ({workflow: kind, title: title.input.value, notes: notes.input.value,
    questions: kind === 'meeting' ? '' : questions.input.value, query: kind === 'meeting' ? '' : query.input.value,
    use_search: kind !== 'meeting' && !demo && search.input.checked,
    use_model: kind !== 'meeting' && !demo && ranking.input.checked,
    demo, sources: [...sources], speaker_map: {...speakerMap}, corrections,
    document_type: documentType.input.value, recipient: recipient.input.value, ...sender.values(),
    ...(kind === 'brief' ? {opening_paragraph: opening.input.value} : {}),
    campaign_sender_review: campaignSenderReview,
    ...(Object.hasOwn(data, 'campaign_route_purpose')
      ? {campaign_route_purpose: data.campaign_route_purpose} : {}),
    campaign_link: data.campaign_link || null,
    profile: {organisation_type: org.input.value, location: location.input.value, budget: budget.input.value}});
  const documentType = selectField('What are you preparing?', [['enquiry', 'Enquiry letter'], ['briefing', 'Briefing note'], ['agenda', 'Agenda item for discussion']], data.document_type || 'enquiry');
  const openingCopy = briefOpeningCopy(documentType.input.value);
  const opening = field(openingCopy.label, 'textarea', data.opening_paragraph ?? '', openingCopy.help,
    {rows: 3});
  const openingHelp = opening.wrap.querySelector('small');
  const openingCount = h('small', {id: opening.input.id + '-count'});
  opening.wrap.append(openingCount);
  opening.input.setAttribute('aria-describedby', opening.input.id + '-help ' + openingCount.id);
  function updateOpening() {
    const copy = briefOpeningCopy(documentType.input.value);
    opening.wrap.querySelector('label').textContent = copy.label;
    openingHelp.textContent = copy.help + ` Plain text, up to ${OPENING_LIMIT.toLocaleString()} characters.`
      + (onDraftWithModel && !demo ? ' A model may revise it if you choose Draft with your model.' : '');
    openingCount.textContent = `${Array.from(opening.input.value).length.toLocaleString()} / ${OPENING_LIMIT.toLocaleString()} characters`;
    opening.input.setCustomValidity(openingParagraphProblem(opening.input.value));
  }
  opening.input.addEventListener('input', updateOpening);
  documentType.input.addEventListener('change', updateOpening);
  updateOpening();
  const recipient = field('Recipient or audience', 'text', data.recipient || '', '', {maxLength: 200});
  const sender = senderFields(data, settings);
  const campaignCopy = campaignSenderReview ? campaignLetterReviewCopy(data) : null;
  if (campaignSenderReview) sender.panel.open = true;
  const missingCampaignSigner = !data.signatory?.trim();
  const missingCampaignContact = !data.contact_details?.trim();
  const campaignSenderPrompt = !campaignSenderReview ? null : notice(
    missingCampaignSigner && missingCampaignContact
      ? 'No campaign signatory or contact details are recorded. This draft will have no sign-off. Add only approved details before using it.'
      : missingCampaignSigner
        ? 'No authorised campaign signatory is recorded. Confirm who may sign this letter before using it.'
        : missingCampaignContact
          ? 'No campaign reply contact is recorded. Add approved contact details before using this letter.'
          : 'Confirm that the campaign signatory and contact details below are approved for this letter before using it.');
  const form = h('form', {class: 'form-panel non-print'});
  const inputSummary = h('summary', {hidden: true}, 'Review or edit project inputs');
  const inputPanel = h('details', {class: 'project-inputs non-print', open: true}, inputSummary, form);
  const fields = h('fieldset', {}, h('legend', {class: 'sr-only'}, 'Project inputs'));
  const feedback = h('div', {'aria-live': 'polite'}), results = h('div');
  const recovery = h('section', {class: 'card stack non-print', hidden: true,
    'aria-label': 'Other drafts in this session'});
  const preparedState = h('p', {class: 'notice', role: 'status', hidden: true});
  function rememberInputs() {
    remember(kind, state());
    const changed = preparedInputKey !== null && preparedInputKey !== JSON.stringify(state());
    preparedState.hidden = !changed;
    preparedState.textContent = changed
      ? 'The draft below uses earlier inputs. Your changes are kept here; prepare again when you want an updated draft. The earlier document has not been changed.' : '';
  }
  const scope = h('p', {class: 'run-scope'});
  function updateScope() {
    scope.textContent = demo ? 'Offline example · No external requests' : kind === 'meeting' || (!search.input.checked && !ranking.input.checked) ?
      'On this computer · No external requests' : `Uses your configured API · ${search.input.checked ? 'Search query' : ''}${search.input.checked && ranking.input.checked ? ' + ' : ''}${ranking.input.checked ? 'selected source excerpts' : ''}`;
    query.input.required = !demo && kind !== 'meeting' && search.input.checked;
  }
  search.input.addEventListener('change', updateScope); ranking.input.addEventListener('change', updateScope); updateScope();
  const status = h('div', {class: 'progress', role: 'status'});
  const cancel = button('Cancel', async () => {
    if (jobId) await request('/api/jobs/cancel', {data: {id: jobId}})
      .catch(error => feedback.replaceChildren(notice(error.message, 'error')));
  });
  cancel.hidden = true;
  async function confirmReplacement() {
    const controller = new AbortController(); decisionController = controller;
    const observer = new MutationObserver(() => { if (!root.isConnected) controller.abort(); });
    observer.observe(document.body, {childList: true, subtree: true});
    try {
      return await confirmAction({title: 'Keep your earlier edits?',
        description: 'Preparing or opening another draft changes the displayed document. Your earlier edits stay available in Other drafts in this session below; they are not carried into the other draft. Save them in My workspace to keep them after this session.',
        confirmLabel: 'Keep edits and change draft', cancelLabel: 'Keep editing', signal: controller.signal});
    } finally { observer.disconnect(); if (decisionController === controller) decisionController = null; }
  }
  const replacementOptions = {confirm: confirmReplacement, isActive: () => root.isConnected};
  function refreshRecovery() {
    const others = [...retainedResults.values()].filter(entry => entry !== currentResult);
    recovery.hidden = !others.length;
    recovery.replaceChildren(h('h3', {}, 'Other drafts in this session'),
      notice('Each draft keeps its own original inputs, evidence and pending edits. Unsaved work stays in this browser session only. Open a draft and save it in My workspace to keep it after closing Sinter.'),
      ...others.map(entry => {
        const open = button(`${entry.shown ? 'Open earlier draft' : 'Open prepared draft'} ${entry.number}`, () => openRetained(entry), 'quiet');
        open.dataset.recoveryNumber = String(entry.number);
        return h('div', {class: 'stack'}, h('p', {}, entry.report.title), open);
      }));
    for (const control of recovery.querySelectorAll('button')) control.disabled = running;
  }
  function showResult(entry) {
    const {report, payload} = entry;
    const view = renderReport(report, {
      recovered: entry.shown,
      onEditInputs: () => { inputPanel.open = true; inputPanel.scrollIntoView({block: 'start'}); },
      onCorrect: changes => perform(reportCorrectionPayload(entry, changes), {validateInputs: false}),
      onCampaignUpdated: saved => {
        if (!payload.campaign_link || !saved?.document) return;
        const selected = saved.document.opportunities.findIndex(row => row.name === payload.campaign_link.opportunity);
        remember('campaigns', {document: saved.document, id: saved.id, revision: saved.revision,
          dirty: false, selected: Math.max(0, selected), tab: 'communications'});
      },
    });
    results.replaceChildren(view);
    currentResult = entry; entry.shown = true;
    corrections = structuredClone(payload.corrections || []);
    preparedInputKey = entry.inputKey;
    inputSummary.hidden = false; inputPanel.open = false;
    refreshRecovery(); rememberInputs();
    (recovery.hidden ? results : recovery).scrollIntoView({block: 'start'});
  }
  async function openRetained(entry) {
    if (running || !root.isConnected) return;
    const focus = document.activeElement;
    running = true; setBusy(true); fields.disabled = true; refreshRecovery();
    try {
      const authorization = await authorizeReportReplacement(currentResult?.report ?? null, replacementOptions);
      if (authorization && root.isConnected && reportReplacementStillAllowed(currentResult?.report ?? null, authorization)) {
        showResult(entry);
        status.textContent = `Showing draft ${entry.number}. Its original preparation inputs, evidence and pending edits are retained.`;
        announce('Selected local draft opened. Its original inputs and pending edits are retained.');
      }
    } catch (error) { if (root.isConnected) feedback.replaceChildren(notice(error.message, 'error')); }
    finally {
      running = false; fields.disabled = false; setBusy(false); refreshRecovery();
      const target = focus?.isConnected ? focus : recovery.querySelector(`[data-recovery-number="${entry.number}"]`);
      if (root.isConnected) target?.focus();
    }
  }
  async function perform(input, {validateInputs = true} = {}) {
    if (running || !root.isConnected || (validateInputs && !form.reportValidity())) return;
    const payload = structuredClone(input), focus = document.activeElement;
    let restoreFocus = true, started = false;
    running = true; setBusy(true); fields.disabled = true; refreshRecovery();
    try {
      const authorization = await authorizeReportReplacement(currentResult?.report ?? null, replacementOptions);
      if (!authorization || !root.isConnected) return;
      feedback.replaceChildren();
      status.textContent = 'Starting your evidence pack...'; cancel.hidden = false;
      const requestPayload = {...payload};
      delete requestPayload.campaign_link;
      started = true;
      const job = await request('/api/workbench', {data: requestPayload}); jobId = job.id;
      const report = await waitForJob(jobId, value => { status.textContent = value.message || 'Preparing...'; });
      report.input_snapshot = structuredClone(payload);
      report.profile = structuredClone(payload.profile);
      if (payload.campaign_link) report.campaign_link = structuredClone(payload.campaign_link);
      registerReportDraft(report, documentMarkdown(report));
      const entry = retainReportResult(report, payload, retainedResults.size + 1);
      retainedResults.set(entry.number, entry);
      if (!root.isConnected) return; // The completed result remains in Pending work; never replay it.
      if (!reportReplacementStillAllowed(currentResult?.report ?? null, authorization)) {
        status.textContent = 'New draft prepared. Your displayed draft changed while preparation was running. Open the prepared draft below when you are ready; your current edits have not been replaced.';
        announce('New draft retained separately. Your current edits have not been replaced.');
        return;
      }
      showResult(entry); restoreFocus = false;
      const reviewCopy = payload.campaign_sender_review
        ? campaignLetterReviewCopy(payload) : null;
      status.textContent = reviewCopy?.status || 'Draft ready. Review sources before using it.';
      announce(reviewCopy?.announcement || 'Your draft is ready for review.');
    } catch (error) {
      feedback.replaceChildren(notice(error.message, 'error'));
      if (started && payload.use_search) feedback.append(h('p', {}, 'Your inputs are safe. You can retry, or add official reference text and prepare without web search.'),
        button('Continue with my notes and references', () => {
          search.input.checked = false; updateScope(); perform({...payload, use_search: false});
        }, 'quiet'));
      if (started) status.textContent = 'Not completed. Your inputs and previous report are unchanged.';
    } finally {
      fields.disabled = false; cancel.hidden = true; jobId = null; running = false; setBusy(false); rememberInputs(); refreshRecovery();
      if (restoreFocus && focus?.isConnected) focus.focus();
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); perform(state()); });
  form.addEventListener('input', rememberInputs);
  fields.append(h('h3', {class: 'form-section-title'}, '1. Set the context'));
  if (kind === 'brief') fields.append(documentType.wrap);
  fields.append(title.wrap);
  if (kind === 'research' && !demo) fields.append(search.wrap, query.wrap);
  if (kind === 'brief') {
    fields.append(recipient.wrap);
    if (campaignSenderPrompt) fields.append(campaignSenderPrompt);
    fields.append(sender.panel);
  }
  if (kind === 'grants') fields.append(h('details', {}, h('summary', {}, 'About your organisation (optional)'),
    h('div', {class: 'form-grid'}, org.wrap, location.wrap, budget.wrap)));
  fields.append(kind === 'research' ? h('details', {}, h('summary', {}, 'Add your notes (optional)'), notes.wrap)
    : campaignNotes ? h('details', {}, h('summary', {}, 'Internal notes and evidence context'), notes.wrap) : notes.wrap);
  const imported = field(kind === 'meeting' ? 'Import a transcript file' : 'Add text files as context', 'file', '',
    'Text and Markdown are supported. Meeting imports also accept JSON, VTT and SRT. Imports remain local unless you enable excerpt ranking.',
    {accept: kind === 'meeting' ? '.txt,.md,.json,.vtt,.srt' : '.txt,.md', multiple: kind !== 'meeting'});
  const sourceList = h('div', {class: 'stack'});
  function refreshSources() {
    sourceList.replaceChildren(...sources.map((source, index) => h('div', {class: 'reference-chip'},
      h('span', {}, source.title + ' / ' + source.content.length.toLocaleString() + ' characters'),
      button('Remove', () => { sources.splice(index, 1); refreshSources(); rememberInputs(); }, 'quiet'))));
  }
  imported.input.addEventListener('change', async () => {
    try {
      const files = [...imported.input.files];
      if (!files.length) return;
      if (files.length > 20) throw new Error('Add no more than 20 text files at once.');
      if (files.some(file => file.size > 800000)) throw new Error('Split large text files into smaller sections first.');
      const contents = await Promise.all(files.map(file => file.text()));
      if (kind === 'meeting') { notes.input.value = contents[0]; speakerMap = {}; corrections = []; }
      else files.forEach((file, index) => sources.push({title: file.name, content: contents[index], kind: 'user_note'}));
      refreshSources(); rememberInputs();
      feedback.replaceChildren(notice('Imported locally. Review the text before continuing.', 'success'));
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
  });
  fields.append(kind === 'research' ? h('details', {}, h('summary', {}, 'Import text files (optional)'), imported.wrap) : imported.wrap); refreshSources();
  if (kind !== 'meeting') {
    fields.append(h('h3', {class: 'form-section-title'}, kind === 'research' ? '2. Focus your research (optional)' : '2. Add questions and references'),
      ...(kind === 'brief' ? [opening.wrap] : []),
      kind === 'research' ? h('details', {}, h('summary', {}, 'Add focus questions'), questions.wrap) : questions.wrap,
      referenceForm(sources, refreshSources, rememberInputs), sourceList,
      h('details', {open: kind === 'grants'}, h('summary', {}, kind === 'research' ? 'Optional source ranking' : 'Search & public API options'),
        kind === 'research' ? null : [search.wrap, query.wrap],
        ranking.wrap, notice('Search sends the query above. Optional model ranking sends up to six source excerpts and the project question to the configured service. '
          + 'Leave ranking off for sensitive material. Ranking cannot add factual prose to this report.')));
    if (demo) { search.input.disabled = true; ranking.input.disabled = true; }
  } else {
    const speakerFields = h('div', {class: 'form-grid'});
    const identify = button('Review speaker labels', async () => {
      try {
        const response = await request('/api/transcript/inspect', {data: {text: notes.input.value}});
        speakerFields.replaceChildren();
        for (const label of response.speakers) {
          if (label === 'Unidentified') { speakerFields.append(notice('Unidentified turns remain unknown. Label individual turns after checking the recording.')); continue; }
          const mapped = field(`Confirmed name for ${label}`, 'text', speakerMap[label] || '', 'Leave blank unless you checked the identity.', {maxLength: 100});
          mapped.input.addEventListener('input', () => {
            if (mapped.input.value.trim()) speakerMap[label] = mapped.input.value; else delete speakerMap[label];
            rememberInputs();
          });
          speakerFields.append(mapped.wrap);
        }
      } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
    });
    notes.input.addEventListener('input', () => { speakerMap = {}; corrections = []; speakerFields.replaceChildren(); });
    fields.append(h('details', {}, h('summary', {}, 'Confirm who is speaking'),
      notice('Names are never inferred from voice. Imported labels still need verification against the recording.'), identify, speakerFields));
    let audioInputSnapshot = notes.input.value;
    if (!demo) fields.append(audioForm(async transcript => {
      if (notes.input.value !== audioInputSnapshot) throw new Error('The transcript was edited while audio review was open. Download the recognised transcript before replacing those edits.');
      const compact = {...transcript, segments: transcript.segments.map(({words, ...segment}) => segment)};
      const serialized = JSON.stringify(compact);
      if (serialized.length > 1000000) throw new Error('This transcript is too large for one report. Export the JSON and split it into sessions.');
      notes.input.value = serialized; audioInputSnapshot = serialized;
      speakerMap = {}; corrections = []; speakerFields.replaceChildren();
      rememberInputs(); feedback.replaceChildren(notice('Transcript inserted. Check names, numbers, negation and unclear words against the recording.', 'success'));
    }, value => { if (value) audioInputSnapshot = notes.input.value; running = value; setBusy(value); }, () => running));
  }
  const prepare = h('div', {class: 'prepare-bar'}, scope,
    h('button', {type: 'submit', class: 'button primary'}, kind === 'research' ? 'Prepare research brief' : 'Prepare my draft'));
  if (kind === 'brief' && !demo && onDraftWithModel) prepare.append(button('Draft with your model', () => {
    if (!form.reportValidity()) return;
    const payload = state(); remember(kind, payload);
    try { onDraftWithModel(payload); }
    catch (problem) { feedback.replaceChildren(notice(problem.message, 'error')); }
  }, 'quiet'), h('p', {class: 'fine'}, 'Opens a guided draft with these inputs for you to review before sending them to the model.'));
  fields.append(h('h3', {class: 'form-section-title'}, 'Review and prepare'), prepare);
  form.append(fields, status, h('div', {class: 'button-row'}, cancel), feedback);
  root.append(h('header', {class: 'page-intro non-print'}, h('span', {class: 'eyebrow'}, 'COMMUNITY WORKBENCH'),
    h('h2', {}, campaignCopy?.title || titles[kind]),
    h('p', {}, campaignCopy?.description || descriptions[kind])),
    h('div', {class: 'non-print'}, demo ? notice('OFFLINE EXAMPLE / All people, programmes and details are fictional. Start a new project from Home for real data.') :
      h('p', {class: 'workspace-hint'}, campaignSenderReview
        ? 'Save this unsent draft to My workspace or record it in the linked campaign log. Sinter will not contact the recipient. '
        : 'Save your finished draft to keep it in My workspace. ', h('a', {href: '#settings'}, 'Set up your details'))), inputPanel, preparedState, recovery, results);
  root.dispose = () => { decisionController?.abort(); root.querySelectorAll('[data-audio-panel]').forEach(panel => panel.dispose?.()); };
  return root;
}

function referenceForm(sources, refresh, remember) {
  const title = field('Reference title', 'text', '', '', {maxLength: 500});
  const url = field('Reference link (optional)', 'url');
  const content = field('Reference text', 'textarea', '', 'Paste relevant guidance or correspondence, including exceptions. A URL alone is not evidence.', {rows: 4, maxLength: 200000});
  const feedback = h('div');
  return h('details', {}, h('summary', {}, 'Add a reference'), title.wrap, url.wrap, content.wrap,
    button('Add this reference', () => {
      if (!title.input.value.trim() || !content.input.value.trim() || !url.input.checkValidity()) {
        feedback.replaceChildren(notice('Add a title and source text, with a valid link if supplied.', 'error')); return;
      }
      sources.push({title: title.input.value, url: url.input.value, content: content.input.value, kind: 'reference_excerpt'});
      title.input.value = ''; url.input.value = ''; content.input.value = '';
      feedback.replaceChildren(); refresh(); remember(); announce('Reference added.');
    }), feedback);
}
