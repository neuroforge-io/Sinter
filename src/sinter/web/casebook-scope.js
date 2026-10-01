/** Explicit wording-search boundaries, anchored to current question positions. */
import {h, field, selectField, check, button, notice} from './ui.js';
import {sourceFilterView, sourceFilterStates} from './casebook-source-filter.js';

const trim = text => text.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu, '');
export const questionLines = text => text.split(/\r\n|[\n\v\f\r\x1c-\x1e\x85\u2028\u2029]/u).map(trim).filter(Boolean);
const knownIds = documents => new Set(documents.filter(row => /^S[0-9a-f]{24}$/.test(row.id || '')).map(row => row.id));
export const sourceCountLabel = count => `${count} source${count === 1 ? '' : 's'}`;
export const casebookSchema = scopes => scopes.length ? 'sinter-casebook/v2' : 'sinter-casebook/v1';
// A raw empty list records a deliberate clear; an absent field never means clear.
export const explicitScopeClear = book => Boolean(book && Object.hasOwn(book, 'question_scopes')
  && Array.isArray(book.question_scopes) && book.question_scopes.length === 0);
export const sourceChoiceLabel = (number, source, index) => `Question ${number} source: ${source.title} — ${/^S[0-9a-f]{24}$/.test(source.id || '') ? source.id : `unsaved source ${index + 1}`}`;

export function questionScopeIssue(text, scopes, documents) {
  const questions = questionLines(text), known = knownIds(documents);
  if (!Array.isArray(scopes) || scopes.length > questions.length) return 'Review source choices for removed questions before saving.';
  let previous = -1;
  for (const row of scopes) {
    if (!row || Object.keys(row).sort().join('|') !== 'question|question_index|source_ids'
        || !Number.isInteger(row.question_index) || row.question_index <= previous
        || row.question_index >= questions.length || row.question_index < 0) return 'Review source choices for changed or removed question positions before saving.';
    if (row.question !== questions[row.question_index]) return 'Questions changed or moved. Review their source choices before saving.';
    if (!Array.isArray(row.source_ids) || row.source_ids.some(id => !known.has(id))
        || new Set(row.source_ids).size !== row.source_ids.length) return 'A selected source is no longer available. Review source choices before saving.';
    previous = row.question_index;
  }
  return '';
}

/** Exactly mirror the backend's preview; no hidden broader evidence packet. */
export function casebookDraftContext(report) {
  if (!report.question_scopes?.length) return {
    questions: report.question_index.slice(0, 8).map(row => row.question),
    excerpts: report.excerpts.slice(0, 8).map(row => ({id: row.id, text: row.quote})),
  };
  const issue = questionScopeIssue(report.question_index.map(row => row.question).join('\n'),
    report.question_scopes, report.source_register);
  if (issue) throw new Error(issue);
  const originals = new Map(report.excerpts.map(row => [row.id, row]));
  const all = report.source_register.map(row => row.id);
  const scopes = new Map(report.question_scopes.map(row => [row.question_index, row.source_ids]));
  const allowed = new Set();
  const questions = report.question_index.slice(0, 8).map((row, index) => {
    const source_ids = [...(scopes.get(index) || all)];
    for (const id of row.excerpt_ids) {
      if (!originals.has(id) || !source_ids.includes(originals.get(id).source_id)) throw new Error('A selected passage falls outside its question source choice.');
      allowed.add(id);
    }
    return {question_index: index, question: row.question, source_ids, excerpt_ids: [...row.excerpt_ids]};
  });
  const excerpts = report.excerpts.filter(row => allowed.has(row.id)).slice(0, 8)
    .map(row => ({id: row.id, source_id: row.source_id, text: row.quote}));
  const sent = new Set(excerpts.map(row => row.id));
  for (const row of questions) row.excerpt_ids = row.excerpt_ids.filter(id => sent.has(id));
  return {questions, excerpts};
}

export function questionScopeControls({text, scopes, documents, onChange, viewState = [], onViewChange}) {
  const questions = questionLines(text), known = knownIds(documents);
  let choices = structuredClone(scopes);
  let views = sourceFilterStates(questions, viewState);
  // Keep the single grid track bounded when a desktop window becomes narrow.
  const root = h('div', {class: 'stack', style: 'grid-template-columns:minmax(0,1fr)'});
  const set = (index, value) => {
    choices = choices.filter(row => row.question_index !== index);
    if (value) choices.push(value);
    choices.sort((a, b) => a.question_index - b.question_index);
    onChange(structuredClone(choices));
  };
  const rerenderQuestion = index => {
    render();
    const current = root.querySelector(`[data-question-scope-index="${index}"]`);
    current.open = true;
    current.querySelector('select').focus({preventScroll: true});
  };
  function render() {
    root.replaceChildren(h('p', {class: 'fine'},
      'Limit related-wording matches and optional draft context for a question. This does not answer the question or review whole sources. All originals stay in the project.'),
    ...(choices.length ? [notice('Explicit source choices use casebook v2. Older previews cannot show these saved projects and refuse their backups. Keep the unchanged workspace or a v2 backup when returning to this preview. Originals and saved history remain local.')] : []));
    if (!questions.length) root.append(h('p', {}, 'Add an explicit question to choose its sources.'));
    if (documents.some(row => !known.has(row.id))) root.append(notice(
      'Use Save project to give newly added sources stable references before choosing them. This is a local save; nothing is uploaded.'));
    questions.forEach((question, index) => {
      let row = choices.find(item => item.question_index === index);
      const details = h('details', {class: 'source', style: 'content-visibility:visible', 'data-question-scope-index': String(index)});
      const summary = h('summary');
      const count = h('p', {role: 'status', 'aria-label': `Question ${index + 1} source count`});
      const update = () => {
        const caption = row ? `${row.source_ids.length} selected source${row.source_ids.length === 1 ? '' : 's'}` : `All ${documents.length} supplied source${documents.length === 1 ? '' : 's'}`;
        summary.textContent = `Question ${index + 1}: ${question} — ${caption}`;
        count.textContent = row ? `${sourceCountLabel(row.source_ids.length)} chosen; ${row.source_ids.filter(id => known.has(id)).length} currently available. ${row.source_ids.length ? 'Related wording is not an answer.' : 'No source will be searched for this question.'}` : `All ${documents.length} supplied source${documents.length === 1 ? '' : 's'} will be searched. Related wording is not an answer.`;
      };
      update();
      const mode = selectField(`Sources for question ${index + 1}`, [['all', 'All supplied sources'], ['selected', 'Choose sources']], row ? 'selected' : 'all');
      mode.input.addEventListener('change', () => {
        set(index, mode.input.value === 'selected' ? {question_index: index, question, source_ids: []} : null);
        rerenderQuestion(index);
      });
      details.append(summary, count, mode.wrap);
      if (row) {
        const stale = row.question !== question || row.source_ids.some(id => !known.has(id));
        if (stale) details.append(notice('This choice needs review. It was recorded for: ' + row.question + '. Saving and preparing are blocked until you confirm or choose All supplied sources.', 'warning'));
        const sourceChoices = h('div');
        details.append(sourceChoices);
        details.addEventListener('toggle', () => {
          if (!details.open || sourceChoices.firstChild) return;
          const previousView = views.find(view => view.question_index === index);
          const filter = field(`Filter sources for question ${index + 1}`, 'search', previousView?.query || '',
            'Search titles, supplied dates, links and stable source references. Original source text is not searched. Filtering is local and does not change your evidence choices.',
            {placeholder: 'Title, date, link or reference'});
          const selectedOnly = check(`Show only selected sources for question ${index + 1}`, previousView?.selected_only || false);
          const visibleCount = h('p', {class: 'fine', role: 'status',
            'aria-label': `Question ${index + 1} source filter results`});
          const emptyView = h('p', {class: 'fine', hidden: true},
            'No sources match this view. Clear the filter or turn off selected only. Filtering does not change your evidence choices.');
          const wrappers = [];
          const applyFilter = removedIndex => {
            const restoreFocus = removedIndex !== undefined
              && wrappers[removedIndex].contains(document.activeElement);
            const view = sourceFilterView(documents, row.source_ids, {
              query: filter.input.value, selectedOnly: selectedOnly.input.checked});
            const visible = new Set(view.visibleIndices);
            for (const [position, wrapper] of wrappers.entries()) wrapper.hidden = !visible.has(position);
            visibleCount.textContent = `Showing ${view.visibleIndices.length} of ${sourceCountLabel(view.totalSources)}. ${view.selectedTotal} selected in total; ${view.selectedOutsideView} selected outside this view.`;
            emptyView.hidden = view.visibleIndices.length !== 0;
            if (restoreFocus && !visible.has(removedIndex)) {
              const next = view.visibleIndices.find(position => position > removedIndex)
                ?? view.visibleIndices.filter(position => position < removedIndex).at(-1);
              const nextCheckbox = next === undefined ? null : wrappers[next].querySelector('input[type="checkbox"]');
              (nextCheckbox && !nextCheckbox.disabled ? nextCheckbox : selectedOnly.input).focus({preventScroll: true});
            }
          };
          const rememberView = () => {
            views = views.filter(view => view.question_index !== index);
            if (filter.input.value || selectedOnly.input.checked) views.push({question_index: index,
              question, query: filter.input.value, selected_only: selectedOnly.input.checked});
            views.sort((a, b) => a.question_index - b.question_index);
            onViewChange?.(structuredClone(views)); applyFilter();
          };
          filter.input.addEventListener('input', rememberView);
          selectedOnly.input.addEventListener('change', rememberView);
          sourceChoices.append(filter.wrap, selectedOnly.wrap, visibleCount, emptyView);
          for (const [sourceIndex, source] of documents.entries()) {
            const choice = check(source.title, row.source_ids.includes(source.id));
            choice.input.setAttribute('aria-label', sourceChoiceLabel(index + 1, source, sourceIndex));
            choice.input.disabled = !known.has(source.id);
            const wording = choice.wrap.querySelector('span');
            wording.append(h('small', {style: 'display:block'},
              choice.input.disabled ? 'Source reference assigned when saved.' : `Source reference: ${source.id}`,
              ` · Supplied source date (unverified): ${source.date || 'unknown'}`,
              ...(source.url ? [` · Source link: ${source.url}`] : [])));
            if (choice.input.disabled) wording.append(h('small', {style: 'display:block'}, 'Save project before choosing this new source.'));
            choice.input.addEventListener('change', () => {
              const ids = new Set(row.source_ids);
              if (choice.input.checked) ids.add(source.id); else ids.delete(source.id);
              row = {...row, source_ids: [...ids]}; set(index, row); update();
              applyFilter(sourceIndex);
            });
            const inspect = h('details', {class: 'source', style: 'content-visibility:visible'});
            const text = h('div');
            inspect.append(h('summary', {}, 'Inspect this local source'),
              h('p', {class: 'fine'}, 'This is the original supplied text. Reading it does not select a source, change the project or upload anything.'), text);
            inspect.addEventListener('toggle', () => {
              if (inspect.open && !text.firstChild) text.append(h('pre', {}, source.content));
            });
            const wrapper = h('div', {'data-source-choice-id': source.id || ''}, choice.wrap, inspect);
            wrappers.push(wrapper); sourceChoices.append(wrapper);
          }
          applyFilter();
        });
        if (stale) details.append(button(`Confirm source choices for question ${index + 1}`, () => {
          set(index, {...row, question, source_ids: row.source_ids.filter(id => known.has(id))});
          rerenderQuestion(index);
        }, 'quiet'));
      }
      root.append(details);
    });
    const removed = choices.filter(row => row.question_index >= questions.length);
    for (const row of removed) root.append(notice(`A removed question still has a source choice: ${row.question}`, 'warning'),
      button('Clear this removed question choice', () => { set(row.question_index, null); render(); }, 'quiet'));
  }
  render();
  return root;
}
