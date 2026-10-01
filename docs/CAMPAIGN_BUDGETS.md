# Recorded quote amounts in campaign/v1

Sinter keeps the five budget-row fields unchanged: `item`, `opportunity`,
`quantity`, `unit_cost` and `quote_reference`. A quote reference is the person's
original free text. Sinter does not infer tax registration, GST treatment,
eligibility, eligible costs or an application amount from that wording. External
reviews may exist; the caveat states what Sinter has not qualified, without
asserting that nobody has reviewed the amounts elsewhere.

The budget summary uses isolated Decimal arithmetic on admitted quoted rows,
independent of an embedding caller's precision, rounding, traps and flags. For example,
two items at A$1,550 and one at A$200 give a recorded quoted subtotal of A$3,300,
even when one reference says GST included and another says GST excluded. Sinter
does not change either amount or add GST to make their bases match. Retain the
original references and ask the appropriate person to review the basis and the
funding rules before choosing an amount to request.

## What the summary fields mean

| Field | Meaning |
| --- | --- |
| `known_total` | Sum of recorded `quantity × unit_cost` values; it excludes unpriced rows. It is a quoted subtotal, not a complete project or application amount. |
| `total` | The same quoted sum when every recorded row has a cost; otherwise `null`. No rows is also `null`. |
| `complete` | Every recorded row has a unit cost and at least one row exists. It does not mean every necessary project cost has been recorded or reviewed. |
| `unknown_costs` | Recorded rows whose unit cost is `null`; these are never treated as zero. |
| `unquoted_costs` | Recorded rows without a quote reference; this is not a verification of references that are present. |
| `quoted_subtotal_over_ceiling` | Per-opportunity raw arithmetic: whether its known quoted subtotal is numerically greater than an entered AUD cash ceiling. It is `null` for a missing ceiling, non-AUD/unconfirmed/unsupported ceiling currency or non-cash route. |
| `over_ceiling` | Always `null` for this v1 quoted-amount policy: the application-level comparison remains unqualified. |
| `amount_basis_note` | Explains that quote bases may be mixed or unknown, no GST conversion is made, and Sinter has not qualified eligible costs/application amounts. |
| `comparison_note` | The separate funding-currency explanation. It does not qualify the amount or GST basis. |

An explicit zero amount remains zero; an absent amount remains unknown. A raw
crossing can be `true` even with unpriced lines. A `false` raw crossing means only
that the entered known amounts did not numerically cross the recorded ceiling;
it does not establish that the complete or eligible application fits. A ceiling
comparison of quoted figures is never a funder decision.

## Current and historical work

Quoted amounts on closed, submitted, paused or not-pursued routes remain in the
historical summary and original campaign. They are excluded from the current
quoted subtotal and current review counts. Unallocated rows remain visible and
are counted in the current quote summary; they are not assigned to a funding
route automatically.

`readiness.budget_amount_basis_review` counts active route groups with at least
one recorded budget row, plus one group if any unallocated budget rows exist.
These groups have an application amount basis that this v1 workflow cannot
qualify. The count is not evidence that a quote omits GST wording or contains a
tax error, and there is no checkbox or free-text wording that dismisses it. It
is displayed as review information independently of the overall readiness
status; it is not a go/no-go eligibility predicate.

`readiness.quoted_subtotals_above_ceiling` counts active raw crossings as review
observations. `readiness.budgets_over_ceiling` does not assert an application
comparison; it stays zero because v1 application comparisons are unqualified.
`readiness.funding_currency_review` remains a separate currency-review count.
None of these fields establishes eligibility or approval.

## Preservation and recovery

Saving, reopening and JSON backups retain the existing campaign/v1 fields,
amounts, references and source identities. There is no schema migration or tax
conversion. A rejected save keeps the prior saved revision; correcting inputs
and retrying requires an explicit action.

Older saved reports keep their original JSON on disk. Their returned derived
view uses the current quote policy without rewriting that historical JSON or
literal user edits. Newly prepared full reports, decision briefs and Word exports
label quote subtotals and retain the amount-basis caveat. Historical user-edited
text remains the author's original text and needs its own review.

This is a foundation for a future reviewed application-budget workflow. Typed
amount bases, supporting evidence and a separately reviewed application
amount/ceiling comparison are not implemented by this change. Sinter does not
determine which costs are eligible.
