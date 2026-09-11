import {h, button} from './ui.js';

/** Overview is intentionally separate from routing and task execution. */
export function home(go, drafts) {
  const cards = [
    ['grants', '01', 'FUNDING', 'Find the right opportunity.', 'Discover funding, check the requirements and keep a watch on what changes.', 'Find funding', 'A shortlist with sources and open questions'],
    ['brief', '02', 'RESEARCH & WRITING', 'Make your case clearly.', 'Turn notes and references into an evidence pack, enquiry letter or agenda item.', 'Build a brief', 'A reviewable draft and evidence register'],
    ['meeting', '03', 'MEETINGS', 'Keep a reliable record.', 'Import a transcript, or transcribe in a speech-enabled installation. Confirm speakers and prepare traceable draft minutes.', 'Prepare minutes', 'A transcript, review queue and draft minutes']
  ];
  const preview = h('aside', {class: 'deliverable-preview', 'aria-label': 'Fictional example preview'},
    h('div', {class: 'preview-top'}, h('span', {class: 'eyebrow'}, 'FICTIONAL EXAMPLE'), h('span', {class: 'badge warm'}, 'Ready to review')),
    h('h3', {}, 'Community venue enquiry'),
    h('p', {class: 'muted'}, 'From loose notes to a source-linked draft.'),
    h('div', {class: 'preview-row'}, h('span', {class: 'preview-number'}, '01'), h('div', {}, h('strong', {}, 'Context, collected'), h('small', {}, 'Notes and reference text stay distinct.'))),
    h('div', {class: 'preview-row'}, h('span', {class: 'preview-number'}, '02'), h('div', {}, h('strong', {}, 'Questions, made visible'), h('small', {}, 'What is supported? What still needs an answer?'))),
    h('div', {class: 'preview-row'}, h('span', {class: 'preview-number'}, '03'), h('div', {}, h('strong', {}, 'A draft you control'), h('small', {}, 'Review, export or save. Never sent automatically.'))),
    button('Open this example', () => go('brief?example=1'), 'quiet'));
  const pending = [...drafts.entries()].filter(([, data]) => !data.demo && (data.title || data.notes));
  return h('div', {},
    h('section', {class: 'hero hero-grid'}, h('div', {class: 'hero-copy'},
      h('span', {class: 'eyebrow'}, 'THE COMMUNITY WORKBENCH'),
      h('h2', {}, 'Less busywork.', h('br'), h('span', {}, 'More community.')),
      h('p', {}, 'Funding research. Clearer correspondence. Better meeting records. Practical tools for the people doing the work - with sources visible and decisions still yours.'),
      h('div', {class: 'button-row'}, button('Try an example', () => go('brief?example=1'), 'primary'), button('Getting started', () => go('help'), 'quiet')),
      h('div', {class: 'hero-meta'}, h('span', {}, 'Local-first'), h('span', {}, 'No account for examples'), h('span', {}, 'Apache 2.0'))), preview),
    pending.length ? h('section', {class: 'resume-strip', 'aria-label': 'Continue an unsaved project'},
      h('span', {class: 'muted'}, 'Still in this session'),
      ...pending.map(([kind, data]) => button(`Continue: ${data.title || kind}`, () => go(kind), 'quiet'))) : null,
    h('div', {class: 'section-heading'}, h('div', {}, h('span', {class: 'eyebrow'}, 'START WITH A REAL TASK'),
      h('h2', {}, 'What would you like to get done?')), h('span', {class: 'muted'}, 'No clever prompting needed.')),
    h('div', {class: 'card-grid'}, cards.map(([id, index, category, title, description, label, outcome]) =>
      h('article', {class: 'card workflow-card'}, h('span', {class: 'card-index', 'aria-hidden': 'true'}, index),
        h('span', {class: 'eyebrow'}, category), h('h3', {}, title), h('p', {}, description), h('small', {class: 'outcome'}, outcome),
        h('div', {class: 'button-row'}, button(label, () => go(id), 'primary'), button('See example', () => go(`${id}?example=1`), 'quiet'))))),
    h('div', {class: 'card-grid secondary-tools'},
      h('article', {class: 'card'}, h('span', {class: 'eyebrow'}, 'KNOWLEDGE'), h('h3', {}, 'Put past work to work.'),
        h('p', {}, 'Find cited material in RKC atlases. Optional Fracture assistance helps draft from a bounded source pack.'), button('Explore knowledge atlases', () => go('atlas'), 'quiet')),
      h('article', {class: 'card'}, h('span', {class: 'eyebrow'}, 'EVERYDAY ADMIN'), h('h3', {}, 'Keep everyone on the same page.'),
        h('p', {}, 'Action lists, volunteer plans, calendar exports and document comparisons. No AI or account needed.'), button('Open community tools', () => go('tools'), 'quiet')),
      h('article', {class: 'card'}, h('span', {class: 'eyebrow'}, 'YOUR WORKSPACE'), h('h3', {}, 'Make yourself comfortable.'),
        h('p', {}, 'Larger type, calmer motion and your own API connection. A workspace that fits the way you work.'), button('Personalise Sinter', () => go('settings'), 'quiet'))),
    h('section', {class: 'steps-strip', 'aria-label': 'How Sinter works'},
      h('div', {}, h('strong', {}, 'Bring the context'), h('p', {}, 'Add notes, reference text or a recording. Choose whether anything is sent to the public API.')),
      h('div', {}, h('strong', {}, 'Check the evidence'), h('p', {}, 'Follow exact excerpts back to their source. Unanswered questions remain open.')),
      h('div', {}, h('strong', {}, 'Review, then use'), h('p', {}, 'Copy, export or save locally. Official communications and minutes remain yours to approve.'))));
}
