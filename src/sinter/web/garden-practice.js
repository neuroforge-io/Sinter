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
      h('h3', {}, 'Try a garden project from start to finish.'),
      h('p', {}, 'Read four practice sources, prepare a volunteer handover and work through the funding checks. Keep unknowns visible. Save, reopen and export your own copy.')),
    h('div', {class: 'garden-practice-choices'},
      h('div', {}, button('Open garden handover', () => open('casebooks'), 'primary'), h('small', {}, 'Original notes → a source-only document')),
      h('div', {}, button('Open garden campaign', () => open('campaigns')), h('small', {}, 'Funding checks → editable next actions'))),
    h('p', {class: 'fine'}, globalThis.sinterBrowser ? 'After the app loads, this practice runs locally without a model. Every person, programme and commitment is fictional. Nothing is sent.' : 'No account or internet needed. Every person, programme and commitment is fictional. Nothing is sent. Open a practice copy, or resume your current practice edits.'));
}

export function gardenGuide(kind, open) {
  return h('section', {class: 'garden-practice-guide non-print', 'aria-label': 'Garden practice steps'},
    h('span', {class: 'eyebrow'}, 'FICTIONAL GARDEN PRACTICE · LOCAL ONLY'),
    h('p', {}, kind === 'casebooks'
      ? '1. Inspect the four sources. 2. Prepare the volunteer handover and check Evidence. Preparation saves the project inputs locally; save an edited document separately. 3. Reopen or export your project. The insurance answer remains unknown.'
      : '1. Inspect the funding checks. 2. Edit a next action without claiming an accepted owner or confirmed date. 3. Save, reopen and export. Earlier-round records remain historical.'),
    button(kind === 'casebooks' ? 'Open garden campaign' : 'Open garden handover',
      () => open(kind === 'casebooks' ? 'campaigns' : 'casebooks'), 'quiet'));
}
