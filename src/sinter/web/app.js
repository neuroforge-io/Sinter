import {casebooksPage} from './casebooks.js';
import {activityPage} from './activity.js';
import {settingsPage, applyAppearance} from './settings.js';
import {atlasPage} from './atlas.js';
import {communityPage} from './community.js';
import {home} from './home.js';
import {h, button, notice, announce, safeLink} from './ui.js';
import {session, request} from './api.js';
import {workbench} from './workbench.js';
import {library, watches} from './library.js';
import {playground} from './playground.js';

const view = document.getElementById('view');
const drafts = new Map();
let busy = false, current = '#home', routeSequence = 0;
const routes = [['home', 'Overview'], ['casebooks', 'Community casebooks'], ['activity', 'Recent activity'], ['grants', 'Find funding'], ['brief', 'Briefs & letters'], ['meeting', 'Meeting minutes'],
  ['watches', 'Search watches'], ['library', 'My workspace'], ['explore', 'Explore Fracture'], ['atlas', 'Knowledge atlases'], ['tools', 'Community tools'], ['settings', 'Settings'], ['help', 'Getting started']];
const navigation = document.getElementById('navigation');
for (const [id, label] of routes) navigation.append(h('a', {href: '#' + id, class: 'nav-button'}, label));
function setBusy(value) {
  busy = value;
  for (const link of navigation.querySelectorAll('a')) link.setAttribute('aria-disabled', String(value));
}
function remember(kind, value) { if (!value.demo) drafts.set(kind, value); }
function go(route) { if (!busy) location.hash = route; }

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
      h('p', {}, 'The interface runs on your computer. Unsaved inputs live in this browser session; saved reports and watches live in ~/.sinter (or the configured data directory). Appearance and connection preferences are saved locally. API keys entered in Settings stay in memory for this session only.'),
      h('p', {}, 'Search sends the exact query. Optional model ranking sends up to six excerpts and the project question. Explore Fracture sends conversation or template inputs. Atlas drafting sends selected excerpts and your question. Avoid private information in external requests.'),
      h('p', {}, 'Quotes, hashes and links establish traceability, not truth. Selection can miss material. Review official guidance, deadlines, eligibility, names, voting and decisions.'),
      h('p', {}, 'Installed apps run until you choose Quit Sinter. Source users keep the launcher window open; Ctrl+C stops it and watch checks. Unfinished jobs are not saved automatically.')),
    h('div', {class: 'card'}, h('h3', {}, 'Meeting audio: optional, local, honest'),
      h('p', {}, 'Import a transcript without extra installation. Core native installers do not bundle the speech engine. Audio transcription needs the optional speech package in a source installation and an explicitly authorised model download. From the Sinter source folder run:'),
      h('pre', {class: 'help-code'}, 'python3 setup_speech.py\n# Windows: py setup_speech.py'),
      h('p', {}, 'Audio is processed locally. Separate isolated microphone channels, listen back to individual passages and keep word timings in JSON. Mixed-room speaker diarization and voice identity are not inferred. Confirm names manually.'),
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
  view.firstElementChild?.dispose?.();
  view.replaceChildren(notice('Opening your workspace...'));
  try {
    const options = {setBusy, remember, seed: drafts.get(id) || {}, example: new URLSearchParams(query || '').get('example') === '1'};
    let content;
    if (['grants', 'brief', 'meeting'].includes(id)) content = await workbench(id, options);
    else if (id === 'casebooks') content = await casebooksPage(options);
    else if (id === 'activity') content = await activityPage();
    else if (id === 'library') content = await library();
    else if (id === 'watches') content = await watches(options);
    else if (id === 'explore') content = await playground(options);
    else if (id === 'atlas') content = atlasPage(options);
    else if (id === 'tools') content = communityPage(options);
    else if (id === 'settings') content = await settingsPage();
    else if (id === 'help') content = help();
    else content = home(go, drafts);
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
  request('/api/settings').then(state => request('/api/settings', {data: {settings: {...state.settings, theme: value}}})).catch(() => announce('Theme changed for this window; saving the preference failed.'));
});
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault(); document.getElementById('content').focus();
});
window.addEventListener('hashchange', route);
window.addEventListener('beforeunload', event => { if (busy || drafts.size) { event.preventDefault(); event.returnValue = ''; } });
session().then(value => {
  document.getElementById('version').textContent = `v${value.version} / Apache 2.0`;
  if (value.desktop) navigation.append(button('Quit Sinter', async () => {
    if ((busy || drafts.size) && !confirm('Quit Sinter? Download or save your work first. Unsaved work will be lost.')) return;
    try { await request('/api/desktop/quit', {data: {}}); busy = false; drafts.clear(); view.replaceChildren(notice('Sinter has stopped. You can close this window.')); }
    catch (error) { announce(error.message); }
  }, 'quiet'));
}).catch(() => {});
request('/api/settings').then(state => applyAppearance(state.settings)).catch(() => {}).finally(route);
