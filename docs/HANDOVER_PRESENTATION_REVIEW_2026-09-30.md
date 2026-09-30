# Source-only handover presentation review — 30 September 2026

This development cycle follows the published Linux `0.5.4rc1` preview. It does
not change its tag, assets or installed qualification. The improvements below
require a later source or separately qualified package.

## What changed

A dedicated presentation adapter builds the handover Document from admitted
questions and selected source passages. It puts a question-specific checklist
first, explicitly labels wording matches as requiring review and keeps unmatched
questions unknown. It assigns no owner, date or real-world answer. The Audit,
original inputs, source identities, exact excerpts, retrieval coverage and review
status retain their prior behavior.

Source headings and supported emphasis are presented more readably. A complete,
unambiguous CSV with recognised column labels becomes a quoted table. Blank cells
have an explicit explanation; quoted records do not confirm commitments. Partial,
malformed, ambiguous or oversized tables retain literal wording. Multiline cells
use labelled records and protected literal text. Only four selected passages are
displayed as source notes, with the actual displayed/selected counts and the
Evidence-only remainder stated. This is not a complete source review.

Document citations now resolve the report's admitted IDs rather than assuming
a sixteen-character hash. Links open the exact local source in Evidence; absent
originals and unknown IDs stay plain text. Quoted source text, code and existing
links are excluded. The matcher is compiled once per article and reusable across
paragraphs. Successful saving clears an obsolete editor reminder only if no newer
edits remain; delayed saves continue to protect newer work.

Campaign readiness instructions now separate missing-field labels from complete
date and source-snapshot sentences. An independent comparison of 2,688 state
combinations found the decision metadata unchanged.

## Adversarial findings and evidence

Independent review found malformed multiline CSV headers being promoted to table
headings and multiline values being interpreted as lists or horizontal rules.
Root review then found the same numbering issue in ordinary source notes; the
critic extended that probe to inline code and indented rules. These findings were
treated as wording-fidelity defects, rather than accepted formatting differences.
Original evidence was retained throughout.

The final formatter SHA-256 is
`329f7eabde2cef7cf72d08208aa5da3d94b698a66ab4d55d9c62fc7b76970366`.
Full Python validation passed **1,613 tests**, with five Windows launcher cases
skipped on this Linux host. JavaScript passed **126 tests**. The formatter has
73 focused cases; independent review passed 135 adjacent/focused tests and ten
paired actual Markdown DOM/Word XML probes before the last two regression
additions. Three separate form-to-preparation-to-Word-download journeys confirmed
the bare, inline-code and indented source-marker fixes.

Actual garden browser checks cover question-specific unknowns, table presentation,
clicking a Document citation into the exact original, a real Word download and
save/reopen/restore behavior. The downloaded Word file is retained locally for
rendered inspection. Thirteen garden journeys, nine report recovery journeys and
the existing casebook browser suite passed. Report recovery checks cover citations,
save feedback, failed saves and newer edits during delayed saves.

Retained receipts include `browser-artifacts/garden-practice-summary.json`,
`report-recovery-summary.json`, `campaign-readiness-prose/`,
`citation-save-independent-review/` and the human screenshots
`handover-human-checklist.jpg`, `handover-human-table.jpg` and
`handover-human-saved.jpg`. Earlier receipts retain their earlier source hashes;
later corrections do not turn them into evidence for a different implementation.
All workspaces were fictional and isolated. No hosted model request was made.

Additional durable receipts are in `browser-artifacts/handover-adversarial-review/`
and `handover-operator-critique/`. The real garden Word download was rendered with
LibreOffice 24.2 to a three-page A4 PDF, retained with page images in
`handover-rendered/`. Visual inspection confirmed long repeated IDs and a table
split over two pages with its header repeated. These remain quality issues rather
than being hidden by XML validation.

The source-bound warm local benchmark measured garden preparation at a median
**0.92 ms** and a synthetic 300-document, 1,980,000-character workload at
**168.48 ms**. Its actual coverage remains explicit: selected wording is not an
exhaustive review. `self-audit-artifacts/offline-benchmark-handover-final.json`
binds retrieval and presentation code hashes and proves zero transport calls.
These measurements do not establish browser responsiveness or model quality.

## Quality limits

The provisional handover-slice assessment is UX **7**, functionality **8** within
its source-only contract, exported-document aesthetics **6.5**. That assessment
used source and Word XML; it is not a whole-product rating or visual acceptance.
The next operator critic observed repeated long IDs in Word and competing passage
and source numbering in the interface. Readable passage references with an exact
identity key are a concrete next presentation improvement.

Lexical matching can retrieve irrelevant wording. In the fictional date question,
generic shared words also selected an unrelated funding passage. A list of
citations therefore does not establish answers. Human-recorded responses,
follow-up decisions and their exact supporting wording need a separate design
with save, source-change and review invalidation semantics. They are not supplied
by this formatting cycle. Repeated campaign qualifications also remain a
readability issue. None of these findings supports a 10/10 claim.

A separate practical operator critic inspected the stable interface and actual
Word downloads, scoring this flow UX **6.5**, functionality **7.5**, aesthetics
**6.5**. Root's rendered inspection supports its readability concerns. This
stricter assessment is retained alongside the implementation-contract assessment;
passing regressions does not resolve the practical next-cycle work.
