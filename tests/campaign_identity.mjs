import assert from 'node:assert/strict';
import test from 'node:test';
import {campaignIdentityFromProfile} from '../src/sinter/web/campaign-letter.js';

test('saved profile values fill only blank campaign identity fields', () => {
  const copied = campaignIdentityFromProfile({
    full_name: 'Taylor Example', role: 'Founder', organisation: 'NeuroforgeIO Pty Ltd',
    email: 'taylor@example.invalid', phone: '', website: 'https://neuroforge.io/',
  }, {organisation: 'NeuroforgeIO Pty Ltd', signatory: '', sender_role: 'Director', contact_details: ''});
  assert.deepEqual(copied, {
    signatory: 'Taylor Example',
    contact_details: 'taylor@example.invalid\nhttps://neuroforge.io/',
  });
});

test('profile data is opt-in and empty or whitespace-only values are not copied', () => {
  assert.deepEqual(campaignIdentityFromProfile({
    full_name: '  ', role: '', organisation: '', email: '', phone: '', website: '',
  }, {}), {});
  assert.deepEqual(campaignIdentityFromProfile(null, {}), {});
});
