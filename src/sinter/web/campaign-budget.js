/** Recorded cost arithmetic only. Never infer GST or an application amount. */
export const QUOTED_BUDGET_NOTE = 'Recorded costs may be quotes or planning estimates; their GST basis may be unknown or mixed. No GST conversion was made. Sinter has not qualified eligible costs or the application amount; this subtotal is not an eligibility or application-ceiling decision. Record the grant request and applicant cash or in-kind contributions separately; this subtotal does not establish them.';

function moneyCents(value) {
  if (!['string', 'number'].includes(typeof value)) return null;
  const raw = String(value);
  if (raw.length > 30) return null;
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(raw);
  if (!match) return null;
  const cents = BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0'));
  return cents <= 100_000_000_000n ? cents : null;
}

export function quotedAmount(cents) {
  return cents === null ? 'Amount not recorded'
    : `A$${(cents / 100n).toLocaleString('en-AU')}.${String(cents % 100n).padStart(2, '0')}`;
}

/** Bound draft input as the server does; invalid or absent values stay unknown. */
export function campaignBudgetRowState(row = {}) {
  const raw = String(row.quantity ?? '');
  const quantity = /^(\d{1,6})$/.test(raw) && Number(raw) >= 1 && Number(raw) <= 100000
    ? BigInt(raw) : null;
  const unitCents = moneyCents(row.unit_cost);
  const lineCents = unitCents === null || quantity === null ? null : unitCents * quantity;
  const referenceRecorded = typeof row.quote_reference === 'string' && Boolean(row.quote_reference.trim());
  return {quantity, unitCents, lineCents, priced: lineCents !== null, referenceRecorded,
    title: typeof row.item === 'string' && row.item.trim() ? row.item : 'Untitled cost',
    amount: lineCents === null ? quantity === null ? 'Quantity needs checking' : 'Price needed'
      : 'Recorded line amount · ' + quotedAmount(lineCents),
    reference: referenceRecorded ? 'Reference recorded · unverified' : 'Reference needed'};
}

/** Call with the current rows only; historical rows remain available separately. */
export function campaignQuotedBudget(rows = []) {
  const states = rows.map(campaignBudgetRowState);
  const knownCents = states.reduce((sum, row) => sum + (row.lineCents ?? 0n), 0n);
  const unknownCosts = states.filter(row => !row.priced).length;
  const priced = states.length - unknownCosts;
  const missingReferences = states.filter(row => !row.referenceRecorded).length;
  const complete = states.length > 0 && !unknownCosts;
  return {knownCents, unknownCosts, priced, missingReferences, complete,
    total: complete ? knownCents : null,
    label: !rows.length
      ? 'No costs recorded for active opportunities. The current project total is unknown.'
      : !priced ? `No costs priced yet · ${unknownCosts} item${unknownCosts === 1 ? '' : 's'} awaiting prices`
        : `Recorded cost subtotal (AUD): ${quotedAmount(knownCents)}${unknownCosts ? ' · ' + unknownCosts + ' uncosted item' + (unknownCosts === 1 ? '' : 's') + ' — total incomplete' : ''}`,
    nextIndex: states.findIndex(row => !row.priced || !row.referenceRecorded),
    amountBasisNote: QUOTED_BUDGET_NOTE};
}
