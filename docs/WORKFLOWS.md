# From context to something useful

[Back to Sinter](../README.md)

## Funding research

Name the project, describe the organisation and add known context. Enter the exact public search query: this is what leaves your computer, not the whole form. Search results are leads and excerpts, not confirmed open grants.

Add exact official guideline text as references, including exclusions. In the report's requirement checker, use that wording and confirm that you checked the source is official, current and correctly interpreted. The comparator can check organisation type, location and numeric budget conditions; it does not understand every grant rule. Missing or unconfirmed values remain **unknown**, and overall eligibility always needs review.

Use **Search watches** for hourly, daily or weekly checks. Watches resume overdue work after restart and distinguish new, changed and not-returned results. Not appearing in a search is not proof a grant closed. The app must remain running. Calendar exports provide review reminders and optional human-confirmed closing dates; verify time zones and closing times separately. Reimporting does not establish a live calendar feed.

## Enquiry letters, briefs and agenda items

Choose the output type before adding notes: **Enquiry letter**, **Briefing note** or **Agenda item for discussion**. Recipient, organisation and sign-off are optional. Missing details stay as placeholders instead of being invented.

Add your actual questions, one per line, and paste reference text or import TXT/Markdown context. The report includes a question-to-source guide. Its keyword matches are navigation aids, **not answers or proof of support**. No match is likewise not proof that the full source lacks an answer.

An agenda item is a proposal for discussion, never an agreed motion. An enquiry asks for clarification rather than promoting unverified allegations to fact. All formats retain source snapshots and review boundaries.

Optional Fracture ranking may reorder existing excerpt IDs. It cannot add factual prose into these source-only reports. Leave it off for confidential material: ranking sends a small excerpt set and the project question to the configured API.

## Meeting review

Import TXT, JSON, SRT or VTT, or use [local audio transcription](TRANSCRIPTION.md) in a speech-enabled source installation. Confirm speaker labels manually. Recognition flags remain visible in minutes, and corrections keep the original text plus the human reviewer's reason.

Action/decision keywords identify **candidates for review**, not actual resolutions. Check whether a statement was a proposal, a negated action, someone else's claim or a real commitment. Do not infer attendance, owners, dates or voting outcomes from fluency.

## Generative templates

**Explore Fracture** is deliberately separate from the evidence workbench. It includes chat, code review, research, summarise, explain, custom prompts and eight community recipes: enquiry letter, agenda item, action register, grant preparation, volunteer handover, event plan, newsletter and consultation questions.

The community templates use three passes: extract supplied context, draft, then check the draft against that original context. They preserve prior-step history and instruct the model to leave unknowns explicit. Their final self-check is **not independent verification**. Check every substantive statement and citation before using model-generated prose.

A custom template cannot turn an unverified generative output into a verified report just by describing it as one. See [the developer guide](DEVELOPMENT.md) for the supported JSON/YAML format.

## Saving and sharing

Save explicitly in **My workspace**, download Markdown for editing, or export the JSON evidence pack. Browser printing also supports Save as PDF through your browser. Sinter does not upload saved reports to a cloud account, send official communications or approve records.

Data is stored without encryption in `~/.sinter/workspace.sqlite3` (or your `SINTER_DATA_DIR`). Back it up responsibly. Unsaved inputs are retained only during this browser session; reload or closing the app can lose them. Returning to Overview lets you continue an unsaved real project without erasing its inputs.

## Community tools and knowledge

**Community tools** prepares action lists from details you enter. Keep unassigned owners and unconfirmed dates blank, export CSV/calendar/JSON or save the result locally. A separate line-oriented comparison shows changed wording; line-ending style and final-newline differences are ignored.

**Knowledge atlases** can use an exported RKC bundle without installing RKC. A running local RKC provides richer context; an explicitly selected executable can compile selected files. Model drafting requires separate transfer consent and never changes canonical atlas evidence. See [the atlas guide](ATLAS.md).

## Funding requirements in a JSON project

When preparing a project for `sinter workbench`, identify each requirement's source
by its exact `source_title`. You do not need to calculate a source hash. Titles
must match the supplied source title exactly, including capitalisation and spacing,
and identify one source. If two sources have the same title, give them distinct
titles or use the existing `source_id` from a report instead. When both selectors
are supplied, they must identify the same source; ambiguous or conflicting selectors
are rejected. Report checks retain the resolved source ID and title for tracing.

This fictional example runs offline. Save it as `funding.json` and run
`sinter workbench funding.json -o funding-report.json`:

```json
{
  "workflow": "grants",
  "title": "Fictional community project budget check",
  "use_search": false,
  "use_model": false,
  "sources": [
    {
      "title": "Fictional funder budget guideline",
      "kind": "reference_excerpt",
      "url": "https://example.org/fictional-guidelines",
      "content": "For this fictional example, project budgets must not exceed $5,000."
    }
  ],
  "profile": {"budget": 4000},
  "criteria": [
    {
      "field": "budget",
      "operator": "maximum",
      "value": 5000,
      "source_title": "Fictional funder budget guideline",
      "quote": "For this fictional example, project budgets must not exceed $5,000.",
      "confirmed": false
    }
  ]
}
```

The example remains **unknown** because `confirmed` is false. For a real project,
replace the fictional source and quotation with current official guideline text.
Only set `confirmed` to true after a person checks its authority, currency and
interpretation. Title selection does not relax the exact-quotation check or make
notes, transcripts or examples authoritative. A matching comparison is still a
check of one entered requirement, never an eligibility determination.
