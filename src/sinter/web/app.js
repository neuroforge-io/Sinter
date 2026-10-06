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
import {confirmAction} from './confirm-action.js';

const view = document.getElementById('view');
const drafts = new Map();
const dirtyDrafts = new Set();
let busy = false, quitPending = false, appStopped = false, current = '#home', routeSequence = 0;
const routes = tools.map(({id, label}) => [id, label]);
const navigation = document.getElementById('navigation');
buildNavigation(navigation);
installToolFinder(go, () => busy || quitPending || appStopped);
function refreshNavigation() {
  for (const link of navigation.querySelectorAll('a')) link.setAttribute('aria-disabled', String(busy || quitPending || appStopped));
}
function setBusy(value) { busy = value; refreshNavigation(); }
function remember(kind, value, options) { rememberDraft(drafts, dirtyDrafts, kind, value, options); }
function go(route) { if (!busy && !quitPending && !appStopped) location.hash = route; }

async function openGarden(kind) {
  if (busy || quitPending || appStopped) return;
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
  if (globalThis.sinterBrowser) return h('div', {class:'stack'}, h('h2', {}, 'Start with one piece of work'), h('p', {}, 'Try the fictional garden example, or create a casebook or funding campaign with your own notes. Use Save project, then export your saved workspace above. Individual project backup JSON works in the installed app too.'), h('p', {}, 'Your documents stay in this browser unless you explicitly choose a search or approve model context. Optional public search provides snippets and citations, not verified answers. Read the originals. Nothing is submitted or sent as an official communication.'), h('p', {}, 'Imports are validated before they replace saved work. Whole-workspace imports start search watches paused. Unsaved editor inputs are not included in workspace backups; use the editor backup controls before closing.'), h('p', {}, 'The browser edition runs the actual Python source tools. Local speech, operating-system file paths, ChatGPT sign-in and RKC executable connections need installed Sinter. Use the What runs here? section above for details.'), gardenCard(openGarden));
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
      h('p', {}, 'Use Save project for inputs and Save to My workspace for edited reports. Wait for the Saved confirmation, then choose Quit Sinter. Closing this browser tab does not stop an installed app. Unfinished jobs are not saved automatically. Source users can also stop the launcher with Ctrl+C.'),
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
  if (appStopped) { history.replaceState(null, '', current); return; }
  if (busy || quitPending || appStopped) { history.replaceState(null, '', current); announce('Finish or cancel the current task before changing pages.'); return; }
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
    if (sequence !== routeSequence || appStopped) { content?.dispose?.(); return; }
    view.replaceChildren(content); document.getElementById('content').focus({preventScroll: true}); window.scrollTo(0, 0);
  } catch (error) { if (sequence === routeSequence && !appStopped) view.replaceChildren(notice(error.message, 'error'), button('Try again', route)); }
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
window.addEventListener('beforeunload', event => { if (!appStopped && (shouldWarnBeforeExit(dirtyDrafts, busy || quitPending) || hasUnsavedReportDrafts())) { event.preventDefault(); event.returnValue = ''; } });
session().then(value => {
  document.getElementById('version').textContent = `v${value.version} / Apache 2.0`;
  const ownerMessage = value.native_window_owner ? h('span', {}, value.session_notice) : null;
  const ownerStatus = ownerMessage ? h('p', {'aria-live': 'polite'}) : null;
  const ownerNotice = ownerMessage ? notice(ownerMessage, 'native-session') : null;
  let ownerPoll = null;
  let ownerActive = true;
  const updateOwnerState = state => {
    const messages = {
      requested: 'Quit requested. Check Sinter; inputs stay here.',
      confirming: 'Check Sinter for confirmation; inputs stay here.',
      waiting: 'Finishing local requests. Keep Sinter open.',
      cancelled: 'Quit cancelled. Both views stay open.',
      refused: 'Close refused: local work is still running. Both views stay open. Nothing was retried.',
      failed: 'Cleanup failed. Native work stays open; retry closing in Sinter.'
    };
    ownerStatus.textContent = messages[state?.state] || '';
    ownerStatus.hidden = !ownerStatus.textContent;
  };
  if (ownerNotice) {
    const about = h('details', {}, h('summary', {}, 'About this local session'), h('p', {}, value.session_details));
    ownerNotice.append(about, ownerStatus);
    document.getElementById('content').insertBefore(ownerNotice, view);
    updateOwnerState(value.native_quit);
    const poll = async () => {
      try { updateOwnerState((await request('/api/session')).native_quit); }
      catch (_) { /* A draining/stopped listener cannot answer; keep inputs and last state. */ }
      if (ownerActive) ownerPoll = window.setTimeout(poll, 1000);
    };
    ownerPoll = window.setTimeout(poll, 1000);
    window.addEventListener('pagehide', () => { ownerActive = false; window.clearTimeout(ownerPoll); });
    window.addEventListener('pageshow', () => { if (!ownerActive) { ownerActive = true; ownerPoll = window.setTimeout(poll, 1000); } });
  }
  if (value.desktop) {
    const quit = button('Quit Sinter', async () => {
      if (quitPending || appStopped) return;
      quitPending = true; quit.disabled = true; refreshNavigation();
      try {
        if ((shouldWarnBeforeExit(dirtyDrafts, busy) || hasUnsavedReportDrafts()) && !await confirmAction({
          title: 'Quit Sinter?',
          description: ownerNotice
            ? 'Save or export your browser work first. The Sinter window will ask for confirmation; your browser inputs stay here while it decides.'
            : 'Save or export your work first. Quitting stops this local app. Unsaved browser work is not saved automatically.',
          confirmLabel: ownerNotice ? 'Request quit' : 'Quit Sinter',
          cancelLabel: 'Keep working'
        })) return;
        await request('/api/desktop/quit', {data: {}});
        if (ownerNotice) {
          updateOwnerState({state: 'requested'});
          announce('Quit requested. Check Sinter; inputs stay here.'); return;
        }
        appStopped = true; ++routeSequence; busy = false;
        theme.disabled = true; document.getElementById('tool-finder-button').disabled = true; drafts.clear(); dirtyDrafts.clear(); clearReportDrafts(); view.replaceChildren(notice('Sinter has stopped. You can close this window.'));
      }
      catch (error) {
        const message = error.message + ' Quit was not confirmed. Your browser inputs are kept here. Check whether Sinter is still running before trying again.';
        view.prepend(notice(message, 'error')); announce(message);
      }
      finally {
        quitPending = false; quit.disabled = appStopped; refreshNavigation();
        if (!appStopped && quit.isConnected) quit.focus({preventScroll: true});
      }
    }, 'quiet');
    if (ownerNotice) ownerNotice.append(quit); else document.querySelector('.top-actions').append(quit);
  }
}).catch(() => {});
request('/api/settings').then(state => applyAppearance(state.settings)).catch(() => {}).finally(route);
