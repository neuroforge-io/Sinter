/** Local retained-evidence navigation; never changes a report or sends a request. */
import {h, button} from './ui.js';
import {retainedCasebookSource, retainedQuestionContext} from './casebook-retained-context.js';

const unavailable = () => new Error('This exact retained destination is unavailable or changed. No substitute was opened.');
const same = (a, b) => a.length === b.length && a.every((value, at) => Object.is(value, b[at]));
function only(rows, key, value) {
  if (!Array.isArray(rows)) throw unavailable();
  const matches = rows.filter(row => row?.[key] === value);
  if (matches.length !== 1) throw unavailable();
  return matches[0];
}
function sourcePin(report, sourceId) {
  const source = only(report.sources, 'id', sourceId);
  const record = only(report.source_register, 'id', sourceId);
  if (typeof source.content !== 'string') throw unavailable();
  return [report.sources, report.source_register, source, record,
    source.id, source.content, source.sha256, source.title, source.url, source.kind, source.retrieved_at,
    record.id, record.sha256, record.title, record.date,
    JSON.stringify(report.sources.map(row => row?.id)),
    JSON.stringify(report.source_register.map(row => row?.id))];
}
function passagePin(report, entry) {
  const excerpt = only(report.excerpts, 'id', entry.excerptId);
  const reference = only(report.document_references, 'label', entry.label);
  const question = report.question_index?.[entry.questionIndex];
  const index = report.document_references.indexOf(reference);
  if (!question || reference.label !== 'Passage ' + (index + 1)
      || report.excerpts[index] !== excerpt
      || reference.excerpt_id !== entry.excerptId || reference.source_id !== entry.sourceId
      || reference.start !== entry.start || reference.end !== entry.end
      || excerpt.source_id !== entry.sourceId || excerpt.start !== entry.start
      || excerpt.end !== entry.end || excerpt.quote !== entry.quote) throw unavailable();
  return [...sourcePin(report, entry.sourceId), report.excerpts, report.document_references,
    report.question_index, excerpt, reference, question,
    JSON.stringify({workflow: report.workflow, model: report.model_draft,
      incomplete: report.incomplete, count: report.question_index.length,
      question: question.question, ids: question.excerpt_ids,
      hasScope: Object.hasOwn(question, 'source_scope'), scope: question.source_scope,
      hasScopes: Object.hasOwn(report, 'question_scopes'), scopes: report.question_scopes,
      excerptIds: report.excerpts.map(row => row?.id),
      questions: report.question_index.map(row => [row?.question, row?.excerpt_ids,
        Object.hasOwn(row || {}, 'source_scope'), row?.source_scope])})];
}

export function reportPassageNavigation({
  report, root, sources, isActive, showEvidence, showDocument, focusReader,
}) {
  let epoch = 0, sequence = 0, disposed = false, destination = null;
  const entries = [], handles = new WeakMap(), bindings = new WeakMap(), messages = new Map();
  const description = h('p', {class: 'fine'});
  const back = button('Return to document', returnToInvoker, 'quiet passage-return');
  const bar = h('div', {class: 'passage-return-controls non-print'}, description, back);
  const active = () => !disposed && isActive();
  const connected = node => Boolean(node?.isConnected && root.contains(node));
  const owns = ticket => Boolean(ticket && active() && ticket.epoch === epoch && ticket.sequence === sequence);
  const invokerCurrent = ticket => owns(ticket) && connected(ticket.invoker)
    && ticket.invoker.getClientRects().length > 0
    && bindings.get(ticket.invoker) === ticket.binding
    && (!ticket.binding || ticket.invoker.textContent === ticket.binding.caption)
    && ticket.invoker.textContent === ticket.caption && document.activeElement === ticket.focus;
  const live = entry => connected(entry.details) && entry.quoteNode.parentNode === entry.details
    && entry.quoteNode.textContent === entry.quote;

  function clearChecking(ticket = null) {
    for (const [node, message] of messages) {
      if (message.kind === 'checking' && (!ticket || message.ticket === ticket)) {
        message.element.remove(); messages.delete(node);
      }
    }
  }
  function say(ticket, text, kind) {
    if (!invokerCurrent(ticket)) return;
    let message = messages.get(ticket.invoker);
    if (!message?.element.isConnected) {
      message = {element: h('span', {class: 'citation-navigation-feedback non-print', role: 'status'})};
      ticket.invoker.after(message.element); messages.set(ticket.invoker, message);
    }
    Object.assign(message, {ticket, kind}); message.element.textContent = text;
  }
  function begin(invoker) {
    clearChecking();
    // Pending intent never removes the last successful landing or its Return.
    return {epoch, sequence: ++sequence, invoker, binding: bindings.get(invoker), caption: invoker.textContent, focus: document.activeElement};
  }
  function invalidate() {
    epoch++; sequence++; destination = null; bar.remove();
    for (const message of messages.values()) message.element.remove();
    messages.clear();
  }
  function register({questionIndex, passage, details, quoteNode}) {
    if (!Number.isSafeInteger(questionIndex) || questionIndex < 0 || !passage?.available
        || !/^Passage [1-9][0-9]*$/.test(passage.label)
        || typeof passage.quote !== 'string' || quoteNode.textContent !== passage.quote) return null;
    const entry = {questionIndex, details, quoteNode, label: passage.label,
      excerptId: passage.excerptId, sourceId: passage.sourceId,
      start: passage.start, end: passage.end, quote: passage.quote};
    try { entry.pin = passagePin(report, entry); } catch { return null; }
    const handle = Object.freeze({}); handles.set(handle, entry); entries.push(entry); return handle;
  }
  function find(passage) {
    return entries.find(entry => root.contains(entry.details)
      && entry.quoteNode.parentNode === entry.details && entry.quoteNode.textContent === entry.quote
      && entry.label === passage?.label
      && entry.excerptId === passage.excerpt_id && entry.sourceId === passage.source_id
      && entry.start === passage.start && entry.end === passage.end);
  }
  function bind(invoker, passage) {
    bindings.set(invoker, Object.freeze({...passage, caption: invoker.textContent}));
  }
  async function verify(entry, sourceId, ticket) {
    const before = entry ? passagePin(report, entry) : sourcePin(report, sourceId);
    if (entry && (!live(entry) || !same(entry.pin, before))) throw unavailable();
    const retained = entry
      ? await retainedQuestionContext(report, entry.questionIndex, entry.excerptId)
      : await retainedCasebookSource(report, sourceId);
    if (!invokerCurrent(ticket)) return null;
    const after = entry ? passagePin(report, entry) : sourcePin(report, sourceId);
    if (!same(before, after) || (entry && (!live(entry)
        || retained.sourceId !== entry.sourceId || retained.start !== entry.start
        || retained.end !== entry.end || retained.quote !== entry.quote))) throw unavailable();
    return retained;
  }
  function commit(ticket, details, before, text, returnTo) {
    if (!invokerCurrent(ticket) || !connected(details) || before.parentNode !== details) return false;
    showEvidence(ticket);
    if (!owns(ticket) || !connected(details) || before.parentNode !== details) return false;
    details.open = true; description.textContent = text;
    back.textContent = returnTo.view === 'document' ? 'Return to document' : 'Return to evidence';
    details.insertBefore(bar, before); destination = returnTo;
    back.focus({preventScroll: true}); bar.scrollIntoView({block: 'center', behavior: 'instant'});
    return true;
  }
  function passageDescription(entry) {
    const positions = report.question_index.flatMap((row, index) =>
      Array.isArray(row?.excerpt_ids) && row.excerpt_ids.includes(entry.excerptId) ? [index + 1] : []);
    const shown = 'Showing ' + entry.label + ' under Question ' + (entry.questionIndex + 1) + '.';
    return positions.length > 1
      ? entry.label + ' is recorded under Questions ' + positions.join(', ') + '. ' + shown
      : shown;
  }
  async function open({invoker}) {
    const ticket = begin(invoker);
    if (!invokerCurrent(ticket)) return false;
    const entry = find(ticket.binding);
    say(ticket, 'Checking the retained passage locally…', 'checking');
    try {
      if (!entry) throw unavailable();
      if (!await verify(entry, entry.sourceId, ticket)) return false;
      return commit(ticket, entry.details, entry.quoteNode,
        passageDescription(entry),
        {view: 'document', node: invoker, binding: ticket.binding, caption: ticket.caption});
    } catch (error) { say(ticket, error.message, 'error'); return false; }
    finally { clearChecking(ticket); }
  }
  async function followOriginal({target = null, sourceId, invoker, view = 'evidence'}) {
    const previous = destination, ticket = begin(invoker);
    if (!invokerCurrent(ticket)) return false;
    const entry = target ? handles.get(target) : null;
    say(ticket, 'Checking the retained original locally…', 'checking');
    try {
      if (target && !entry) throw unavailable();
      const id = entry?.sourceId ?? sourceId;
      if (!await verify(entry, id, ticket)) return false;
      const originals = [...sources.querySelectorAll('.source-jump')]
        .filter(node => node.dataset.sourceId === id);
      if (originals.length !== 1) throw unavailable();
      const original = originals[0], text = original.querySelector('pre');
      if (!text || text.textContent !== only(report.sources, 'id', id).content) throw unavailable();
      return commit(ticket, original, text, entry
        ? 'Retained original for ' + entry.label + '; Question ' + (entry.questionIndex + 1) + ' destination.'
        : 'Retained original source.',
      previous || {view, node: invoker, binding: ticket.binding, caption: ticket.caption});
    } catch (error) { say(ticket, error.message, 'error'); return false; }
    finally { clearChecking(ticket); }
  }
  function returnToInvoker() {
    if (!active() || !destination) return;
    const saved = destination, ticket = {epoch, sequence: ++sequence};
    clearChecking(); destination = null; bar.remove();
    if (saved.view === 'document') showDocument(ticket); else showEvidence(ticket);
    if (!owns(ticket)) return;
    const node = saved.node;
    if (connected(node) && node.textContent === saved.caption && (!saved.binding || bindings.get(node) === saved.binding)
        && (!saved.binding || node.textContent === saved.binding.caption)
        && node.getClientRects().length > 0) {
      node.focus({preventScroll: true}); node.scrollIntoView({block: 'center', behavior: 'instant'});
    } else {
      if (saved.view !== 'document') showDocument(ticket);
      if (owns(ticket)) focusReader('The earlier reading position is no longer available. Returned to the document heading.');
    }
  }
  function viewGuard(invoker) {
    const captured = epoch;
    return () => active() && epoch === captured && connected(invoker);
  }
  function dispose() { disposed = true; invalidate(); entries.length = 0; }
  return {register, bind, open, followOriginal, invalidate, dispose, owns,
    has: passage => Boolean(find(passage)), viewGuard};
}
