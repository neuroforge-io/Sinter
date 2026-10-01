import {casebooksPage} from './casebooks.js';
import {campaignsPage} from './campaigns.js';
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
import {tools, buildNavigation, installToolFinder} from './navigation.js';
import {rememberDraft, shouldWarnBeforeExit} from './draft-state.js';
import {hasUnsavedReportDrafts, clearReportDrafts} from './report-drafts.js';
import {gardenSeed, gardenCard, GARDEN_PRACTICE} from './garden-practice.js';

const view = document.getElementById('view');
const drafts = new Map();
const dirtyDrafts = new Set();
let busy = false, current = '#home', routeSequence = 0;
const routes = tools.map(({id, label}) => [id, label]);
const navigation = document.getElementById('navigation');
buildNavigation(navigation);
installToolFinder(go, () => busy);
function setBusy(value) {
  busy = value;
  for (const link of navigation.querySelectorAll('a')) link.setAttribute('aria-disabled', String(value));
}
function remember(kind, value, options) { rememberDraft(drafts, dirtyDrafts, kind, value, options); }
function go(route) { if (!busy) location.hash = route; }

async function openGarden(kind) {
  if (busy) return;
  const previous = drafts.get(kind);
  if (previous?.practice === GARDEN_PRACTICE) { go(kind); return; }
  if (dirtyDrafts.has(kind) && !confirm('Open the fictional garden example in this editor? Save or export your current project first if you need to keep its unsaved inputs. Saved projects and document drafts stay available.')) return;
  setBusy(true);
  try {
    const bundle = await request('/api/practice/garden');
    remember(kind, gardenSeed(kind, bundle), {dirty: true});
    setBusy(false); go(kind);
  } catch (error) {
    const message = error.message + ' Your current project is unchanged. Choose the example again to retry.';
    view.prepend(notice(message, 'error')); announce(message);
  }
  finally { setBusy(false); }
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
    gardenCard(openGarden),
    h('div', {class: 'card'}, h('h3', {}, 'Privacy and trust'),
      h('p', {}, 'The interface runs on your computer. Unsaved inputs live in this browser session; saved reports and watches live in ~/.sinter (or the configured data directory). Appearance and connection preferences are saved locally. API keys entered in Settings stay in memory for this session only.'),
      h('p', {}, 'Search sends the exact query. Optional model ranking sends up to six excerpts and the project question. Explore AI sends conversation or template inputs. Atlas drafting sends selected excerpts and your question. Avoid private information in external requests.'),
      h('p', {}, 'Quotes, hashes and links establish traceability, not truth. Selection can miss material. Review official guidance, deadlines, eligibility, names, voting and decisions.'),
      h('p', {}, 'Save project inputs and edited reports separately. Wait for the Saved confirmation, then choose Quit Sinter. Closing this browser tab does not stop an installed app. Unfinished jobs are not saved automatically. Source users can also stop the launcher with Ctrl+C.'),
      h('p', {}, 'The full community workbench uses a local browser address. If your environment refuses that address, keep its protections in place. Linux packages with the native window also provide a Sinter native source workspace menu entry for the smaller offline interface.')),
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
    const options = {setBusy, remember, seed: drafts.get(id) || {}, onOpenGarden: openGarden, example: new URLSearchParams(query || '').get('example') === '1',
      onDraftWithModel: payload => {
        remember('explore', {mode: 'templates', template: 'enquiry-letter', signatory: payload.signatory,
          sender_role: payload.sender_role, organisation: payload.organisation, contact_details: payload.contact_details,
          variables: {recipient: payload.recipient, questions: payload.questions,
            context: [payload.title, payload.notes, ...(payload.sources || []).map(source => `${source.title}\n${source.content}\n${source.url || ''}`)].filter(Boolean).join('\n\n')}});
        go('explore');
      }};
    let content;
    if (['research', 'grants', 'brief', 'meeting'].includes(id)) content = await workbench(id, options);
    else if (id === 'casebooks') content = await casebooksPage(options);
    else if (id === 'campaigns') content = await campaignsPage(options);
    else if (id === 'activity') content = await activityPage();
    else if (id === 'library') content = await library({onEditProject: payload => { remember(payload.workflow, payload, {dirty: true}); go(payload.workflow); }});
    else if (id === 'watches') content = await watches(options);
    else if (id === 'explore') content = await playground(options);
    else if (id === 'atlas') content = atlasPage(options);
    else if (id === 'tools') content = communityPage(options);
    else if (id === 'settings') content = await settingsPage();
    else if (id === 'help') content = help();
    else content = home(go, drafts, (await request('/api/settings')).settings, openGarden);
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
window.addEventListener('beforeunload', event => { if (shouldWarnBeforeExit(dirtyDrafts, busy) || hasUnsavedReportDrafts()) { event.preventDefault(); event.returnValue = ''; } });
session().then(value => {
  document.getElementById('version').textContent = `v${value.version} / Apache 2.0`;
  if (value.desktop) navigation.append(button('Quit Sinter', async () => {
    if ((shouldWarnBeforeExit(dirtyDrafts, busy) || hasUnsavedReportDrafts()) && !confirm('Quit Sinter? Download or save your work first. Unsaved work will be lost.')) return;
    try { await request('/api/desktop/quit', {data: {}}); busy = false; drafts.clear(); dirtyDrafts.clear(); clearReportDrafts(); view.replaceChildren(notice('Sinter has stopped. You can close this window.')); }
    catch (error) { announce(error.message); }
  }, 'quiet'));
}).catch(() => {});
request('/api/settings').then(state => applyAppearance(state.settings)).catch(() => {}).finally(route);
