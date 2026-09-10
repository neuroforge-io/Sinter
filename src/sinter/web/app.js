import {h, button, notice, announce, safeLink} from './ui.js';
import {session, request} from './api.js';
import {workbench} from './workbench.js';
import {library, watches} from './library.js';
import {playground} from './playground.js';

const view = document.getElementById('view');
const drafts = new Map();
let busy = false, current = '#home', routeSequence = 0;
const routes = [['home', 'Overview'], ['grants', 'Find funding'], ['brief', 'Briefs & letters'], ['meeting', 'Meeting minutes'],
  ['watches', 'Search watches'], ['library', 'My workspace'], ['explore', 'Explore Fracture'], ['help', 'Getting started']];
const navigation = document.getElementById('navigation');
for (const [id, label] of routes) navigation.append(h('a', {href: '#' + id, class: 'nav-button'}, label));
function setBusy(value) {
  busy = value;
  for (const link of navigation.querySelectorAll('a')) link.setAttribute('aria-disabled', String(value));
}
function remember(kind, value) { drafts.set(kind, value); }
function go(route) { if (!busy) location.hash = route; }

function home() {
  const cards = [
    ['grants', '01', 'FUNDING RADAR', 'Good ideas deserve a chance.', 'Find funding, check real requirements and keep track of what changes.', 'Find funding'],
    ['brief', '02', 'EVIDENCE STUDIO', 'Turn a pile of notes into a plan.', 'Bring context and sources together. Prepare a useful brief and an enquiry worth sending.', 'Build a brief'],
    ['meeting', '03', 'MEETING DESK', 'Keep the meaning. Lose the mess.', 'Prepare traceable draft minutes, confirm speaker names and review corrections.', 'Prepare minutes']
  ];
  return h('div', {}, h('section', {class: 'hero'}, h('span', {class: 'eyebrow'}, 'FOR THE PEOPLE WHO MAKE THINGS HAPPEN'),
    h('h2', {}, 'Less busywork.', h('br'), h('span', {}, 'More community.')),
    h('p', {}, 'A little help for the work that matters. Bring your notes, references and next steps together - so volunteers can spend more time making a difference.'),
    h('div', {class: 'button-row'}, button('Try an example', () => go('brief?example=1'), 'primary'), button('How it works', () => go('help'))),
    h('div', {class: 'hero-meta'}, h('span', {}, 'NO ACCOUNT TO GET STARTED'), h('span', {}, 'YOUR SOURCES, VISIBLE'), h('span', {}, 'APACHE 2.0'))),
    h('div', {class: 'section-heading'}, h('h2', {}, 'What would you like to get done?'), h('span', {class: 'muted'}, 'Start small. Make it useful.')),
    h('div', {class: 'card-grid'}, cards.map(([id, index, category, title, description, label]) =>
      h('article', {class: 'card workflow-card'}, h('span', {class: 'card-index', 'aria-hidden': 'true'}, index),
        h('span', {class: 'eyebrow'}, category), h('h3', {}, title), h('p', {}, description),
        h('div', {class: 'button-row'}, button(label, () => { drafts.delete(id); go(id); }, 'primary'), button('See example', () => go(`${id}?example=1`), 'quiet'))))),
    h('section', {class: 'steps-strip'},
      h('div', {}, h('strong', {}, '01 / Bring your context'), h('p', {}, 'Notes, questions and source text. No clever prompting needed.')),
      h('div', {}, h('strong', {}, '02 / Follow the evidence'), h('p', {}, 'Exact excerpts, visible sources and clear unknowns.')),
      h('div', {}, h('strong', {}, '03 / Review, then use'), h('p', {}, 'Download, print or save locally. You stay in control.'))));
}

function help() {
  const connection = h('div', {'aria-live': 'polite'});
  return h('div', {class: 'stack'}, h('header', {class: 'page-intro'}, h('h2', {}, 'You do not need to be technical.'),
    h('p', {}, 'Start with a fictional example, then bring one real piece of work.')),
    h('div', {class: 'card'}, h('h3', {}, 'Three steps to a useful first draft'),
      h('p', {}, '1. Choose funding, a brief or meeting minutes. Name your project and paste your notes.'),
      h('p', {}, '2. Add actual reference text. A link alone is not evidence. Search is optional and sends only the query you enter.'),
      h('p', {}, '3. Prepare the draft, check sources and unknowns, then download or save it. Nothing is sent automatically.'),
      button('Open a local example', () => go('brief?example=1'), 'primary')),
    h('div', {class: 'card'}, h('h3', {}, 'Privacy and trust'),
      h('p', {}, 'The interface runs on your computer. Unsaved inputs live in this browser session; saved reports and watches live in your Sinter folder. Only the theme preference is stored in browser storage.'),
      h('p', {}, 'Search sends the exact query. Optional model ranking sends up to six excerpts and the project question. Explore Fracture sends conversation or template inputs. Avoid private information in external requests.'),
      h('p', {}, 'Quotes, hashes and links establish traceability, not truth. Selection can miss material. Review official guidance, deadlines, eligibility, names, voting and decisions.'),
      h('p', {}, 'Keep the launcher window open. Closing it stops the app and watch checks. Unfinished jobs are not saved automatically.')),
    h('div', {class: 'card'}, h('h3', {}, 'Meeting audio: optional, local, honest'),
      h('p', {}, 'Import a transcript without extra installation. Audio transcription needs the optional speech package and an explicitly authorised model download. From the Sinter source folder run:'),
      h('pre', {class: 'help-code'}, 'python -m pip install ".[speech]"'),
      h('p', {}, 'Audio is processed locally. Automatic speaker separation and voice identity are not included. Import a diarized transcript and confirm names manually.'),
      h('p', {}, 'Speech recognition can omit or invent words. Listen again to unclear passages, names, amounts and negation before correcting anything.')),
    h('div', {class: 'card'}, h('h3', {}, 'Connection and help'),
      button('Check public API connection', async () => {
        connection.textContent = 'Checking...';
        try { const status = await request('/api/health'); connection.replaceChildren(notice(status.message, status.ok ? 'success' : 'error')); }
        catch (error) { connection.replaceChildren(notice(error.message + ' Local examples still work.', 'error')); }
      }), connection,
      h('p', {}, safeLink('https://github.com/neuroforge-io/Sinter', 'Source code and setup guide')),
      h('p', {}, safeLink('https://neuroforge.io', 'About NeuroForge'))));
}

async function route() {
  if (busy) { history.replaceState(null, '', current); announce('Finish or cancel the current task before changing pages.'); return; }
  const hash = location.hash || '#home'; current = hash;
  const [id, query] = hash.slice(1).split('?');
  const name = routes.find(([key]) => key === id)?.[1] || 'Overview';
  document.getElementById('page-title').textContent = name;
  document.title = `${name} - Sinter`;
  for (const link of navigation.querySelectorAll('a')) {
    if (link.hash === '#' + id) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  const sequence = ++routeSequence;
  view.replaceChildren(notice('Opening your workspace...'));
  try {
    const options = {setBusy, remember, seed: drafts.get(id) || {}, example: new URLSearchParams(query || '').get('example') === '1'};
    let content;
    if (['grants', 'brief', 'meeting'].includes(id)) content = await workbench(id, options);
    else if (id === 'library') content = await library();
    else if (id === 'watches') content = await watches(options);
    else if (id === 'explore') content = await playground(options);
    else if (id === 'help') content = help();
    else content = home();
    if (sequence !== routeSequence) return;
    view.replaceChildren(content); document.getElementById('content').focus({preventScroll: true}); window.scrollTo(0, 0);
  } catch (error) { if (sequence === routeSequence) view.replaceChildren(notice(error.message, 'error'), button('Try again', route)); }
}

const theme = document.getElementById('theme-toggle');
function applyTheme(value) {
  document.documentElement.dataset.theme = value;
  theme.textContent = value === 'dark' ? 'Light theme' : 'Dark theme';
  theme.setAttribute('aria-label', `Switch to ${value === 'dark' ? 'light' : 'dark'} theme`);
}
try { applyTheme(localStorage.getItem('sinter-theme') === 'light' ? 'light' : 'dark'); } catch { applyTheme('dark'); }
theme.addEventListener('click', () => {
  const value = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; applyTheme(value);
  try { localStorage.setItem('sinter-theme', value); } catch { /* Preferences are optional. */ }
});
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault(); document.getElementById('content').focus();
});
window.addEventListener('hashchange', route);
window.addEventListener('beforeunload', event => { if (busy || drafts.size) { event.preventDefault(); event.returnValue = ''; } });
session().then(value => { document.getElementById('version').textContent = `v${value.version} / Apache 2.0`; }).catch(() => {});
route();
