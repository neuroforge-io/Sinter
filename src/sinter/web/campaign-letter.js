/** Build a funder-specific clarification draft without campaign-wide context. */
export function clarificationQuestion(requirement) {
  const topic = String(requirement || '').replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!topic) return '';
  if (/^(what|when|where|who|which|how|whether|does|do|is|are|can|could|will|would|should|has|have)\b/i.test(topic)) {
    return topic.endsWith('?') ? topic : topic + '?';
  }
  // A pasted source passage is not a useful question title. Keep the user's
  // requirement recognizable while bounding the generated form input.
  const label = topic.length > 240 ? topic.slice(0, 237).trimEnd() + '…' : topic;
  return `Could you confirm the current requirement for “${label}” and what evidence we should provide?`;
}

export function campaignClarificationDraft(campaign, opportunity, campaignLink = null) {
  const open = (campaign.requirements || []).filter(row => row.opportunity === opportunity.name && (
    row.status !== 'met' || ![row.evidence, row.source_url, row.source_quote, row.checked_at]
      .every(value => String(value || '').trim())
  ));
  const questions = open.map(row => clarificationQuestion(row.rule)).filter(Boolean);
  const draft = {
    openCount: open.length,
    workflow: 'brief',
    title: 'Clarification: ' + opportunity.name,
    recipient: opportunity.funder || '',
    // A selected opportunity can be introduced by its title and recipient;
    // do not turn campaign-wide objectives into letter background.
    notes: '',
    questions: questions.length ? questions.join('\n')
      : 'Could you confirm the current applicant eligibility, permitted costs and application timetable for this opportunity?',
    organisation: campaign.organisation || '',
    signatory: campaign.signatory || '',
    sender_role: campaign.sender_role || '',
    contact_details: campaign.contact_details || '',
    campaign_sender_review: true,
    use_search: false,
    use_model: false,
  };
  if (campaignLink) draft.campaign_link = campaignLink;
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
  const draftDate = String(date || '');
  if (draftDate && (!/^\d{4}-\d{2}-\d{2}$/.test(draftDate)
      || Number.isNaN(Date.parse(`${draftDate}T00:00:00Z`))
      || new Date(`${draftDate}T00:00:00Z`).toISOString().slice(0, 10) !== draftDate)) {
    throw new Error('Use a valid YYYY-MM-DD date, or leave the communication date blank.');
  }
  return {
    opportunity: String(link.opportunity || ''), date: draftDate, direction: 'outgoing', status: 'draft',
    channel, counterparty, subject, content: body, evidence_links: [],
  };
}
