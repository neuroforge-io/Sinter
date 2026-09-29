import {hasCurrentApplicationWindowEvidence} from './campaign-state.js';

/** Build a funder-specific clarification draft without campaign-wide context. */
export function clarificationQuestion(requirement, context = {}) {
  const topic = String(requirement || '').replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!topic) return '';
  if (/^(what|when|where|who|which|how|whether|does|do|is|are|can|could|will|would|should|has|have)\b/i.test(topic)) {
    return topic.endsWith('?') ? topic : topic + '?';
  }
  const evidence = String(context.evidence || '');
  const source = String(context.source_quote || '');
  const record = `${topic} ${evidence} ${source}`;
  if (/operating age|minimum operating|trading period/i.test(record)
      && /(?:6|six) months/i.test(record)
      && /(?:1|one) year|12 months/i.test(record)
      && /financial threshold|turnover|operating expenditure/i.test(record)) {
    return 'Our saved source notes differ on the required operating or trading period and may use different financial thresholds or periods. Please confirm the current operating-age rule, how its start date is counted, the financial test and period, how regional status is determined, and what evidence is required.';
  }
  if (/operating age|minimum operating|trading period/i.test(record)
      && /(?:6|six) months/i.test(record)
      && /(?:1|one) year|12 months/i.test(record)) {
    return 'Our saved source notes differ on the required operating or trading period. Which current rule applies, how is the start date counted, and what evidence should we provide?';
  }
  if (/financial threshold|turnover|operating expenditure/i.test(record)) {
    return 'Our saved source notes may describe different financial thresholds or periods. Please confirm the current turnover or expenditure test, the financial period, how regional status is determined, and what evidence you require.';
  }
  if (/cash match|cash contribution|matching contribution/i.test(topic)) {
    return 'Please confirm whether a cash contribution is required, the matching ratio, which costs qualify, when funds must be available, and what evidence is needed.';
  }
  if (/eligible research project|university partner|ip terms|confidentiality/i.test(topic)) {
    return 'Please confirm who may participate, which project types and durations are eligible, what information is needed for initial screening, and when background IP, project IP and confidentiality terms should be agreed.';
  }
  if (/public disclosure|publicity|publish.*(name|logo|project|amount)|name.*logo/i.test(record)) {
    return 'Please explain any publication or publicity conditions, including what may be disclosed, the approval process and when consent is required, so the applicant can review those terms before applying.';
  }
  // A pasted source passage is not a useful question title. Keep the user's
  // requirement recognizable while bounding the generated form input.
  const label = topic.length > 240 ? topic.slice(0, 237).trimEnd() + '…' : topic;
  return `Could you confirm the current requirement for “${label}” and what evidence we should provide?`;
}

function campaignRecipient(opportunity) {
  const name = String(opportunity?.name || '').trim();
  const funder = String(opportunity?.funder || '').trim();
  if (/CSIRO/i.test(name) && /\bRUIC\b/i.test(name)) return 'CSIRO RUIC programme team';
  if (/CSIRO/i.test(name) && /Kick-Start/i.test(name)) return 'CSIRO Kick-Start programme team';
  if (/CSIRO/i.test(name) && /Innovate to Grow/i.test(name)) return 'CSIRO Innovate to Grow team';
  if (!funder.includes('/')) {
    const clean = funder.replace(/\s*\([^)]*administrator[^)]*\)/i, '').trim();
    if (clean) return clean;
  }
  return 'Programme team';
}

function campaignEvidenceLinks(campaign, opportunity) {
  const sources = Array.isArray(campaign?.sources) ? campaign.sources : [];
  const sourceById = new Map(sources.map(source => [source.id, source]));
  const links = [];
  const seen = new Set();
  const add = (title, url, notes = '', source = null, checkedAt = source?.checked_at || '') => {
    if (typeof url !== 'string' || !url.trim()) return;
    let parsed;
    try { parsed = new URL(url); } catch { return; }
    if (!['http:', 'https:'].includes(parsed.protocol)) return;
    const noteText = String(notes || '');
    const key = `${source?.id || parsed.href}\n${noteText}\n${checkedAt}`;
    if (seen.has(key)) return;
    if (links.length >= 10) {
      throw new Error('This route has more than 10 source excerpts. Split the clarification into smaller drafts so every excerpt stays attached.');
    }
    if (noteText.length > 5000) {
      throw new Error('A linked source excerpt is too long to preserve in the draft. Use a shorter exact passage.');
    }
    seen.add(key);
    links.push({title: String(title || 'Campaign source').trim().slice(0, 500),
      url: parsed.href, notes: noteText,
      source_id: source?.id || '', checked_at: checkedAt || ''});
  };
  const windowSource = sourceById.get(opportunity?.window_source_id);
  if (windowSource || opportunity?.window_source_quote) {
    const quoteDate = opportunity.window_checked_at || '';
    const sourceDate = windowSource?.checked_at || 'date not recorded';
    const changed = !windowSource || !opportunity.window_source_url
      || opportunity.window_source_url !== windowSource.url
      || !quoteDate || quoteDate !== windowSource.checked_at;
    const dateNote = !quoteDate ? 'date not recorded'
      : changed ? `checked ${quoteDate}; linked source record differs or has since changed (now ${sourceDate}), so recheck before reuse`
        : `checked ${quoteDate}`;
    add(windowSource?.title || opportunity?.name,
      opportunity.window_source_url || windowSource?.url || opportunity?.url,
      `Application-window wording (user-entered, unverified; ${dateNote}): ${opportunity.window_source_quote || 'no exact wording recorded'}`,
      windowSource, quoteDate);
  } else if (opportunity?.url) {
    add(opportunity.name, opportunity.url);
  }
  for (const row of Array.isArray(campaign?.requirements) ? campaign.requirements : []) {
    if (row.opportunity !== opportunity?.name) continue;
    const source = sourceById.get(row.source_id);
    const checkedAt = row.checked_at || '';
    const sourceDate = source?.checked_at || 'date not recorded';
    const changed = source && (row.source_url !== source.url || !checkedAt
      || row.checked_at !== source.checked_at);
    const dateNote = !checkedAt ? 'date not recorded'
      : changed ? `checked ${checkedAt}; linked source record differs or has since changed (now ${sourceDate}), so recheck before reuse`
        : `checked ${checkedAt}`;
    const notes = row.source_quote
      ? `Requirement wording (user-entered, unverified; ${dateNote}): ${row.source_quote}` : '';
    add(source?.title || `Requirement: ${row.rule}`, row.source_url || source?.url,
      notes, source, row.checked_at || '');
  }
  return links;
}

function localToday() {
  const today = new Date();
  return [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'),
    String(today.getDate()).padStart(2, '0')].join('-');
}

function currentCheckDate(value, today) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')
      || !/^\d{4}-\d{2}-\d{2}$/.test(today || '')) return false;
  const checked = Date.parse(`${value}T00:00:00Z`);
  const current = Date.parse(`${today}T00:00:00Z`);
  return Number.isFinite(checked) && Number.isFinite(current)
    && new Date(checked).toISOString().slice(0, 10) === value
    && checked <= current && (current - checked) / 86400000 <= 90;
}

export function campaignClarificationDraft(campaign, opportunity, campaignLink = null, today = localToday()) {
  const sources = Array.isArray(campaign.sources) ? campaign.sources : [];
  const open = (campaign.requirements || []).filter(row => row.opportunity === opportunity.name && (
    row.status !== 'met' || ![row.evidence, row.source_url, row.source_quote]
      .every(value => String(value || '').trim()) || !currentCheckDate(row.checked_at, today)
      || (row.source_id && (() => {
        const source = sources.find(item => item.id === row.source_id);
        return !source || source.url !== row.source_url || source.checked_at !== row.checked_at;
      })())
  ));
  const routeQuestions = [];
  const addRouteQuestion = question => { if (question && !routeQuestions.includes(question)) routeQuestions.push(question); };
  if ((opportunity.application_mode || 'unknown') === 'unknown') {
    addRouteQuestion('Does this route require a formal application or registration, and which organisation or person is allowed to apply?');
  } else if (opportunity.application_mode === 'required' && !String(opportunity.applicant || '').trim()) {
    addRouteQuestion('Which organisation or person should be the applicant or programme lead, and what evidence is needed to confirm that role?');
  }
  if (opportunity.status === 'clarification') {
    addRouteQuestion('Please confirm the outstanding programme point recorded in our notes and the current rule that should guide the next step.');
  }
  const windowKind = opportunity.application_window
    || (opportunity.deadline ? 'fixed' : 'unknown');
  const currentWindow = hasCurrentApplicationWindowEvidence(opportunity, today, sources);
  if (windowKind === 'unknown') {
    addRouteQuestion('Please confirm whether this route has a fixed or rolling intake, its current dates and any next closing date.');
  } else if (!currentWindow && windowKind === 'fixed') {
    addRouteQuestion('Please confirm the current closing date and whether the published intake is still accepting applications.');
  } else if (!currentWindow && windowKind === 'rolling') {
    addRouteQuestion('Please confirm that the route still accepts applications on a rolling basis and whether any current intake conditions apply.');
  }
  if (!String(opportunity.url || '').trim()) {
    addRouteQuestion('Please direct us to the current official programme guidance and application or registration page.');
  }
  const questions = [
    ...open.map(row => clarificationQuestion(row.rule, row)).filter(Boolean),
    ...routeQuestions,
  ];
  const hasQuestions = questions.length > 0;
  const routeFit = String(opportunity.fit || '').trim();
  const organisation = String(campaign.organisation || '').trim();
  const draft = {
    openCount: open.length,
    routeGapCount: routeQuestions.length,
    workflow: 'brief',
    title: 'Clarification: ' + opportunity.name,
    recipient: campaignRecipient(opportunity),
    notes: [
      `Prepare an unsent clarification for ${organisation || 'the organisation named in the campaign'} about the selected route “${opportunity.name}”.`,
      routeFit ? `Route-specific context recorded by the campaign (unverified): ${routeFit}`
        : 'No route-specific project context is recorded; do not invent one.',
      'Use only this route and its linked evidence. Do not claim eligibility, secured funds, approved scope, prior contact or authority to apply unless a person has confirmed it.',
    ].join(' '),
    questions: hasQuestions ? questions.join('\n')
      : 'Could you confirm the current applicant eligibility, permitted costs and application timetable for this opportunity?',
    organisation: campaign.organisation || '',
    signatory: campaign.signatory || '',
    sender_role: campaign.sender_role || '',
    contact_details: campaign.contact_details || '',
    campaign_sender_review: true,
    use_search: false,
    use_model: false,
  };
  if (campaignLink) draft.campaign_link = {...campaignLink,
    evidence_links: campaignEvidenceLinks(campaign, opportunity)};
  return draft;
}

/** Map saved local profile details into blank campaign identity fields on opt-in. */
export function campaignIdentityFromProfile(profile, current = {}) {
  const saved = profile && typeof profile === 'object' ? profile : {};
  const fields = {
    signatory: saved.full_name,
    sender_role: saved.role,
    organisation: saved.organisation,
    contact_details: ['email', 'phone', 'website']
      .map(key => typeof saved[key] === 'string' ? saved[key].trim() : '')
      .filter(Boolean).join('\n'),
  };
  return Object.fromEntries(Object.entries(fields).filter(([key, value]) =>
    typeof value === 'string' && value.trim() && !String(current[key] || '').trim()));
}

/** Context-aware copy for an unsent campaign clarification in the shared brief UI. */
export function campaignLetterReviewCopy(payload = {}) {
  const missingSignatory = !String(payload.signatory || '').trim();
  const missingContact = !String(payload.contact_details || '').trim();
  let description = 'Review the recipient, factual claims and approved campaign sign-off before using this unsent draft.';
  if (missingSignatory && missingContact) {
    description = 'No authorised signatory or reply contact is recorded. Add approved details before using this unsent draft.';
  } else if (missingSignatory) {
    description = 'No authorised signatory is recorded. Confirm who may sign this letter before using this unsent draft.';
  } else if (missingContact) {
    description = 'No approved reply contact is recorded. Add one before using this unsent draft.';
  }
  return {
    title: 'Prepare a campaign letter for review.',
    description,
    status: 'Campaign draft ready for review. It has not been sent; verify the recipient, claims and authorised sign-off before use.',
    announcement: 'Campaign letter ready for review. Not sent.',
  };
}

/** A generated campaign letter can be recorded locally, but never sent here. */
export function campaignDraftLogBlockReason(link) {
  if (!link?.id || !Number.isSafeInteger(link.revision) || link.revision < 1) {
    return 'Save the campaign before creating a clarification draft so Sinter can link it to the correct record.';
  }
  if (link.dirty) {
    return 'This draft was made from unsaved campaign changes. Save the campaign, then create a fresh clarification draft before logging it.';
  }
  if (link.logged) return 'This draft is already recorded in the campaign communication log.';
  return '';
}

export function campaignCommunicationFromDraft({report, content, channel, date}) {
  const link = report?.campaign_link;
  const blocked = campaignDraftLogBlockReason(link);
  if (blocked) throw new Error(blocked);
  const body = String(content || '').trim();
  if (!body) throw new Error('The draft is empty. Add the letter text before saving it to the campaign log.');
  if (body.length > 20000) throw new Error('This draft is over the campaign log’s 20,000-character limit. Save a separate copy and shorten it before logging.');
  const subject = String(report.document_title || report.title || 'Untitled campaign draft').trim();
  if (subject.length > 1000) throw new Error('The draft title is over the campaign log’s 1,000-character limit.');
  const counterparty = String(report.input_snapshot?.recipient || report.recipient || '').trim();
  if (counterparty.length > 300) throw new Error('The recipient is over the campaign log’s 300-character limit.');
  if (!['email', 'letter', 'portal', 'other'].includes(channel)) throw new Error('Choose a draft channel before saving it to the campaign log.');
  const evidenceLinks = link.evidence_links || [];
  if (!Array.isArray(evidenceLinks) || evidenceLinks.length > 10) {
    throw new Error('A campaign communication can include at most 10 linked sources.');
  }
  const checkedEvidenceLinks = evidenceLinks.map((item, index) => {
    const title = String(item?.title || '').trim();
    const url = String(item?.url || '').trim();
    const notes = String(item?.notes || '').trim();
    const sourceId = String(item?.source_id || '').trim();
    const checkedAt = String(item?.checked_at || '').trim();
    if (title.length > 500 || url.length > 2000 || notes.length > 2000) {
      throw new Error(`Campaign source link ${index + 1} is too long to record.`);
    }
    if (sourceId && !/^[0-9a-f]{32}$/.test(sourceId)) {
      throw new Error(`Campaign source link ${index + 1} has an invalid saved source ID.`);
    }
    if (checkedAt && (!/^\d{4}-\d{2}-\d{2}$/.test(checkedAt)
        || Number.isNaN(Date.parse(`${checkedAt}T00:00:00Z`))
        || new Date(`${checkedAt}T00:00:00Z`).toISOString().slice(0, 10) !== checkedAt)) {
      throw new Error(`Campaign source link ${index + 1} has an invalid check date.`);
    }
    if (url) {
      let parsed;
      try { parsed = new URL(url); } catch { throw new Error(`Campaign source link ${index + 1} is not a valid URL.`); }
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        throw new Error(`Campaign source link ${index + 1} must use HTTP or HTTPS.`);
      }
    }
    if (!title && !url && !notes && !sourceId && !checkedAt) return null;
    return {title, url, notes, source_id: sourceId, checked_at: checkedAt};
  }).filter(Boolean);
  const draftDate = String(date || '');
  if (draftDate && (!/^\d{4}-\d{2}-\d{2}$/.test(draftDate)
      || Number.isNaN(Date.parse(`${draftDate}T00:00:00Z`))
      || new Date(`${draftDate}T00:00:00Z`).toISOString().slice(0, 10) !== draftDate)) {
    throw new Error('Use a valid YYYY-MM-DD date, or leave the communication date blank.');
  }
  return {
    opportunity: String(link.opportunity || ''), date: draftDate, direction: 'outgoing', status: 'draft',
    channel, counterparty, subject, content: body, evidence_links: checkedEvidenceLinks,
  };
}
