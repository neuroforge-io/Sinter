import {localBackupText, localBackupControls} from './local-backup.js';

export const casebookBackupText = document => localBackupText(document, 'project');

export const casebookBackupControls = currentDocument => localBackupControls(
  currentDocument, {noun: 'project', label: 'Project',
    description: 'Captures current project inputs and unsaved edits. Add or clear any pending source first. No server connection is needed.',
    failureMessage: 'Could not prepare project backup text. Add or clear any pending source before trying again. Your project inputs are unchanged.'});
