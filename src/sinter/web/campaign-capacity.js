/** Editor estimates; the server validates normalized fields and encoded size. */
export const CAMPAIGN_TEXT_LIMIT = 200_000;
export const CAMPAIGN_BYTE_LIMIT = 1_000_000;

function textCharacters(value) {
  if (typeof value === 'string') {
    let count = 0;
    for (const character of value) count += 1;
    return count;
  }
  if (Array.isArray(value)) return value.reduce((count, item) => count + textCharacters(item), 0);
  if (value && typeof value === 'object') return textCharacters(Object.values(value));
  return 0;
}

export function campaignCapacity(document) {
  const characters = textCharacters(document);
  const bytes = new TextEncoder().encode(JSON.stringify(document)).length;
  const over = characters > CAMPAIGN_TEXT_LIMIT || bytes > CAMPAIGN_BYTE_LIMIT;
  return {characters, bytes, state: over ? 'over' :
    characters >= CAMPAIGN_TEXT_LIMIT * 0.9 || bytes >= CAMPAIGN_BYTE_LIMIT * 0.9 ? 'near' : 'within'};
}
