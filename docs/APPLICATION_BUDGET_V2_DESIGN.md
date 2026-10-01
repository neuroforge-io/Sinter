# Application-budget v2 architecture handoff

Status: open implementation proposal, not implemented or qualified. Source assessment: `7bbdc870a7cbc3a2d1083b7e8b706121bed3c584`, 2026-10-01. All examples are fictional local data. No tax conversion, provider operation, transmission, submission, eligibility decision or installed-platform result is proposed or claimed.

This handoff preserves the full objective: a usable budget workflow that retains exact quoted AUD amounts and their basis, records separately reviewed application amounts and evidence, and admits only a supported numerical comparison. The quoted-summary checkpoint is an immediate truthfulness improvement. It is not completion of that objective or of the full product.

## Assessed baseline before the quoted-summary foundation

`src/sinter/campaigns.py:413` accepts exactly five budget-row keys: `item`, `opportunity`, `quantity`, `unit_cost`, `quote_reference`. Admission uses canonical decimal strings with two places, and null remains unknown. Quote references preserve supplied wording. `_budget_total` mechanically sums quoted unit costs times quantity. `_budget_summary` at that baseline compared the raw sum against an entered AUD ceiling under the legacy v1 gate, including a known subtotal while another line is unknown.

The fictional witness is 110.00 explicitly including GST and 100.00 explicitly excluding GST, against an AUD 200.00 ceiling. The raw subtotal is 210.00. That is arithmetic on unlike recorded amounts, not a reviewed application amount. Adding an unknown production line makes the total incomplete but did not remove the baseline over-ceiling conclusion. A nonblank reference does not establish a supplier quote, amount basis or application-ready amount. Free text must not be parsed into an asserted basis.

The baseline UI called the sum a known cost estimate. The full pack called a fully priced sum current entered cost and could say it exceeded the funding ceiling. The baseline decision brief and its Word export carried the subtotal while intentionally omitting quote references. Therefore the brief itself needs a basis caveat; keeping it only in the audit pack is insufficient.

## Immediate quoted-summary foundation

Use a small pure quoted-budget module. Retain the existing row schema, amounts, quantity, raw totals, active/historical filtering, incomplete states and Decimal/cents behavior.

- Label sums `Recorded quoted subtotal (AUD)` and state that amounts may use different GST bases, are recorded as quoted, and have not been converted or qualified as application amounts.
- Existing `known_total`, `total`, `complete`, `unknown_costs` and `unquoted_costs` describe quoted input coverage only. A complete raw quote total is not a complete application budget.
- Set application `over_ceiling` to null/unsupported for every unreviewed v1 amount-basis comparison. It must not feed an application/readiness conclusion or `budgets_over_ceiling`.
- An optional `quoted_subtotal_over_ceiling` is only an arithmetic observation about the known recorded subtotal and entered nominal ceiling. Apply the existing legacy v1 AUD gate, which excludes `non_cash_support` without positively qualifying other route types. Always accompany it with the independent amount-basis caveat. False does not establish under-cap status, especially with unknown lines. Neither true nor false establishes tax treatment or eligibility.
- Keep `amount_basis_note` separate from currency `comparison_note` and currency review metrics. It must remain visible when the currency note is empty.
- Keep historical rows outside current totals and current review counts. Preserve historical rows and references in backups and audit output.
- Show consistent caveats in the live total, decision brief/Word, full pack and reopened policy view of a saved report. Preserve disk originals and user edits.

This milestone cannot supply reviewed application entry, evidence, stale-review handling or qualified application comparisons. Those remain open below.

## Design alternatives

1. **Quoted-summary foundation only:** no new schema; remove unsupported application conclusions and make the raw arithmetic honest. Low compatibility cost, but no usable reviewed application budget.
2. **Inline route-scoped v2 reviews, recommended first:** stable budget-row identity, separate quote basis/evidence, separate reviewed application line amount, and per-route basis requirement/ceiling evidence. This is the narrowest usable extension to the current editor.
3. **Separate route application worksheets:** worksheets reference stable quoted-row IDs and record allocations and reviewed amounts independently. This supports one quote contributing differently to several applications. It adds allocation, duplication and reconciliation controls and should be separately scoped if the inline model is inadequate.

Do not half-ship new application fields as optional v1 keys. The numerical meaning changes and older interfaces cannot be assumed to preserve or understand it.

## Proposed domain contract

Use `sinter-campaign/v2` only when the user explicitly adds the new review records and saves/upgrades that working copy. Ordinary v1 documents keep their existing schema and five-key rows. Reading v1 must not write a migration or add asserted basis defaults to stored originals. Presentation can project unknown basis without altering the persisted document.

The following types describe a proposed contract. They are not existing API support. Field names can be finalized during implementation, but the separations and invariants must remain.

```typescript
type MoneyAUD = string; // canonical nonnegative decimal, exactly two places
type Basis = 'unknown' | 'gst_inclusive' | 'gst_exclusive' | 'other';
type Sha256 = string;   // exactly 64 lowercase hex characters
type DateRecorded = string; // YYYY-MM-DD or '' where not recorded

interface EvidenceSnapshot {
  source_id: string | null; // optional link to a retained stable campaign source
  source_title: string;
  source_url: string;
  source_quote: string;    // exact supplied wording; never refreshed from a link
  checked_at: DateRecorded;
}

interface ApplicantBasisContext {
  applicant: string; // explicit route applicant snapshot, not inferred organisation
  gst_status: 'unknown' | 'registered' | 'not_registered';
  evidence: EvidenceSnapshot[];
  rationale: string; // why the operator recorded this context; no policy engine
}

interface RouteBasisReview {
  required_application_basis: Basis;
  application_evidence: EvidenceSnapshot[];
  ceiling_basis: Basis;
  ceiling_evidence: EvidenceSnapshot[];
  applicant_context: ApplicantBasisContext;
  rationale: string;
  reviewed: boolean; // an operator-recorded review, not independent verification
  reviewed_at: string | null;
  context_sha256: Sha256 | null;
}

interface ApplicationAmountReview {
  amount: MoneyAUD | null; // entire line total, NOT a quoted unit amount
  basis: Basis;
  evidence: EvidenceSnapshot[];
  rationale: string;
  reviewed: boolean;
  reviewed_at: string | null;
  context_sha256: Sha256 | null;
}

interface BudgetRowV2 {
  id: string; // stable, unique within campaign; never derived from mutable item text
  item: string;
  opportunity: string; // existing route reference; '' retains unallocated work
  quantity: number; // existing positive integer contract
  unit_cost: MoneyAUD | null; // retained quoted unit amount in AUD
  quote_reference: string;    // retained original reference
  quoted_basis: Basis;
  quoted_basis_evidence: EvidenceSnapshot[];
  application_review: ApplicationAmountReview | null;
}

// In v2, an opportunity may carry budget_basis: RouteBasisReview | null.
// Existing ceiling and ceiling_currency retain their original meaning/values.
```

`unknown` is the default interpretation of absent legacy basis, never exclusive. `other` preserves unsupported supplied wording in evidence and remains noncomparable even when two records both say other. Do not add an exemption classification or infer an exemption from a supplier phrase. Inclusive/exclusive are operator-recorded descriptions of evidence, not a tax conclusion.

Use closed-schema validation for every nested object. Reject unknown keys, malformed values, duplicate stable IDs, negative/nonfinite money, booleans posing as numbers, fractional quantity, broken required references, invalid dates, invalid Unicode and exceeded bounds before mutation. Reuse the existing money/quantity rules and campaign size budgets. Bound every evidence list and text field; proposed initial limits are two snapshots per evidence slot and 4,000 characters per quote, within the existing aggregate limits. Avoid copying whole unlimited source documents into each line.

Drafts must remain saveable with null amount, unknown basis or incomplete evidence. An explicit review flag is usable only when its required amount/basis/evidence/rationale and current context are available. A complete or nonblank draft must not automatically become reviewed. A source pointer is not a substitute for a captured evidence snapshot. Removing a linked source must preserve captured wording; require explicit detachment or another controlled resolution of the link rather than silently dropping evidence.

Applicant GST status is optional factual context with evidence. It must not select an application basis or perform a calculation. If the operator applies a conditional instruction, capture their stated context/rationale and exact instruction together; the software does not interpret the policy condition. Changing the named applicant or relevant status/context invalidates the review that depended on it.

## Review fingerprint and stale state

The fingerprint establishes that the currently displayed inputs match the operator-recorded review. It does not authenticate a person, verify a supplier, prove the interpretation of official wording or establish tax treatment. Imported review metadata retains its provenance as recorded/imported work.

Define a versioned canonical context format, for example `sinter-application-budget-review-context/v1`. Compute SHA-256 over canonical JSON of already admitted values: sorted object keys, fixed separators, UTF-8, canonical money strings and exact retained evidence wording. No Unicode normalization or whitespace replacement in quoted references or evidence is allowed. Python and JavaScript must agree through shared fixtures.

The route context includes the named route and applicant, the entered ceiling and denomination, application-required basis and evidence, ceiling basis and evidence, applicant context and any current retained source records whose identity/content the review relies on. The row context includes its stable ID, original five fields, quoted basis/evidence, application amount/basis/evidence/rationale and the semantic route context. A route review must itself be current before a row is admitted to a comparison.

Exclude the review's own hash, review flag and review timestamp from its fingerprint to avoid recursion. Exclude incidental database campaign ID, revision number and unrelated presentation state: restoring an unchanged backup into a fresh campaign should not alter its semantic inputs. Row ordering does not change a row fingerprint; duplicate row identities are rejected. Route references currently use names, so changing a route name conservatively invalidates relevant reviews unless a later separately tested stable route identity design proves preservation.

States should distinguish `draft`, `reviewed_current`, `reviewed_stale` and `unavailable`. Structural invalidity refuses admission; incomplete or stale but structurally valid work remains retained. A mismatch must never be repaired by silently replacing the recorded hash with the current one. Preserve prior application amount, rationale, timestamp and evidence as earlier work and exclude it from the qualified total until the explicit re-review action.

Edits to quote amount/reference, quantity, row item/identity, allocation, quoted basis/evidence, application amount/basis/evidence/rationale, applicant context or relevant route requirement/ceiling evidence invalidate the dependent review. Changing a retained source after review must be detectable and must not refresh the captured wording. Unrelated campaign revisions or display filters must not falsely create a new review or needlessly erase one.

A backend helper should compute/return the current canonical context and hash for the explicit review action. The UI should show that context before the action. Normal save verifies retained bindings and derives current/stale status. Caller-provided metadata is an operator assertion, not cryptographic certification. Request overlap, asynchronous preparation and failed save must not apply a review to newer inputs or overwrite the previous snapshot.

## Totals and admitted comparisons

Maintain two distinct summaries:

- **Quoted summary:** exact quoted unit costs times quantity, known subtotal, unknown line count, active/historical coverage, basis caveat. Never an application total.
- **Application summary:** manually recorded reviewed line amounts, current review coverage, unsupported/stale reasons, declared common basis and allocation status. Do not multiply these line amounts by quantity again.

Initially admit a numerical application-versus-ceiling comparison only when all contributing route lines have current explicit reviews, all line amounts are known, allocation is explicit, all application bases equal the supported basis required for the application and the reviewed ceiling basis, and the existing denomination policy admits an entered AUD cash ceiling. The route requirement/ceiling review must be current and have retained evidence. Historical/inactive rows are excluded from current totals and current readiness counts. Explicit zero is valid recorded money; no rows is not a complete zero budget.

Missing, stale, mixed, unknown or other basis, foreign/unconfirmed currency, non-cash routes, missing ceiling or unresolved allocation means unsupported comparison, with explicit reasons. If active unallocated costs could be relevant, the initial design must hold a full application comparison until the operator resolves their allocation; it must not silently assume they are excluded. Preserve known partial subtotals in clearly labeled buckets. Do not aggregate reviewed amounts with unlike bases into one application amount. Do not claim a partial subtotal is under the ceiling.

The conservative initial version requires a complete supported application total for either true or false `over_ceiling`. A separately specified later feature could show a supported lower-bound subtotal exceeding a compatible ceiling, but that would remain a bounded arithmetic observation with incomplete-total wording. It must not slip into this implementation implicitly.

The comparison is of entered reviewed values only. It must not be labeled eligible cost, correct GST, approved budget, grant request, final application, tax entitlement or readiness to submit. No basis conversion, tax rate, exemption determination, input-credit computation, formula or rounding policy is introduced.

## Typed fictional examples

The examples are proposed domain records, not accepted v1 payloads. Current v1 admission should refuse them. The examples deliberately supply application amounts independently; no relationship between quote and application amount is calculated.

An example quoted row keeps its original five fields and an unknown application draft:

```json
{
  "id": "11111111111111111111111111111111",
  "item": "Fictional venue equipment",
  "opportunity": "Fictional Lantern round",
  "quantity": 1,
  "unit_cost": "110.00",
  "quote_reference": "Fictional supplier Q-01: AUD 110.00 including GST. Exact supplied reference retained.",
  "quoted_basis": "gst_inclusive",
  "quoted_basis_evidence": [{
    "source_id": null,
    "source_title": "Fictional Q-01",
    "source_url": "",
    "source_quote": "AUD 110.00 including GST",
    "checked_at": "2026-10-01"
  }],
  "application_review": {
    "amount": null,
    "basis": "unknown",
    "evidence": [],
    "rationale": "",
    "reviewed": false,
    "reviewed_at": null,
    "context_sha256": null
  }
}
```

A separately entered fictional application review draft is:

```json
{
  "amount": "85.00",
  "basis": "gst_exclusive",
  "evidence": [{
    "source_id": null,
    "source_title": "Fictional operator-reviewed worksheet W-01",
    "source_url": "",
    "source_quote": "Application line amount recorded in this fictional worksheet: AUD 85.00 excluding GST.",
    "checked_at": "2026-10-01"
  }],
  "rationale": "Manually entered from fictional worksheet W-01; no conversion performed by Sinter.",
  "reviewed": false,
  "reviewed_at": null,
  "context_sha256": null
}
```

The route review draft separately captures the application and ceiling bases:

```json
{
  "required_application_basis": "gst_exclusive",
  "application_evidence": [{"source_id": null, "source_title": "Fictional form instruction", "source_url": "", "source_quote": "For this fictional example only, enter application line amounts excluding GST.", "checked_at": "2026-10-01"}],
  "ceiling_basis": "gst_exclusive",
  "ceiling_evidence": [{"source_id": null, "source_title": "Fictional ceiling instruction", "source_url": "", "source_quote": "For this fictional example only, the AUD 200.00 ceiling is stated excluding GST.", "checked_at": "2026-10-01"}],
  "applicant_context": {"applicant": "Fictional Lantern association", "gst_status": "unknown", "evidence": [], "rationale": "No applicant tax status inferred from the quote."},
  "rationale": "The separately entered fictional instructions state the two bases. Their real-world truth is not established.",
  "reviewed": false,
  "reviewed_at": null,
  "context_sha256": null
}
```

After an explicit hypothetical review action computes and captures matching fingerprints, two independently entered application line amounts of 85.00 and 90.00 on the supported common basis total 175.00. The quoted originals can still total 210.00 on mixed bases. Only the complete, current application total may then be numerically compared to the separately reviewed AUD 200.00 ceiling. This does not prove that any of the fictional amounts are correct or eligible.

Expected state transitions:

| Fixture | Quoted observation | Application state | Comparison |
| --- | --- | --- | --- |
| Legacy 110.00 inclusive + 100.00 exclusive | Raw known subtotal 210.00; basis unreviewed | No application amounts | Unsupported |
| Same plus production unit cost null | Quoted total incomplete; raw subtotal retained | Incomplete | Unsupported |
| Separately entered 85.00 + 90.00, drafts | Quoted originals unchanged | Draft amounts retained | Unsupported |
| Same after current explicit route and row reviews | Quoted originals unchanged | Complete reviewed total 175.00 on one supported basis | Entered total does not exceed entered compatible 200.00 ceiling; no eligibility verdict |
| Quantity/reference/applicant/terms changed afterward | Updated quote inputs retained; prior evidence kept | Earlier review stale | Unsupported until re-review |
| Application amount null, basis other or currency USD | Preserve entered values | Incomplete/unsupported | Unsupported; no conversion |

## Migration and older-client refusal

Keep legacy v1 documents readable and saveable under their existing contract. Upgrade only a deliberately selected working copy; preserve every existing value and create stable row identities for the upgraded copy. No startup migration, silent schema change, rewrite of old checkpoints or global registration default is permitted. Unknown remains unknown. Preserve v1 saved IDs/revisions and prior backups; a restored copy gets a new campaign identity without overwriting its saved original.

Introduce an explicit campaign-preservation capability, analogous to `X-Sinter-Casebook-Schema` and `Runtime.call(..., casebook_schema=...)`. A proposed HTTP declaration is exactly one `X-Sinter-Campaign-Schema: sinter-campaign/v2` header. This is a preservation capability, not authorization or a provider header.

Guard v2 reads, preparation/validation, imports and writes. On an update, inspect both the submitted document and the existing saved record before mutation. A cached caller must not overwrite a stored v2 campaign by submitting stripped v1 data, even with a current revision. Missing, incorrect or duplicate capability values fail closed. Keep the normal revision guard as a separate requirement. Reader refusal should explain that the interface cannot preserve the review data and direct the user to reload/open the current supported workflow; originals remain retained.

Do not put the capability automatically into the shared API helper: that would let an older cached campaign page accidentally claim support. Only the new campaign-aware caller opts in. Existing v1 clients continue to work on v1 campaigns. A direct v2-to-v1 update is refused. Clearing an application review should keep v2 unless a separately designed explicit compatible-copy export is requested; no silent lossy downgrade.

Older server/source versions already reject unsupported schemas/keys. Prove that attempted v2 import/save into a copied older workspace fails without mutating records or IDs; do not promise an older executable can read a database containing v2. Tests must distinguish controlled refusal from destructive normalization or unsupported database behavior.

## Report, backup, CLI, Python and native boundaries

`CampaignStore.get` currently normalizes documents on read without rewriting database originals. Preserve that read-only behavior. Current campaign backup import obtains a document through `campaigns.prepare`, whose shareable report projection redacts some content. For v2, prefer a dedicated lossless validation result for import; a shareable report is not a canonical restoration payload. Cancel, invalid input and failed import must retain the exact previous editor, captured backup and pending work.

`saved_report_view` validates an embedded historical campaign and regenerates derived summaries at read time. Disk originals and user edits must remain untouched. Never consult the current saved campaign to qualify an old report. Old inputs remain historical; no new application amounts or review facts can be invented. Any updated policy view must say what it is. Carry the basis caveat in the decision brief itself because Word exports its document text, not the omitted source register. Preserve edited report text as authored; a surrounding warning may explain historical/unreviewed basis without altering that text.

Gate nested v2 campaigns in report read/import/save boundaries where the caller cannot preserve their meaning. Saved-report projection must explicitly carry the recognized review fields or fail with supported-workflow guidance; it must not silently omit them, treat them as v1 or return a fabricated qualified summary. Existing safe report filtering, including held/historical answers, must remain enforced.

The current CLI's dedicated import/export kinds are casebook and report, not campaign. Campaign source operations exist through `run campaigns.*`. Do not describe a nonexistent campaign import command. Add an explicit `campaign_schema` capability to Python/runtime capture and opt in from tested current lossless CLI paths, including nested campaign-report handling. Older Python callers fail closed on v2. Machine errors remain one structured envelope with the established nonzero exit contract, and JSON/UTF-8 file exports preserve originals. General CLI campaign import/export is a separately explicit implementation choice, not an existing feature.

The native Tk workflow currently has no campaign Budget editor and no campaign Word workflow proven. Do not add or claim those interfaces incidentally. When native report history/import encounters a v2 campaign review it cannot safely render or preserve, show clear guidance to use the supported current campaign workbench or CLI, retain the original, and avoid a traceback, coercion or editable downgraded copy. Listing safe identity metadata can remain available. Native qualification is separate from web/source qualification.

No new budget evidence should be automatically included in assistant/model context or transmitted. Existing assistant context is explicitly selected and previewed. Any later provider feature needs its own exact preview/consent design and tests; it is outside this local budget implementation.

## Module and UI boundaries

`campaign_budget.py` should own closed admission of new records, canonical contexts/fingerprints, quoted/application summaries and explicit unsupported reasons. A matching browser module should use integer cents and shared semantic fixtures. `campaigns.py` should orchestrate overall document validation, persistence and report rendering. `campaign_currency.py` owns denomination only; passing its currency gate alone never establishes application comparability.

Show the quote amount, quantity, exact reference and recorded basis beside the separate application line amount. Display the application-required basis and ceiling evidence before the explicit review action. Default to unknown, and never preselect a reviewed status or copy a quoted amount into the application amount as if reviewed. Keep drafts available through navigation, asynchronous operations, failed requests, reopen and backup restoration. Make stale review reasons visible and re-review deliberate. Review controls must work with keyboard and phone layouts, avoid inaccessible native prompts and lock/guard overlapping transitions.

An explicit zero remains distinguishable from blank; no costs is distinguishable from a complete zero-cost set. Historical rows remain available but are visibly excluded from current arithmetic. Current basis, currency and allocation problems get separate reasons rather than a single misleading completeness badge. Never use a whole-product score or installed claim to substitute for workflow evidence.

## Open implementation and testing checklist

All items below remain open for v2. Passing the quoted-summary checkpoint does not close them.

- [ ] Finalize the inline versus worksheet choice, exact typed field names, bounds and schema/version policy; keep all quote/application/evidence separations.
- [ ] Implement pure backend quote/application admission and summary module; do not add tax rules or conversions.
- [ ] Implement stable budget-row identities without rewriting legacy v1 reads or checkpoints.
- [ ] Implement route basis/ceiling evidence and applicant context without inferring registration or policy outcomes.
- [ ] Implement versioned canonical context/fingerprint parity fixtures, explicit review action, stale derivation and retained previous work.
- [ ] Implement capability-aware campaign readers/writers and inspect stored schema before an update; preserve revision checks.
- [ ] Implement lossless import validation and controlled older-server/older-client refusal before mutation.
- [ ] Implement live quote/application entry, deliberate review, supported comparison and visible unsupported reasons; keep drafts/unknowns usable.
- [ ] Implement consistent decision brief, Word text, full pack, report JSON and reopened historical policy views without rewriting originals or user edits.
- [ ] Implement Python/runtime and existing CLI campaign-operation capability propagation; explicitly scope any new dedicated import/export command.
- [ ] Implement native unsupported-workflow guidance and safe nested report handling; do not claim a native budget editor.
- [ ] Verify fictional mixed-basis 110.00 + 100.00 retains raw 210.00 and cannot qualify application comparison.
- [ ] Verify unknown production line, no rows, explicit zero, unallocated work, inactive routes and current/historical totals/counts.
- [ ] Verify separately entered line totals are not recomputed from quoted unit price or multiplied twice by quantity.
- [ ] Verify draft, missing evidence, unsupported basis, non-AUD/unconfirmed denomination, non-cash routes and missing ceilings never give an under-cap/application-ready conclusion.
- [ ] Verify quote/reference/quantity/allocation/application/applicant/requirement/ceiling/source changes invalidate dependent review while retaining snapshots and amounts.
- [ ] Verify reordered rows keep identity, duplicate IDs refuse, unrelated revisions/display state do not invent or erase reviews, and unchanged semantic backup restoration is coherent.
- [ ] Verify malformed schema/money/quantity/evidence/date/Unicode, unknown keys and aggregate bounds refuse before mutation.
- [ ] Verify copied v1 workspace values, IDs, revisions, backups, checkpoints, raw database report payloads and authored report edits remain intact.
- [ ] Verify v2 save/reopen/restore, current-versus-stale review state, report history, failed/cancelled import and late asynchronous responses.
- [ ] Verify missing/wrong/duplicate capability, cached old page, stripped-v1 update of stored v2, older Python caller and attempted older-version import all fail closed.
- [ ] Verify browser/backend integer-cents/Decimal parity, brief/Word/full-pack/CLI wording and comparison-reason parity.
- [ ] Verify keyboard/phone review interactions and unsupported native guidance in bounded local fixtures.
- [ ] Run relevant focused regressions, full existing suites, schema/provenance and public-boundary checks on a frozen combined source; retain exact receipt hashes.
- [ ] Keep source, frozen-binary, installed-platform and real-operator qualifications distinct. Installed/release claims require separately completed evidence.

## Hard failure gates

Do not accept the usable v2 workflow if any of these occurs:

1. Unlike or unknown quoted bases silently become a qualified application total or ceiling conclusion.
2. A quote amount, null/unknown, explicit zero, reference, historical row, checkpoint, backup, raw saved report or user-authored report edit is rewritten or lost.
3. Editing a relevant input leaves its earlier review current, or a mismatched fingerprint is silently refreshed.
4. An older interface can receive v2 as editable v1 or overwrite a saved v2 record while omitting its review fields.
5. Partial, unallocated, stale or unsupported amounts produce an under-cap, eligible-cost or application-ready result.
6. Live UI, backend, decision brief, Word, full pack, historical report view or CLI disagree about monetary meaning, totals or unsupported reasons.
7. Invalid schema, duplicate identities, malformed money, broken references or exceeded bounds mutate the destination before refusal.
8. Any input basis or applicant status is inferred from free text, a conversion/rate/credit rule is added, or evidence is transmitted without a separately authorized explicit flow.
9. A source or browser pass is relabeled as installed/native/full-product qualification, or the quoted-summary milestone is treated as completion of the application-budget objective.

Review and implementation remain open. This artifact is an architecture handoff for subsequent work, not a shipping acceptance record.
