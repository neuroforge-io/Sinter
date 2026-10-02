# Recorded funding totals

Campaigns can record funding stages and calculate a current-campaign summary
without a model, network request, submission or spending action. The human
workspace, CLI and Python interface call the same operation and validator.

Opportunity search and status filtering paginate the rail at 20 records per
page. Filtering does not change saved content or the full-campaign totals. Up
to 200 opportunities can be admitted; the existing 200,000-character and 1 MB
document bounds still apply. Oversized imports fail without replacing the
working copy. Export a backup before restructuring a document; nothing is
silently clipped or spread into extra campaigns.

In Campaigns, select an opportunity and open **Funding tracking**. Record its
programme round key, benefit type and application, award and receipt states.
Enter a draft target separately from an actual requested amount. Use cumulative
amounts for one round, benefit type and currency; update a received amount as
payments arrive rather than adding duplicate round records. Keep source
snapshots and notes beside each amount. **Update funding totals** previews the
current working copy; **Save campaign** persists it with the existing revision
guard. Editing marks the totals stale until refreshed.

The summary keeps cash and nominal service credits separate, groups currencies
without conversion and never adds pipeline stages together. It covers the
selected campaign, not all campaigns or an audited lifetime ledger. A blank
amount is unknown; an entered zero is a known zero. Empty stages do not prove
there was no historical funding.

Available totals use individual ceilings for recorded eligible **Open** routes
with current application-window, eligibility and ceiling source checks. They
are possible ceilings, not guaranteed funding. Whole programme pools, equity,
tax relief and matched research vouchers are outside these cash/credit totals.
The existing quoted project-cost summary remains separate. Closing a route
does not erase its submitted request, award or receipt. Closed amount totals
use actual requests from closed submitted applications, never old ceilings.

Round keys are explicit; names and URLs do not reliably identify a round.
Unidentified records and every amount in a duplicate-key group are excluded
until reconciled. Counts identify duplicate rounds separately from raw records.
One benefit type per round is supported in this pass; mixed cash/credit rounds
need reconciliation and cannot be represented by inventing independent keys.
Entered statuses and evidence remain user assessments, not funder verification.
Amounts entered without the corresponding event status remain saved and have
explicit exclusions. An explicit **Not awarded** alongside **Received** requires
reconciliation before a receipt total is shown; an unknown award does not erase
a recorded receipt. Closed-outcome counts are also present in human reports.

The native window's **Funding campaigns** action inspects the same saved
campaign totals and full source notes without a listener or another runtime.
It is read-only; editing remains in the full workbench. Closing the funding view
leaves the main workspace open. Saved campaign reports retain their snapshot
date separately from the date of refreshed derived checks.

## Shared operation

`campaigns.funding_summary` accepts `{"document": <campaign>}` and returns
`sinter-funding-summary/v1`: `as_of`, `scope`, `counts`, `stages`,
`duplicate_rounds`, `exclusions`, `amount_basis`, `notice` and human `markdown`.
Each stage has `opportunities`, currency/benefit `groups`, and `excluded_rows`.
Groups expose `known_total`, `total`, `known_amounts`, `unknown_amounts` and
`excluded_amounts`. `total` is null for incomplete groups; `known_total` is null
when no amount qualifies. A numeric known subtotal never fills unknown amounts.

```sh
sinter operations campaigns.funding_summary
sinter run campaigns.funding_summary --input campaign-input.json
sinter run campaigns.funding_summary --input campaign-input.json --format json
```

Machine stdout uses the existing `sinter-operation-result/v1` envelope, stable
operation ID and existing exit codes. Human output uses the same computed
summary. A Python caller can use:

```python
from sinter.runtime import Runtime

with Runtime("my-workspace") as runtime:
    saved = runtime.call("campaigns.get", {"id": campaign_id})
    result = runtime.call("campaigns.funding_summary", {
        "document": saved["document"],
    })
```

The equivalent UI route is `POST /api/campaigns/funding-summary`, subject to the
existing local launch-token/host protections. No provider consent, account or
credential operation is added. Funding tracking is excluded from the existing
campaign assistant's selected context.

## Optional campaign extension

An opportunity may contain `funding_tracking` with:

- `round_key`: explicit programme/round identity, up to 200 characters.
- `benefit_type`: `unknown`, `cash` or `credits`.
- `eligibility`: `unknown`, `eligible` or `ineligible`.
- `ceiling_scope`: `unknown`, `individual` or `program_pool`.
- `application_status`: `unknown`, `not_applied`, `preparing` or `submitted`.
- `award_status`: `unknown`, `not_awarded` or `awarded`.
- `receipt_status`: `unknown`, `not_received` or `received`.
- `closure_reason`: `unknown`, `round_closed`, `declined`, `withdrawn`,
  `ineligible`, `not_pursued` or `other`.
- `eligibility_evidence` and `ceiling_evidence`: claim snapshots with
  `source_id`, `source_url`, `source_quote`, `checked_at` and `evidence`.
- `target`, `requested`, `awarded` and `received`: records with `amount`,
  `currency`, `source_id`, `source_url`, `source_quote`, `checked_at` and `notes`.

Amounts normalize to decimal strings with two places or null. New amount
currencies default to `unconfirmed`; supported denominations match the existing
ceiling currencies. `other` is retained but excluded from numeric comparison.
The existing ceiling's legacy AUD interpretation is unchanged. Broken source
references, invalid amounts and unknown keys fail before save. Source snapshots
are retained rather than rewritten when registered source metadata changes.

Absent tracking stays absent through validation, save, reopen and export.
Legacy reports retain their previous shape when tracking is absent. The campaign
schema remains `sinter-campaign/v1` with an optional additive field. New readers
accept older backups; older binaries that reject unknown fields cannot edit a
tracking-enabled backup. Preserve original backups and upgrade the consumer;
do not remove tracking merely to make an old binary accept it.
