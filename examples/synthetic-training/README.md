# Free practice session: sources, drafts and useful unknowns

Allow about 20 minutes. These four exercises are included under Sinter's
Apache-2.0 licence. Every person, organisation, programme and document is
invented for this session. No real grant, venue, booking or customer is described.
No purchase, account or AI connection is needed.

Run the commands from the Sinter source directory with Python 3.10 or later:

```text
python start.py workbench examples/synthetic-training/research.json -o fictional-research.json
python start.py workbench examples/synthetic-training/grants.json -o fictional-grants.json
python start.py workbench examples/synthetic-training/brief.json -o fictional-brief.json
python start.py workbench examples/synthetic-training/meeting.json -o fictional-meeting.json
```

Use distinct output filenames to retain previous work. These commands produce
JSON reports. Open them in a text editor and inspect `document_markdown` for the
draft, `markdown` for the review pack, and `sources` for the original material.
For a readable Markdown review pack, repeat a command with a new `.md` output
filename. The original exercise JSON remains unchanged.

Keep the JSON output and original inputs together: `sources` retains full source
text. Markdown reports contain selected passages and a source register; they
are not a complete source backup. Read the originals even if a report says the
evidence pack retains them.

All four inputs set `demo: true`, `use_search: false` and `use_model: false`.
Sinter rejects a demo input that enables either remote option. Keep those flags
for this session. Source-only work runs locally; connecting an AI provider is a
separate exercise requiring its own destination, authentication, cost and payload
review.

## 1. Inspect the research evidence

Read `research.json` before its report. The entrance has not been measured, two
chairs were recorded, seating needs still need review, and no opening time was
agreed. Compare each selected quote with the original source and its character
offsets. The source register includes content hashes.

The checked run selected five exact excerpts across two sources. Matching text
establishes where the quote came from. It does not establish that a source is
true, authoritative, current or sufficient to answer the question.

Practice: change the question in a separate copy, run it to a new output, and
inspect which evidence appears. Keep unanswered questions visible. Do not infer
an entrance width, agreed opening time or access suitability.

## 2. Keep the funding result unresolved

The fictional budget is 120 practice units and the fictional maximum is 200.
The exercise deliberately includes `confirmed: true` on the entered comparison.
Its source is still a `sample`, so the result remains `unknown` and
`review_required`. A checkbox and a numerical match cannot make a fictional
programme an official funding opportunity.

Practice: identify what is missing before any real application: current official
guidelines, applicant conditions, exclusions, costs and the application window.
No reminder or application should be created from this practice material.

## 3. Review the enquiry before use

The brief asks about access, seating, cost and booking authority. It retains the
statement that no booking or spending was approved in an explicit opening
paragraph for the recipient. The preparation notes remain in the evidence pack
and do not appear in the enquiry letter. Read each question against the notes
and source; distinguish an enquiry from a confirmed arrangement.

Practice: edit a separate input copy to add one invented question, regenerate
the report, then compare the new output with the previous one. Nothing in this
exercise sends the enquiry.

## 4. Preserve the original meeting record

The first fictional turn contains a deliberate transcription error: “We did
approve the booking.” Its reviewed correction adds “not”. Inspect `segments`
and `corrections`: the original text, replacement and reason all remain. The
draft document uses the corrected wording and preserves “No vote was taken
today.” Robin and Sky are explicitly fictional labels supplied by the exercise.
Inspect every original turn and correction, even when it is grouped under
“Other discussion” or absent from the automatically detected review candidates.
Those categories do not establish the importance or completeness of a statement.

Practice: locate the statement about requesting an estimate. It is an action
mentioned in the record, not proof of a completed task, accepted cost or booking.
Keep minutes as a draft until the appropriate human review is complete.

## Reusable operating procedure

1. Start with the smallest useful set of authorised source documents. Preserve
   originals; write reports and edits to separate files.
2. Check the source's identity, date, scope and missing information before
   interpreting a quote. Review offsets and surrounding text.
3. Prepare a source-only draft first. Retain questions, negation, uncertainty and
   correction history. Confirm owners, dates and decisions with people.
4. If optional assistance is useful, inspect the exact proposed destination and
   payload first. Resolve provider permission and cost before transmitting it.
   An AI model may rank existing excerpts in this workflow; a model suggestion
   does not create evidence or establish a grant condition.
5. Review the draft, export a separate backup, and record what actually happened.
   Sending, booking, applying and approving are distinct human actions.

## What has been checked

On 30 September 2026, all four CLI commands completed on Linux with outbound
socket connections blocked and an empty temporary Sinter data directory. The
research, funding and enquiry runs retained 5, 2 and 3 exact excerpts respectively;
the minutes retained the original and correction. All outputs stayed drafts.
Six regression tests also checked the exercises and mocked assistance: valid
existing IDs can be reordered; an invented evidence ID is discarded and local
selection retained. No remote model produced these training outputs.

These checks establish local traceability and fallback behaviour. They do not
qualify live model accuracy, a customer deployment, Windows/macOS installers or
funding eligibility. See the [connector readiness record](../../docs/CONNECTOR_READINESS_2026-09-30.md)
for connection status and the proposed synthetic remote test.
