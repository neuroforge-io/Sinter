/** Shared, conservative ownership language for campaign actions. */
const ACTION_OWNER_KINDS = new Set(['unknown', 'person', 'role', 'unassigned']);

function ownerLabel(owner) {
  return String(owner || '').trim()
    .replace(/\s*\((?:suggested|suggested role)\)\s*$/i, '').trim();
}

export function campaignOwnerKind(owner, ownerKind) {
  const value = String(owner || '').trim();
  if (!value || /\bunassigned\b/i.test(value)) return 'unassigned';
  if (/\b(?:suggested|role suggestion)\b/i.test(value)) return 'role';
  if (ACTION_OWNER_KINDS.has(ownerKind)) return ownerKind;
  return 'unknown';
}

/** Normalize additive owner fields while preserving safe legacy intent. */
export function normalizeCampaignActionOwners(actions) {
  return (Array.isArray(actions) ? actions : []).map(action => {
    const next = {...action};
    const hadOwnerKind = Object.hasOwn(next, 'owner_kind');
    next.owner ??= '';
    next.owner_confirmed ??= false;
    next.owner_kind = campaignOwnerKind(next.owner, next.owner_kind);
    // Older versions allowed a role suggestion to carry a checked acceptance
    // box. Keep the suggestion and discard only that invalid legacy signal.
    if (!hadOwnerKind && next.owner_kind !== 'person') next.owner_confirmed = false;
    return next;
  });
}

export function campaignActionOwnerState(owner, accepted = false, ownerKind = '') {
  const value = String(owner || '').trim();
  const kind = campaignOwnerKind(value, ownerKind);
  if (kind === 'unassigned') {
    return {kind, summary: 'No person named; owner needed',
      detail: 'Owner needed — no person is recorded. Assign a named person before marking acceptance.',
      export: 'Unassigned', state: 'unassigned', canAccept: false};
  }
  if (kind === 'role') {
    const label = ownerLabel(value) || value;
    return {kind, summary: `Suggested role only; no person named (${label})`,
      detail: 'This is a role suggestion, not a named person. Record a person who agrees before marking acceptance.',
      export: `${label} (suggested role; no person named)`, state: 'suggested', canAccept: false};
  }
  if (kind === 'unknown') {
    return {kind, summary: `Owner type not confirmed: ${value}`,
      detail: 'Confirm whether this entry is a named person or a suggested role before recording acceptance.',
      export: `${value} (owner type not confirmed)`, state: 'unknown', canAccept: false};
  }
  if (accepted) {
    return {kind, summary: `Named person: ${value}; user-marked accepted`,
      detail: 'Acceptance recorded by user; verify directly with this person.',
      export: `${value} (user-marked accepted; verify directly)`, state: 'accepted', canAccept: true};
  }
  return {kind, summary: `Named person: ${value}; acceptance unconfirmed`,
    detail: 'Named person recorded. Confirm that this person has accepted the action.',
    export: `${value} (named person; acceptance unconfirmed)`, state: 'confirm', canAccept: true};
}
