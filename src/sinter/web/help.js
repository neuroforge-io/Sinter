/** First-use guidance stays separate from routing and project state. */
import {h, button, notice, safeLink} from './ui.js';
import {gardenCard} from './garden-practice.js';

export function helpPage({go, openGarden, checkConnection}) {
  const browser = Boolean(globalThis.sinterBrowser);
  const connection = h('div', {'aria-live': 'polite'});
  return h('div', {class: 'stack help-page'},
    h('header', {class: 'page-intro'}, h('h2', {}, 'Start with one piece of work'),
      h('p', {}, 'Make a handover you can check, save and come back to. Start with the fictional garden notes below.')),
    gardenCard(openGarden),
    h('section', {class: 'card first-work-save'}, h('h3', {}, 'Keep the copy you worked on'),
      h('ol', {class: 'first-work-checklist'},
        h('li', {}, h('strong', {}, 'Save the inputs and the document.'), ' Save project keeps the notes and questions. Save to My workspace keeps an edited report. Wait for the Saved confirmation.'),
        h('li', {}, h('strong', {}, 'Reopen the right copy.'), ' Find project inputs in Community casebooks and saved reports in My workspace. Funding campaigns has its own saved campaign list.'),
        h('li', {}, h('strong', {}, 'Keep a separate backup.'), ' Export project backup contains casebook inputs; export an edited report separately. A campaign backup contains the campaign, not a saved report. Restore a casebook backup opens a new unsaved project.')),
      h('p', {class: 'fine'}, browser
        ? 'Export saved workspace above keeps saved browser projects, reports, watches and preferences together. Unsaved editor inputs are not included. Backups and browser storage are not encrypted.'
        : 'Saved work and backups are not encrypted. When finished, choose Quit Sinter; closing this browser tab does not stop the installed app.')),
    h('section', {class: 'card first-work-next'}, h('h3', {}, 'Then bring your own notes'),
      h('p', {}, 'A handover, a funding question or a committee decision is enough to begin. Add the original text, keep unanswered questions visible and decide what needs checking next.'),
      h('div', {class: 'button-row'}, button('Open community casebooks', () => go('casebooks'), 'quiet'),
        button('Open funding campaigns', () => go('campaigns'), 'quiet'))),
    h('details', {class: 'card first-work-details'}, h('summary', {}, 'What stays local, and what can leave'),
      h('p', {}, browser
        ? 'After the app loads, the source tools work locally without a model. Your documents stay in this browser unless you explicitly choose a search or approve model context. Browser clearing, private browsing or device loss can erase saved work; keep an exported backup.'
        : 'The interface runs on your computer. Unsaved inputs live in this browser session; saved projects, reports and watches live in ~/.sinter or the configured data directory. Appearance and connection preferences are saved locally. API keys entered in Settings stay in memory for this session only.'),
      h('p', {}, 'Search sends the exact query and returns snippets and citations, not verified answers. Optional model ranking sends up to six excerpts and the project question. Explore AI sends conversation or template inputs. Atlas drafting sends selected excerpts and your question. Review the selected material before sending private information.'),
      h('p', {}, 'Quotes, hashes and links establish traceability, not truth. Selection can miss material. Check original guidance, deadlines, eligibility, names, voting and decisions. Nothing is submitted or sent as an official communication automatically.'),
      browser ? h('p', {}, 'The browser edition runs the actual Python source tools. Local speech, operating-system file paths, ChatGPT sign-in and RKC executable connections need installed Sinter. The What runs here? section above explains the available tools.')
        : h('p', {}, 'The full community workbench uses a local browser address. If your environment refuses it, keep its protections in place. Linux packages with the native window also provide a Sinter native source workspace menu entry for the smaller offline interface. Source users can stop the launcher with Ctrl+C.')),
    h('details', {class: 'card first-work-details'}, h('summary', {}, 'Restoring backups and unfinished work'),
      h('p', {}, 'Save project keeps inputs; it does not keep edited report text. Unfinished jobs are not saved automatically. Use the editor backup controls for unsaved inputs before closing.'),
      h('p', {}, browser
        ? 'Imports are validated before they replace saved work. Import workspace backup replaces the saved browser workspace only after confirmation; imported search watches start paused. Individual project backup JSON works in the installed app too.'
        : 'Restore a casebook backup opens a new unsaved project without overwriting existing casebooks. Save it as a separate copy when you want to keep it. Keep original sources and earlier reviews as historical evidence.')),
    browser ? null : h('details', {class: 'card first-work-details'}, h('summary', {}, 'Meeting audio: optional and local'),
      h('p', {}, 'Import a transcript without extra installation. Core native installers do not bundle the speech engine. Audio transcription needs the optional speech package in a source installation and an explicitly authorised model download. From the Sinter source folder run:'),
      h('pre', {class: 'help-code'}, 'python3 setup_speech.py\n# Windows: py setup_speech.py'),
      h('p', {}, 'Audio is processed locally. Separate isolated microphone channels, listen back to individual passages and keep word timings in JSON. Mixed-room speaker diarization and voice identity are not inferred. Confirm names manually.'),
      h('p', {}, 'Speech recognition can omit or invent words. Listen again to unclear passages, names, amounts and negation before correcting anything.')),
    h('details', {class: 'card first-work-details'}, h('summary', {}, 'Optional connections and more help'),
      h('p', {}, 'The garden handover needs no API connection. A connection check shows whether the configured API responds; it does not establish useful model answers.'),
      browser ? h('p', {}, 'Optional public search and AI are explained in What runs here? above. Source-only reports remain available when a model cannot fit the selected material.')
        : h('div', {}, button('Check public API connection', async () => {
          connection.textContent = 'Checking...';
          try { const status = await checkConnection(); connection.replaceChildren(notice(status.message, status.ok ? 'success' : 'error')); }
          catch (error) { connection.replaceChildren(notice(error.message + ' Local examples still work.', 'error')); }
        }, 'quiet'), connection),
      h('p', {}, safeLink('https://github.com/neuroforge-io/Sinter', 'Source code and setup guide')),
      h('p', {}, safeLink('https://neuroforge.io', 'About NeuroForge'))));
}
