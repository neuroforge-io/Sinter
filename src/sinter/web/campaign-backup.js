import {localBackupText, localBackupControls} from './local-backup.js';
export {resetLocalBackupControls as resetCampaignBackupControls} from './local-backup.js';

/** Preserve the working copy, without applying server admission or normalization. */
export const campaignBackupText = document => localBackupText(document, 'campaign');

/** Explicit local recovery: the callback reads the current editable campaign. */
export function campaignBackupControls(currentDocument) {
  const controls = localBackupControls(currentDocument, {noun: 'campaign', label: 'Campaign'});
  // Preserve the existing component's public styling hook.
  controls.className = 'campaign-clipboard-backup';
  return controls;
}
