import {h, button, field, selectField, check, notice, announce} from './ui.js';
import {request, waitForJob} from './api.js';
import {renderReport} from './reports.js';
import {audioForm} from './audio.js';

const titles = {grants: 'Find funding for good ideas.', brief: 'Bring the whole picture together.', meeting: 'A clearer record. Not a different story.'};
const descriptions = {
  grants: 'Discover opportunities, then check actual requirements. No invented deadlines or automatic eligibility decisions.',
  brief: 'Gather notes, questions and references into a source-linked briefing and a ready-to-edit enquiry letter.',
  meeting: 'Import a transcript or transcribe audio locally. Confirm speakers and corrections before preparing draft minutes.'
};

export async function workbench(kind, {example = false, seed = {}, setBusy, remember}) {
  const data = example ? await request(`/api/example?workflow=${kind}`) : seed;
  const root = h('div');
  const demo = Boolean(data.demo);
  const sources = [...(data.sources || [])];
  let speakerMap = {...(data.speaker_map || {})}, corrections = [...(data.corrections || [])];
  let running = false, lastPayload, jobId;
  const title = field('Project name', 'text', data.title || '', 'A name you will recognise later.', {required: true, maxLength: 200});
  const notes = field(kind === 'meeting' ? 'Transcript' : 'Your notes and context', 'textarea', data.notes || '',
    kind === 'meeting' ? 'Paste Speaker: words, or import TXT, SRT, VTT or JSON segments. Unlabelled turns remain unidentified.'
      : 'Keep original wording where it matters. Notes are labelled as notes, not verified facts.', {rows: 7, maxLength: kind === 'meeting' ? 1000000 : 200000});
  const questions = field('Questions you need answered', 'textarea', data.questions || '', 'One question per line works well.', {rows: 4, maxLength: 12000});
  const query = field('Exact web search query', 'text', data.query || '', 'Only this query is sent to NeuroForge search. Avoid names and private details.', {maxLength: 1024});
  const search = check('Search the web for related material', !demo && (data.use_search ?? kind === 'grants'));
  const ranking = check('Let Fracture rank a small set of source excerpts', !demo && Boolean(data.use_model));
  const org = field('Organisation type', 'text', data.profile?.organisation_type || '', 'For example: incorporated P&C association.');
  const location = field('Location', 'text', data.profile?.location || '');
  const budget = field('Project budget', 'number', data.profile?.budget || '', 'Numbers only; record currency in your notes.', {min: '0', step: 'any'});
  const state = () => ({workflow: kind, title: title.input.value, notes: notes.input.value,
    questions: kind === 'meeting' ? '' : questions.input.value, query: kind === 'meeting' ? '' : query.input.value,
    use_search: kind !== 'meeting' && !demo && search.input.checked,
    use_model: kind !== 'meeting' && !demo && ranking.input.checked,
    demo, sources: [...sources], speaker_map: {...speakerMap}, corrections,
    document_type: documentType.input.value, recipient: recipient.input.value, signatory: signatory.input.value, organisation: organisation.input.value,
    profile: {organisation_type: org.input.value, location: location.input.value, budget: budget.input.value}});
  const documentType = selectField('What are you preparing?', [['enquiry', 'Enquiry letter'], ['briefing', 'Briefing note'], ['agenda', 'Agenda item for discussion']], data.document_type || 'enquiry');
  const recipient = field('Recipient or audience', 'text', data.recipient || '', '', {maxLength: 200});
  const signatory = field('Your name or role', 'text', data.signatory || '', '', {maxLength: 200});
  const organisation = field('Organisation name', 'text', data.organisation || '', '', {maxLength: 200});
  const form = h('form', {class: 'form-panel non-print'});
  const fields = h('fieldset', {}, h('legend', {class: 'sr-only'}, 'Project inputs'));
  const feedback = h('div', {'aria-live': 'polite'}), results = h('div');
  const status = h('div', {class: 'progress', role: 'status'});
  const cancel = button('Cancel', async () => {
    if (jobId) await request('/api/jobs/cancel', {data: {id: jobId}})
      .catch(error => feedback.replaceChildren(notice(error.message, 'error')));
  });
  cancel.hidden = true;
  async function perform(payload) {
    if (running) return;
    if (!title.input.value.trim()) { title.input.reportValidity(); return; }
    running = true; setBusy(true); fields.disabled = true; feedback.replaceChildren();
    status.textContent = 'Starting your evidence pack...'; cancel.hidden = false;
    lastPayload = payload;
    try {
      const job = await request('/api/workbench', {data: payload}); jobId = job.id;
      const report = await waitForJob(jobId, value => { status.textContent = value.message || 'Preparing...'; });
      results.replaceChildren(renderReport(report, {onCorrect: async changes => {
        corrections = changes; await perform({...lastPayload, corrections});
      }}));
      status.textContent = 'Draft ready. Review sources before using it.';
      announce('Your draft is ready for review.'); results.scrollIntoView({block: 'start'});
    } catch (error) {
      feedback.replaceChildren(notice(error.message, 'error'));
      status.textContent = 'Not completed. Your inputs and previous report are unchanged.';
    } finally {
      fields.disabled = false; cancel.hidden = true; jobId = null; running = false; setBusy(false); remember(kind, state());
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); perform(state()); });
  form.addEventListener('input', () => remember(kind, state()));
  fields.append(h('h3', {class: 'form-section-title'}, '1. Set the context'));
  if (kind === 'brief') fields.append(documentType.wrap);
  fields.append(title.wrap);
  if (kind === 'brief') fields.append(h('details', {}, h('summary', {}, 'Recipient and sign-off (optional)'), recipient.wrap, signatory.wrap, organisation.wrap));
  if (kind === 'grants') fields.append(h('details', {}, h('summary', {}, 'About your organisation (optional)'),
    h('div', {class: 'form-grid'}, org.wrap, location.wrap, budget.wrap)));
  fields.append(notes.wrap);
  const imported = field(kind === 'meeting' ? 'Import a transcript file' : 'Add text files as context', 'file', '',
    'Text and Markdown are supported. Meeting imports also accept JSON, VTT and SRT. Imports remain local unless you enable excerpt ranking.',
    {accept: kind === 'meeting' ? '.txt,.md,.json,.vtt,.srt' : '.txt,.md', multiple: kind !== 'meeting'});
  const sourceList = h('div', {class: 'stack'});
  function refreshSources() {
    sourceList.replaceChildren(...sources.map((source, index) => h('div', {class: 'reference-chip'},
      h('span', {}, source.title + ' / ' + source.content.length.toLocaleString() + ' characters'),
      button('Remove', () => { sources.splice(index, 1); refreshSources(); remember(kind, state()); }, 'quiet'))));
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
      refreshSources(); remember(kind, state());
      feedback.replaceChildren(notice('Imported locally. Review the text before continuing.', 'success'));
    } catch (error) { feedback.replaceChildren(notice(error.message, 'error')); }
  });
  fields.append(imported.wrap); refreshSources();
  if (kind !== 'meeting') {
    fields.append(h('h3', {class: 'form-section-title'}, '2. Add questions and references'), questions.wrap, referenceForm(sources, refreshSources, () => remember(kind, state())), sourceList,
      h('details', {open: kind === 'grants'}, h('summary', {}, 'Search & public API options'), search.wrap, query.wrap,
        ranking.wrap, notice('Search sends the query above. Optional Fracture ranking sends up to six source excerpts and the project question to the configured service. '
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
            remember(kind, state());
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
      remember(kind, state()); feedback.replaceChildren(notice('Transcript inserted. Check names, numbers, negation and unclear words against the recording.', 'success'));
    }, value => { if (value) audioInputSnapshot = notes.input.value; running = value; setBusy(value); }, () => running));
  }
  fields.append(h('h3', {class: 'form-section-title'}, 'Review and prepare'), h('div', {class: 'button-row'}, h('button', {type: 'submit', class: 'button primary'}, 'Prepare my draft')));
  form.append(fields, status, h('div', {class: 'button-row'}, cancel), feedback);
  root.append(h('header', {class: 'page-intro non-print'}, h('span', {class: 'eyebrow'}, 'COMMUNITY WORKBENCH'),
    h('h2', {}, titles[kind]), h('p', {}, descriptions[kind])),
    h('div', {class: 'non-print'}, demo ? notice('OFFLINE EXAMPLE / All people, programmes and details are fictional. Start a new project from Home for real data.') :
      notice('Work stays in this session until you save it. Reloading loses unsaved drafts. Review before sending; Sinter never sends letters or approves minutes.')), form, results);
  root.dispose = () => root.querySelectorAll('[data-audio-panel]').forEach(panel => panel.dispose?.());
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
