/** Explicit local identity defaults, shared by correspondence and guided drafting. */
import {h, field} from './ui.js';

export function senderFields(data = {}, settings = {}) {
  const defaults = {
    signatory: settings.full_name || '', sender_role: settings.role || '', organisation: settings.organisation || '',
    contact_details: [settings.email, settings.phone, settings.website].filter(Boolean).join('\n')
  };
  const entries = {
    signatory: field('Your name or role', 'text', data.signatory ?? defaults.signatory, '', {maxLength: 200, autocomplete: 'name'}),
    sender_role: field('Your role', 'text', data.sender_role ?? defaults.sender_role, '', {maxLength: 200, autocomplete: 'organization-title'}),
    organisation: field('Organisation name', 'text', data.organisation ?? defaults.organisation, '', {maxLength: 1024, autocomplete: 'organization'}),
    contact_details: field('Contact details', 'textarea', data.contact_details ?? defaults.contact_details, 'Only include the details you want in this document.', {rows: 3, maxLength: 4096})
  };
  const values = () => Object.fromEntries(Object.entries(entries).map(([key, entry]) => [key, entry.input.value]));
  const summary = h('span');
  function refresh() { const sender = values(); summary.textContent = [sender.signatory, sender.organisation].filter(Boolean).join(' · ') || 'Add your name and contact details'; }
  const panel = h('details', {class: 'sender-panel'}, h('summary', {}, h('span', {class: 'sender-label'}, 'Your sign-off'), summary),
    h('p', {class: 'fine'}, 'Filled from your saved details. Changes here apply to this draft only. ', h('a', {href: '#settings'}, 'Update your profile')),
    h('div', {class: 'form-grid'}, entries.signatory.wrap, entries.sender_role.wrap), entries.organisation.wrap, entries.contact_details.wrap);
  panel.addEventListener('input', refresh); refresh();
  return {panel, entries, values};
}

export function senderContext(values) {
  return Object.entries(values).filter(([, value]) => value.trim()).map(([key, value]) => key.replaceAll('_', ' ') + ': ' + value).join('\n');
}
