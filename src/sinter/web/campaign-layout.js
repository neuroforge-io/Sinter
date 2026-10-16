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
