/** Presentation order only; decisions and canonical campaign records stay elsewhere. */
import {h, button} from './ui.js';

export const isCampaignWorkSection = tab => ['actions', 'communications'].includes(tab);

export function arrangeCampaignEditor({root, editor, capacity, decisionCard, transfers, tab}) {
  const working = isCampaignWorkSection(tab);
  root.dataset.campaignView = working ? 'work' : 'overview';
  const next = working ? decisionCard : transfers;
  if (editor.nextSibling !== next) root.insertBefore(editor, next);
  // Capacity warnings must precede work. Ordinary estimates can follow it.
  const capacityNext = working && capacity.dataset.capacityState === 'within'
    ? transfers : editor;
  if (capacity.nextSibling !== capacityNext) root.insertBefore(capacity, capacityNext);
}

export function renderCampaignWorkContext(context, decision, onStatus, scope) {
  context.replaceChildren(h('div', {class: 'campaign-work-context-main'},
    h('div', {class: 'campaign-work-context-heading'},
      h('p', {}, 'Selected route: ', h('strong', {}, decision.focusOpportunity || 'No route selected')),
      h('span', {class: 'campaign-context-state', 'data-state': decision.state}, decision.label)),
    h('p', {class: 'campaign-context-detail'}, decision.detail),
    h('p', {class: 'campaign-context-scope'}, scope)),
  button('Campaign status', onStatus, 'quiet'));
}

export function campaignActionGuidance(open) {
  return h('details', {class: 'campaign-action-guidance', open},
    h('summary', {}, 'How action scope, owners and dates work'),
    h('p', {}, 'Turn missing quotes, approvals and unanswered conditions into actions. '
      + 'New actions use the selected active route by default; change the scope for campaign-wide work.'),
    h('p', {}, 'Submitted-route tasks only return to current work when marked as after-submission '
      + 'follow-up. Each affected action shows its own hold reason.'),
    h('p', {}, 'A name or date is a planning note until the person agrees and timing is confirmed. '
      + 'Suggested roles and unknown owners are not accepted assignments.'));
}
