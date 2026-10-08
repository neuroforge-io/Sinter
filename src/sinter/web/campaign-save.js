/** Admit a usable save acknowledgement before replacing any local editor state. */
export function acknowledgedCampaign(saved) {
  const document = saved?.document;
  const collections = ['opportunities', 'requirements', 'answers', 'budget',
    'actions', 'sources', 'communications', 'assets'];
  const text = ['title', 'organisation', 'objective', 'signatory',
    'sender_role', 'contact_details'];
  if (!saved || Array.isArray(saved) || !/^[0-9a-f]{32}$/.test(saved.id || '')
      || !Number.isSafeInteger(saved.revision) || saved.revision < 1
      || !document || document.schema !== 'sinter-campaign/v1'
      || !text.every(key => typeof document[key] === 'string') || !document.title.trim()
      || !collections.every(key => Array.isArray(document[key])
        && document[key].every(row => row && typeof row === 'object' && !Array.isArray(row)))) {
    const failure = new Error('The app returned a save reply that could not confirm a saved campaign. Your earlier editor version is unchanged.');
    failure.partialResult = saved;
    throw failure;
  }
  return saved;
}
