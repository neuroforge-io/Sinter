import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignActionOwnerState, campaignOwnerKind,
  normalizeCampaignActionOwners} from '../src/sinter/web/campaign-owner.js';

test('owner kind migration is conservative and preserves explicit records', () => {
  assert.equal(campaignOwnerKind('', '', false), 'unassigned');
  assert.equal(campaignOwnerKind('', 'person'), 'unassigned');
  assert.equal(campaignOwnerKind('Unassigned', 'person'), 'unassigned');
  assert.equal(campaignOwnerKind('Treasurer (suggested)', '', false), 'role');
  assert.equal(campaignOwnerKind('Treasurer (suggested)', 'unknown'), 'role');
  assert.equal(campaignOwnerKind('Treasurer', '', false), 'unknown');
  assert.equal(campaignOwnerKind('Casey', ''), 'unknown');
  assert.equal(campaignOwnerKind('Treasurer', 'role', false), 'role');
});

test('owner summaries distinguish a role, an unknown type and a named person', () => {
  const role = campaignActionOwnerState('Treasurer', false, 'role');
  assert.equal(role.canAccept, false);
  assert.equal(role.summary, 'Suggested role only; no person named (Treasurer)');

  const legacyRole = campaignActionOwnerState('Treasurer (suggested)', false, 'role');
  assert.equal(legacyRole.summary, role.summary);
  assert.equal(legacyRole.export, role.export);

  const unknown = campaignActionOwnerState('Treasurer', false, 'unknown');
  assert.equal(unknown.canAccept, false);
  assert.match(unknown.summary, /Owner type not confirmed/);

  const person = campaignActionOwnerState('Casey', false, 'person');
  assert.equal(person.canAccept, true);
  assert.match(person.summary, /Named person: Casey; acceptance unconfirmed/);
});

test('acceptance on a role suggestion never changes its classification', () => {
  const state = campaignActionOwnerState('Treasurer', true, 'role');
  assert.equal(state.kind, 'role');
  assert.equal(state.canAccept, false);
  assert.match(state.export, /no person named/);
});

test('legacy acceptance cannot resolve an ambiguous owner type', () => {
  const [role, ambiguous, explicit] = normalizeCampaignActionOwners([
    {owner: 'Treasurer (suggested)', owner_confirmed: true},
    {owner: 'Casey', owner_confirmed: true},
    {owner: 'Treasurer', owner_kind: 'role', owner_confirmed: true},
  ]);
  assert.equal(role.owner_kind, 'role');
  assert.equal(role.owner_confirmed, false);
  assert.equal(role.owner, 'Treasurer (suggested)');
  assert.equal(ambiguous.owner_kind, 'unknown');
  assert.equal(ambiguous.owner_confirmed, false);
  assert.equal(explicit.owner_kind, 'role');
  assert.equal(explicit.owner_confirmed, true);
});
