/** One tool catalogue powers navigation, page titles and the keyboard finder. */
import {h, button, announce} from './ui.js';

export const tools = [
  {id: 'home', label: 'Overview', group: 'WORKSPACE', icon: '⌂', description: 'Start a task or try a local example', keywords: 'start home example'},
  {id: 'campaigns', label: 'Funding campaigns', group: 'WORKSPACE', icon: '◇', description: 'Keep opportunities, application answers, quotes and next actions together', keywords: 'grant campaign funding budget eligibility application'},
  {id: 'casebooks', label: 'Community casebooks', group: 'WORKSPACE', icon: '▤', description: 'Connect notes, policies and questions in a saved project', keywords: 'knowledge project collection documents'},
  {id: 'library', label: 'My workspace', group: 'WORKSPACE', icon: '▱', description: 'Open reports you saved on this computer', keywords: 'saved library documents exports'},
  {id: 'activity', label: 'Recent activity', group: 'WORKSPACE', icon: '◷', description: 'Recover a result or check a running task', keywords: 'jobs cancel recover progress'},
  {id: 'research', label: 'Research a topic', group: 'CREATE', icon: '⌕', description: 'Find source highlights, citations and gaps to investigate', keywords: 'research evidence sources search'},
  {id: 'grants', label: 'Find funding', group: 'CREATE', icon: '◇', description: 'Discover opportunities and check requirements', keywords: 'grants money fund eligibility'},
  {id: 'brief', label: 'Briefs & letters', group: 'CREATE', icon: '↗', description: 'Prepare an enquiry, briefing or agenda item', keywords: 'enquiry email writing draft'},
  {id: 'meeting', label: 'Meeting minutes', group: 'CREATE', icon: '≋', description: 'Review a transcript and prepare traceable minutes', keywords: 'audio speech recording transcript speakers'},
  {id: 'tools', label: 'Community tools', group: 'EXPLORE', icon: '⊞', description: 'Compare wording or build a plan and calendar', keywords: 'compare difference diff event volunteer action register calendar'},
  {id: 'watches', label: 'Search watches', group: 'EXPLORE', icon: '◉', description: 'Keep track of changes in repeat searches', keywords: 'monitor schedule alerts funding'},
  {id: 'explore', label: 'Explore Fracture', group: 'EXPLORE', icon: '✧', description: 'Chat, search or use a guided drafting template', keywords: 'chat ai model templates recipes consultation newsletter enquiry'},
  {id: 'atlas', label: 'Knowledge atlases', group: 'EXPLORE', icon: '⋈', description: 'Inspect cited material from an RKC atlas', keywords: 'rkc knowledge compile context'},
  {id: 'settings', label: 'Settings', group: 'PREFERENCES', icon: '⚙', description: 'Appearance, reading comfort and your API connection', keywords: 'theme light dark large text preferences'},
  {id: 'help', label: 'Getting started', group: 'PREFERENCES', icon: '?', description: 'A practical guide to your first piece of work', keywords: 'help guide support privacy'},
];

export function buildNavigation(target) {
  let group;
  for (const tool of tools) {
    if (tool.group !== group) target.append(h('span', {class: 'nav-section'}, group = tool.group));
    target.append(h('a', {href: '#' + tool.id, class: 'nav-button'},
      h('span', {class: 'nav-icon', 'aria-hidden': 'true'}, tool.icon), h('span', {}, tool.label)));
  }
}

/** Native dialog supplies focus containment and Escape recovery without a dependency. */
export function installToolFinder(go, isBusy) {
  const input = h('input', {type: 'search', placeholder: 'Try “minutes”, “compare” or “research”…',
    'aria-label': 'Find a Sinter tool', autocomplete: 'off'});
  const results = h('div', {class: 'finder-results'});
  const count = h('p', {class: 'fine', role: 'status'});
  const dialog = h('dialog', {class: 'tool-finder', 'aria-labelledby': 'finder-title'},
    h('div', {class: 'finder-heading'}, h('h2', {id: 'finder-title'}, 'What would you like to do?'),
      button('Close', () => dialog.close(), 'quiet')), input, count, results,
    h('p', {class: 'finder-hint fine'}, '↑ ↓ to move · Enter to open · Esc to close'));
  function render() {
    const words = input.value.toLowerCase().trim().split(/\s+/);
    const matches = tools.filter(tool => words.every(word =>
      `${tool.label} ${tool.description} ${tool.keywords}`.toLowerCase().includes(word)));
    results.replaceChildren(...matches.map(tool => button(
      h('span', {}, h('strong', {}, tool.label), h('small', {}, tool.description)),
      () => { dialog.close(); go(tool.id); }, 'finder-result')));
    count.textContent = matches.length ? `${matches.length} ${matches.length === 1 ? 'tool' : 'tools'} available` : 'No match. Try a task such as “funding” or “meeting”.';
  }
  input.addEventListener('input', render);
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); dialog.close(); return; }
    const buttons = [...results.querySelectorAll('button')];
    const at = buttons.indexOf(document.activeElement);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (buttons.length) buttons[at < 0 ? (event.key === 'ArrowDown' ? 0 : buttons.length - 1) :
        (at + (event.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length].focus();
    } else if (event.key === 'Enter' && document.activeElement === input) {
      event.preventDefault(); buttons[0]?.click();
    }
  });
  function open() {
    if (isBusy()) { announce('Finish or cancel the current task before opening another tool.'); return; }
    if (dialog.open) return;
    input.value = ''; render(); dialog.showModal(); input.focus();
  }
  document.body.append(dialog);
  document.getElementById('tool-finder-button').addEventListener('click', open);
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); open();
    }
  });
}
