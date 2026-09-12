import {h, button} from './ui.js';

/** Overview is intentionally separate from routing and task execution. */
export function home(go, drafts, settings = {}) {
  const cards = [
    ['research', '01', 'RESEARCH', 'Follow the evidence.', 'Explore a topic through source excerpts, clear citations and questions worth asking next.', 'Research a topic', 'A research brief with highlights and gaps'],
    ['grants', '01', 'FUNDING', 'Find the right opportunity.', 'Discover funding, check the requirements and keep a watch on what changes.', 'Find funding', 'A shortlist with sources and open questions'],
    ['brief', '02', 'RESEARCH & WRITING', 'Make your case clearly.', 'Turn notes and references into an evidence pack, enquiry letter or agenda item.', 'Build a brief', 'A reviewable draft and evidence register'],
    ['meeting', '03', 'MEETINGS', 'Keep a reliable record.', 'Import a transcript, or transcribe in a speech-enabled installation. Confirm speakers and prepare traceable draft minutes.', 'Prepare minutes', 'A transcript, review queue and draft minutes']
  ];
  const pending = [...drafts.entries()].filter(([, data]) => !data.demo && (data.title || data.notes || data.book?.title));
  return h('div', {},
    h('header', {class: 'workspace-welcome'}, h('div', {}, h('span', {class: 'eyebrow'}, settings.organisation || 'YOUR COMMUNITY WORKSPACE'),
      h('h2', {}, settings.full_name ? 'What are we working on, ' + settings.full_name.split(' ')[0] + '?' : 'Your next piece of work starts here.'),
      h('p', {}, 'Research a question, write a letter or make sense of meeting notes. Leave with a document you can actually use.')),
      button('Try an example', () => go('brief?example=1'), 'quiet')),
    !settings.full_name ? h('section', {class: 'profile-nudge'}, h('div', {}, h('strong', {}, 'Your details, ready for every draft'),
      h('p', {}, 'Add your name, group and contact details once. Sinter will complete the sign-off for you.')),
      button('Set up my details', () => go('settings'), 'primary')) : null,
    pending.length ? h('section', {class: 'resume-strip', 'aria-label': 'Continue an unsaved project'},
      h('span', {class: 'muted'}, 'Still in this session'),
      ...pending.map(([kind, data]) => button(`Continue: ${data.title || data.book?.title || kind}`, () => go(kind), 'quiet'))) : null,
    h('div', {class: 'section-heading'}, h('div', {}, h('span', {class: 'eyebrow'}, 'START WITH A REAL TASK'),
      h('h2', {}, 'What would you like to get done?')), h('span', {class: 'muted'}, 'No clever prompting needed.')),
    h('div', {class: 'card-grid task-grid'}, cards.map(([id, index, category, title, description, label, outcome], position) =>
      h('article', {class: 'card workflow-card'}, h('span', {class: 'card-index', 'aria-hidden': 'true'}, String(position + 1).padStart(2, '0')),
        h('span', {class: 'eyebrow'}, category), h('h3', {}, title), h('p', {}, description), h('small', {class: 'outcome'}, outcome),
        h('div', {class: 'button-row'}, button(label, () => go(id), 'primary'), button('See example', () => go(`${id}?example=1`), 'quiet'))))),
    h('section', {class: 'card secondary-tools'}, h('span', {class: 'eyebrow'}, 'FUNDING CAMPAIGNS'), h('h3', {}, 'Keep the whole application together.'),
      h('p', {}, 'Compare opportunities, prepare answers, record quotes and turn missing checks into next actions. Saved on this computer, with the original guidance beside the work.'),
      button('Open funding campaigns', () => go('campaigns'), 'primary')),
    h('section', {class: 'card secondary-tools'}, h('span', {class: 'eyebrow'}, 'NEW / COMMUNITY CASEBOOKS'), h('h3', {}, 'Scattered information. Connected work.'),
      h('p', {}, 'Bring notes, replies, policies and handovers together. Save a project, ask your questions, and prepare a source-only briefing with the gaps still visible.'),
      button('Open community casebooks', () => go('casebooks'), 'primary')),
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
