/** Correspondence presentation; all edits retain canonical campaign rows. */
import {h, field, selectField, button, notice, safeLink} from './ui.js';
import {campaignCommunicationView, campaignCommunicationPreview,
  COMMUNICATION_ORDERS, COMMUNICATION_STATUSES} from './campaign-communication-view.js';

const countCharacters = value => [...value].length;
const directionOptions = [['incoming', 'Incoming'], ['outgoing', 'Outgoing']];
const channelOptions = [['email', 'Email'], ['letter', 'Letter'], ['phone', 'Phone call'],
  ['meeting', 'Meeting'], ['portal', 'Application portal'], ['other', 'Other']];
const statusText = status => status === 'draft' ? 'Draft · not sent'
  : status === 'sent' ? 'Recorded as sent' : 'Recorded as received';
const provenanceText = status => (status === 'draft'
  ? 'Draft · not sent · user-entered.'
  : `${statusText(status)} · user-entered, unverified.`)
  + ' Dates, message details and links remain user-entered and unverified.';

export function renderCampaignCommunications(panel, {document, view, openState,
  editor, input, choice, changed, renderEditor, rememberCampaign, error, remove,
  scopeChoices, campaignSourcePicker}) {
  const addCommunication = button('Add communication', () => {
      const row = {opportunity: '', date: '', direction: 'outgoing', status: 'draft',
        channel: 'email', counterparty: '', subject: '', content: '', evidence_links: []};
      document.communications.push(row);
      view.query = ''; view.route = null; view.status = 'all';
      openState.set(row, true);
      changed(); renderEditor();
      const target = editor.querySelector(`.campaign-communication[data-communication-index="${document.communications.indexOf(row)}"] [data-campaign-field="subject"]`);
      target?.focus(); target?.scrollIntoView({block: 'nearest'});
    }, 'quiet');
  panel.append(h('div', {class: 'campaign-section-heading'},
    h('h3', {}, 'Record correspondence and drafts'), addCommunication),
    h('p', {class: 'muted'}, 'Saved locally. Dates and delivery status are recorded by you and remain unverified. Sinter does not read mail or send messages.'));
  if (!document.communications.length) {
    panel.append(h('div', {class: 'campaign-empty'}, h('h4', {}, 'No communications recorded yet'),
      h('p', {}, 'Add a received message or an outgoing draft when there is something to track. Nothing is sent from this page.')));
    return;
  }
  if (view.route && !document.opportunities.some(row => row.name === view.route)) view.route = null;
  const search = field('Find a communication', 'search', view.query,
    'Search messages, contacts, routes and saved evidence.',
    {placeholder: 'Try a contact, route or phrase from a message', maxLength: 200});
  const routeChoices = [['all', 'All routes and campaign-wide'], ['campaign', 'Campaign-wide'],
    ...document.opportunities.map((row, index) => [`route:${index}`, row.name])];
  const routeValue = view.route === null ? 'all' : view.route === '' ? 'campaign'
    : `route:${document.opportunities.findIndex(row => row.name === view.route)}`;
  const routeFilter = selectField('Communication scope', routeChoices, routeValue);
  const order = selectField('Communication order', COMMUNICATION_ORDERS, view.order);
  const statusFilter = selectField('Communication status filter', COMMUNICATION_STATUSES, view.status);
  const resultCount = h('p', {class: 'campaign-filter-status', 'aria-live': 'polite'});
  const empty = h('p', {class: 'campaign-filter-empty', hidden: true},
    'No communications match this view. Clear the search or choose another scope or status.');
  const clear = button('Clear communication filters', () => {
    view.query = ''; view.route = null; view.status = 'all';
    search.input.value = ''; routeFilter.input.value = 'all'; statusFilter.input.value = 'all';
    updateCommunicationView(); rememberCampaign(); search.input.focus();
  }, 'quiet');
  const communicationList = h('div', {class: 'campaign-communication-list'});
  const cards = new Map(), previews = new Map();
  function updateCommunicationView() {
    const visible = campaignCommunicationView(document.communications, view);
    const shown = new Set(visible.map(({index}) => index));
    for (const [index, card] of cards) {
      card.hidden = !shown.has(index);
      previews.get(index)();
    }
    const arranged = [...visible.map(({index}) => cards.get(index)),
      ...[...cards].filter(([index]) => !shown.has(index)).map(([, card]) => card)];
    const current = [...communicationList.children];
    if (arranged.length !== current.length || arranged.some((card, index) => card !== current[index])) {
      communicationList.replaceChildren(...arranged);
    }
    empty.hidden = visible.length !== 0;
    clear.hidden = !view.query && view.route === null && view.status === 'all';
    const orderLabel = COMMUNICATION_ORDERS.find(([value]) => value === view.order)?.[1]
      || 'Record order';
    const statusLabel = COMMUNICATION_STATUSES.find(([value]) => value === view.status)?.[1]
      || 'All statuses';
    resultCount.textContent = `${visible.length} of ${document.communications.length} communications · ${statusLabel} · ${orderLabel}.`
      + (view.order === 'record' ? '' : ' Entries without a valid recorded date appear last.');
  }
  search.input.addEventListener('input', () => {
    view.query = search.input.value.trim(); updateCommunicationView(); rememberCampaign();
  });
  routeFilter.input.addEventListener('change', () => {
    const value = routeFilter.input.value;
    view.route = value === 'all' ? null : value === 'campaign' ? ''
      : document.opportunities[Number(value.slice(6))]?.name ?? null;
    updateCommunicationView(); rememberCampaign();
  });
  order.input.addEventListener('change', () => {
    view.order = order.input.value; updateCommunicationView(); rememberCampaign();
  });
  statusFilter.input.addEventListener('change', () => {
    view.status = statusFilter.input.value; updateCommunicationView(); rememberCampaign();
  });
  // Keep a canonical editor attached while typing. Refresh matching at commit.
  communicationList.addEventListener('change', event => {
    // Picker blur must not detach the explicit source selection under the pointer.
    if (!event.target.closest('.campaign-source-picker')) updateCommunicationView();
  });
  communicationList.addEventListener('click', event => {
    if (event.target.closest('.campaign-source-picker button')) updateCommunicationView();
  });
  panel.append(search.wrap, h('div', {class: 'form-grid'}, routeFilter.wrap,
    statusFilter.wrap, order.wrap), clear, resultCount, empty, communicationList);

  for (const [index, row] of document.communications.entries()) {
    const evidenceLinks = Array.isArray(row.evidence_links) ? row.evidence_links : [];
    const state = h('span', {class: 'campaign-communication-state', 'data-state': row.status},
      statusText(row.status));
    const summaryTitle = h('strong', {}, row.subject || 'Untitled communication');
    const summaryDetails = h('span', {class: 'fine'});
    const preview = h('span', {class: 'campaign-communication-preview'});
    const cue = h('span', {class: 'fine campaign-communication-cue'});
    const summary = h('summary', {}, summaryTitle, state, summaryDetails, preview, cue);
    const open = openState.get(row) ?? (!row.subject && !row.content);
    openState.set(row, open);
    const details = h('details', {open}, summary);
    let built = false, provenance = null;
    function updatePreview() {
      const saved = campaignCommunicationPreview(row, {query: view.query});
      preview.textContent = saved.text ? `${saved.label}: ${saved.text}` : 'No message text recorded.';
      preview.dataset.previewKind = saved.kind;
      cue.textContent = `${saved.evidenceCount} saved evidence link${saved.evidenceCount === 1 ? '' : 's'} · `
        + (details.open ? 'Close details' : 'Open to view or edit');
    }
    function updateSummary() {
      const channelLabel = channelOptions.find(([value]) => value === row.channel)?.[1] || 'Other';
      summaryDetails.textContent = [row.date || 'Date not recorded',
        row.direction === 'incoming' ? 'Incoming' : 'Outgoing', channelLabel,
        row.counterparty, row.opportunity || 'Campaign-wide'].filter(Boolean).join(' · ');
      state.textContent = statusText(row.status); state.dataset.state = row.status;
      if (provenance) provenance.textContent = provenanceText(row.status);
      updatePreview();
    }
    function buildEditor() {
      if (built) return;
      const direction = choice('Direction', directionOptions, row, 'direction', () => {
        row.status = row.direction === 'incoming' ? 'received'
          : row.status === 'received' ? 'draft' : row.status;
        updateSummary(); changed(); renderEditor();
      });
      const statusChoices = row.direction === 'incoming'
        ? [['received', 'Received · recorded by you']]
        : [['draft', 'Draft · not sent'], ['sent', 'Sent · recorded by you']];
      const statusField = choice('Communication status', statusChoices, row, 'status', updateSummary);
      const channel = choice('Channel', channelOptions, row, 'channel', updateSummary);
      const date = input('Communication date (user-entered)', 'date', row, 'date',
        'Enter the date shown by your records. For a draft, leave blank unless you have a separate date to record. Sinter does not infer or verify it.', {}, updateSummary);
      const counterparty = input('Person or organisation', 'text', row, 'counterparty',
        'Who the message was with. This is a user-entered record.', {maxLength: 300}, updateSummary);
      const subject = input('Subject or short title', 'text', row, 'subject', '', {maxLength: 1000}, () => {
        summaryTitle.textContent = row.subject || 'Untitled communication'; updateSummary();
      });
      const content = input('Message text or summary', 'textarea', row, 'content',
        'Paste the relevant message or a useful summary. Stored with this campaign on this computer; include only details the campaign needs.',
        {rows: 6, maxLength: 20000}, updatePreview);
      const contentCount = h('small', {class: 'campaign-character-count'},
        `${countCharacters(row.content || '')} characters · destination limits vary; check before copying.`);
      content.input.addEventListener('input', () => {
        contentCount.textContent = `${countCharacters(content.input.value)} characters · destination limits vary; check before copying.`;
      });
      content.wrap.append(contentCount);
      const evidence = h('div', {class: 'campaign-communication-evidence'},
        h('h4', {}, 'Evidence links · user-entered, unverified'),
        h('p', {class: 'fine'}, 'For example, a link to a message, attachment or portal record. Sinter does not open or check it.'),
        button('Add evidence link', () => {
          if (evidenceLinks.length >= 10) { error('A communication can have up to 10 evidence links.'); return; }
          row.evidence_links = evidenceLinks;
          evidenceLinks.push({source_id: '', title: '', url: '', notes: '', checked_at: ''});
          changed(); renderEditor();
        }, 'quiet'));
      for (const link of evidenceLinks) {
        const navigation = h('div', {class: 'campaign-communication-evidence-navigation'});
        function updateNavigation() {
          navigation.replaceChildren(...(link.url
            ? [safeLink(link.url, 'Open evidence link')] : []));
        }
        const linkTitle = input('Evidence title', 'text', link, 'title',
          'For example, “Email from programme officer” or “Application portal receipt”.', {maxLength: 500});
        const linkUrl = input('Evidence link', 'url', link, 'url',
          'HTTP or HTTPS link only. Links are not opened or verified by Sinter.',
          {maxLength: 4000}, updateNavigation);
        const linkNotes = input('Evidence note', 'textarea', link, 'notes', '', {rows: 2, maxLength: 2000});
        const savedSource = document.sources.find(source => source.id === link.source_id);
        const linkChecked = input(savedSource
          ? 'Source check date at link time · user-entered' : 'Source check date · user-entered',
        'date', link, 'checked_at', savedSource
          ? 'Preserved from when this evidence was linked. Sinter does not verify the date.'
          : 'Record the source check date. Sinter does not verify it.', {});
        const snapshotWarning = notice('', 'warning');
        function updateSnapshotWarning(source) {
          const differs = Boolean(source && (link.title !== source.title
            || link.url !== source.url || link.checked_at !== source.checked_at));
          snapshotWarning.hidden = !differs;
          snapshotWarning.textContent = differs
            ? 'This saved evidence snapshot differs from the current source record. Its original title, link and check date are preserved. Recheck the source before use; clear and select it again only to replace the snapshot.' : '';
        }
        updateSnapshotWarning(savedSource);
        const sourceChoice = campaignSourcePicker('Link to a saved campaign source', link.source_id, source => {
          const isNewLink = Boolean(source && source.id !== link.source_id);
          link.source_id = source?.id || '';
          if (source && isNewLink) {
            link.title = source.title; link.url = source.url; link.checked_at = source.checked_at;
            linkTitle.input.value = source.title; linkUrl.input.value = source.url;
            linkChecked.input.value = source.checked_at;
          }
          linkTitle.input.disabled = Boolean(source); linkUrl.input.disabled = Boolean(source);
          linkChecked.input.disabled = Boolean(source);
          linkChecked.wrap.querySelector('label').textContent = source
            ? 'Source check date at link time · user-entered' : 'Source check date · user-entered';
          updateSnapshotWarning(source); updateNavigation(); updatePreview();
        });
        linkTitle.input.disabled = Boolean(savedSource); linkUrl.input.disabled = Boolean(savedSource);
        linkChecked.input.disabled = Boolean(savedSource);
        updateNavigation();
        evidence.append(h('article', {class: 'campaign-row', 'aria-label': 'Communication evidence link'},
          sourceChoice.wrap, snapshotWarning, linkTitle.wrap, linkUrl.wrap, linkChecked.wrap, linkNotes.wrap,
          navigation,
          remove(evidenceLinks, link, 'Remove evidence link')));
      }
      const opportunity = choice('Related opportunity', scopeChoices(), row, 'opportunity', updateSummary);
      provenance = h('p', {class: 'fine campaign-communication-provenance'},
        provenanceText(row.status));
      details.append(h('div', {class: 'campaign-communication-editor'},
        h('div', {class: 'form-grid'}, direction.wrap, statusField.wrap, channel.wrap, date.wrap),
        h('div', {class: 'form-grid'}, counterparty.wrap, subject.wrap, opportunity.wrap),
        content.wrap, evidence,
        provenance,
        remove(document.communications, row, 'Remove communication')));
      built = true;
    }
    details.addEventListener('toggle', () => {
      if (!details.isConnected) return;
      openState.set(row, details.open);
      if (details.open) buildEditor();
      updatePreview();
    });
    if (open) buildEditor();
    cards.set(index, h('article', {class: 'campaign-row campaign-communication',
      'aria-label': 'Campaign communication', 'data-communication-index': String(index)}, details));
    previews.set(index, updatePreview);
    updateSummary();
  }
  updateCommunicationView();
}
