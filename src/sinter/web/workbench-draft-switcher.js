import {h, button} from './ui.js';

let nextSwitcherId = 0;
const SAVE_LABELS = {
  prepared: 'Not saved', saved: 'Saved locally', saving: 'Saving…',
  'not-sent': 'Save not sent', rejected: 'Save rejected', unconfirmed: 'Save not confirmed',
};

function saveLabel(entry) {
  return entry.save?.kind === 'pending'
    ? entry.pendingText ? 'Text waiting to apply' : 'Changes not saved'
    : SAVE_LABELS[entry.save?.kind] ?? 'Save state unavailable';
}
function text(node, value) { if (node.textContent !== value) node.textContent = value; }
function attribute(node, name, value) {
  if (value === null) { if (node.hasAttribute(name)) node.removeAttribute(name); }
  else if (node.getAttribute(name) !== value) node.setAttribute(name, value);
}

/** Presentation only; Workbench owns requests, adoption, evidence and saves. */
export function createWorkbenchDraftSwitcher({onOpen}) {
  const prefix = `workbench-drafts-${++nextSwitcherId}`;
  const rows = new Map(), preparedRows = new Map(), knownNumbers = new Set();
  let disposed = false, busy = false, currentNumber = null, lastRequested = null;
  const currentLabel = h('strong', {class: 'draft-switcher-current'});
  const durability = h('p', {class: 'draft-switcher-durability'},
    'Unsaved work is kept only in this open page.');
  const summary = h('summary', {}, 'Drafts · 0');
  const list = h('ul', {class: 'draft-switcher-list'});
  const details = h('details', {class: 'draft-switcher-disclosure'}, summary,
    h('p', {class: 'fine'}, 'Each draft keeps its own original inputs and sources. This list contains drafts prepared here.'), list);
  const preparedList = h('ul', {class: 'draft-switcher-list'});
  const prepared = h('section', {class: 'draft-switcher-prepared'},
    h('h3', {}, 'Ready to open'), preparedList);
  const announcement = h('p', {class: 'sr-only', role: 'status', 'aria-atomic': 'true'});
  const element = h('section', {class: 'draft-switcher non-print', 'aria-label': 'Workbench drafts'},
    h('p', {class: 'draft-switcher-heading'}, currentLabel), durability, prepared, details, announcement);
  element.hidden = true; prepared.hidden = true;

  function makeRow(number, outside) {
    const suffix = `${outside ? 'prepared' : 'all'}-${number}`;
    const state = h('span', {class: 'draft-switcher-state', id: `${prefix}-${suffix}-state`});
    const title = h('span', {class: 'draft-switcher-title', id: `${prefix}-${suffix}-title`});
    const control = button('', () => {
      if (disposed || busy || number === currentNumber) return;
      lastRequested = {number, control}; onOpen(number);
    }, 'quiet draft-switcher-row');
    control.setAttribute('aria-label', outside ? `Open prepared draft ${number}` : `Open draft ${number}`);
    control.append(h('span', {class: 'draft-switcher-number'}, `Draft ${number}`), state, title);
    return {item: h('li', {}, control), control, state, title};
  }
  function reconcile(container, cache, entries, showTitles, outside) {
    const present = new Set(entries.map(entry => entry.number));
    for (const [number, row] of cache) if (!present.has(number)) { row.item.remove(); cache.delete(number); }
    let cursor = container.firstElementChild;
    for (const entry of entries) {
      let row = cache.get(entry.number);
      if (!row) { row = makeRow(entry.number, outside); cache.set(entry.number, row); }
      const isCurrent = entry.number === currentNumber;
      const title = showTitles ? (entry.title ?? '').trim() : '';
      text(row.state, `${isCurrent ? 'Current · ' : ''}${saveLabel(entry)}${entry.shown ? '' : ' · New'}`);
      text(row.title, title); row.title.hidden = !title;
      row.control.disabled = busy || isCurrent;
      attribute(row.control, 'aria-current', isCurrent ? 'true' : null);
      attribute(row.control, 'aria-describedby', `${row.state.id}${title ? ` ${row.title.id}` : ''}`);
      if (row.item !== cursor) container.insertBefore(row.item, cursor);
      cursor = row.item.nextElementSibling;
    }
  }
  function update({entries, current, busy: nextBusy = false}) {
    if (disposed) return;
    busy = nextBusy; currentNumber = current;
    const active = entries.find(entry => entry.number === current);
    const waiting = entries.filter(entry => !entry.shown);
    const newlyReady = waiting.filter(entry => !knownNumbers.has(entry.number));
    const titles = new Set(entries.map(entry => (entry.title ?? '').trim()).filter(Boolean));
    element.hidden = !active || entries.length === 0;
    text(currentLabel, active ? `Draft ${active.number} · ${saveLabel(active)}` : '');
    durability.hidden = !entries.some(entry => entry.save?.kind !== 'saved');
    text(summary, `Drafts · ${entries.length}`); details.hidden = entries.length < 2;
    reconcile(list, rows, entries, titles.size > 1, false);
    reconcile(preparedList, preparedRows, waiting, titles.size > 1, true);
    prepared.hidden = waiting.length === 0;
    if (newlyReady.length) text(announcement, newlyReady.length === 1
      ? `Draft ${newlyReady[0].number} is ready to open.` : `${newlyReady.length} drafts are ready to open.`);
    else if (!waiting.length) text(announcement, '');
    for (const entry of entries) knownNumbers.add(entry.number);
  }
  function focusVersion(number) {
    if (disposed || busy || element.hidden) return false;
    const candidates = [lastRequested?.number === number ? lastRequested.control : null,
      preparedRows.get(number)?.control, rows.get(number)?.control];
    const control = candidates.find(candidate => candidate?.isConnected && element.contains(candidate)
      && !candidate.disabled && (!details.contains(candidate) || (!details.hidden && details.open)));
    if (control) { control.focus({preventScroll: true}); return true; }
    if (rows.has(number) && !details.hidden && summary.isConnected) {
      summary.focus({preventScroll: true}); return true;
    }
    return false;
  }
  return {element, update, focusVersion,
    opened() { if (!disposed) { details.open = false; lastRequested = null; } },
    dispose() {
      disposed = true; element.remove(); element.replaceChildren();
      rows.clear(); preparedRows.clear(); knownNumbers.clear(); lastRequested = null;
    }};
}
