/** The complete local practice project is separate from a user's saved work. */
import {h, button} from './ui.js';

export const GARDEN_PRACTICE = 'offline-garden';

export function gardenSeed(kind, bundle) {
  if (bundle?.schema !== 'sinter-practice-bundle/v1' || bundle?.id !== GARDEN_PRACTICE
      || bundle?.fictional !== true) throw new Error('The local practice bundle could not be opened. Your work is unchanged.');
  if (kind === 'casebooks') return {practice: GARDEN_PRACTICE, dirty: true,
    book: {...structuredClone(bundle.casebook), signatory: '', sender_role: '', contact_details: ''}};
  if (kind === 'campaigns') return {practice: GARDEN_PRACTICE, dirty: true,
    document: structuredClone(bundle.campaign)};
  throw new Error('Choose the garden handover or funding campaign.');
}

export function gardenCard(open) {
  return h('section', {class: 'garden-practice-card', 'aria-label': 'Fictional garden practice project'},
    h('div', {class: 'garden-practice-intro'}, h('span', {class: 'eyebrow'}, 'FICTIONAL PROJECT · WORKS OFFLINE'),
      h('h3', {}, 'Turn garden notes into a handover.'),
      h('p', {}, 'Four fictional sources become a source-only document you can review. The missing quote and unknown insurance answer stay visible.'),
      h('ol', {class: 'garden-practice-steps', 'aria-label': 'First handover steps'},
        h('li', {}, h('strong', {}, 'Inspect the notes.'), ' Read the four original sources.'),
        h('li', {}, h('strong', {}, 'Prepare and review.'), ' Choose Prepare source-only report, then check Evidence and edit the draft.'),
        h('li', {}, h('strong', {}, 'Save your copy.'), ' Save project keeps inputs; Save to My workspace keeps the edited report. Wait for Saved, then reopen or export.'))),
    h('div', {class: 'garden-practice-choices'},
      h('div', {}, button('Open garden handover', () => open('casebooks'), 'primary'), h('small', {}, 'Start here · no model or account')),
      h('div', {}, button('Open garden campaign', () => open('campaigns'), 'quiet'), h('small', {}, 'Then try funding checks and next actions'))),
    h('p', {class: 'fine'}, globalThis.sinterBrowser ? 'After the app loads, this practice runs locally without a model. Every person, programme and commitment is fictional. Nothing is sent.' : 'No account or internet needed. Every person, programme and commitment is fictional. Nothing is sent. Open a practice copy, or resume your current practice edits.'));
}

export function gardenGuide(kind, open) {
  return h('section', {class: 'garden-practice-guide non-print', 'aria-label': 'Garden practice steps'},
    h('span', {class: 'eyebrow'}, 'FICTIONAL GARDEN PRACTICE · LOCAL ONLY'),
    h('p', {}, kind === 'casebooks'
      ? '1. Inspect the four sources. 2. Prepare the handover, check Evidence and edit the draft. Preparation saves inputs locally; Save to My workspace keeps the edited report. 3. Wait for Saved. Reopen inputs in Community casebooks and reports in My workspace. Export project inputs and the edited report separately. Restoring a project backup opens a new unsaved copy. The insurance answer remains unknown.'
      : '1. Inspect the funding checks. 2. Edit a next action without claiming an accepted owner or confirmed date. 3. Save, reopen and export. Earlier-round records remain historical.'),
    button(kind === 'casebooks' ? 'Open garden campaign' : 'Open garden handover',
      () => open(kind === 'casebooks' ? 'campaigns' : 'casebooks'), 'quiet'));
}
