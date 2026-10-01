# From context to something useful

[Back to Sinter](../README.md)

## Funding research

Name the project, describe the organisation and add known context. Enter the exact public search query: this is what leaves your computer, not the whole form. Search results are leads and excerpts, not confirmed open grants.

Add exact official guideline text as references, including exclusions. In the report's requirement checker, use that wording and confirm that you checked the source is official, current and correctly interpreted. The comparator can check organisation type, location and numeric budget conditions; it does not understand every grant rule. Missing or unconfirmed values remain **unknown**, and overall eligibility always needs review.

Use **Search watches** for hourly, daily or weekly checks. Watches resume overdue work after restart and distinguish new, changed and not-returned results. Not appearing in a search is not proof a grant closed. The app must remain running. Calendar exports provide review reminders and optional human-confirmed closing dates; verify time zones and closing times separately. Reimporting does not establish a live calendar feed.

## Funding campaigns

**Funding campaigns** keep several opportunities, application answers, quotes and
next actions in one local record. Statuses, costs and requirement checks are
entered by a person. A requirement is only treated as checked when its status,
evidence, source link, source wording and check date are all present.

The recorded quoted subtotal is incomplete while any row lacks a unit cost.
Missing quote references are listed separately; priced rows do not establish
reviewed or eligible application amounts. Unknowns remain visible in the prepared
brief. See [what recorded quote amounts mean](CAMPAIGN_BUDGETS.md).

Each opportunity has its own **Funding ceiling currency**. Choose AUD, USD, EUR,
GBP, NZD or CAD from the official funding terms; new opportunities start with
currency unconfirmed. For another currency, choose **Another currency · comparison
unsupported** and retain its exact name and payment conditions in the source or
project-fit notes. Sinter does not verify those terms or convert currencies.

Project costs remain explicitly **AUD**. A different, unconfirmed or unsupported
funding denomination is shown separately in the route, currency review and brief;
it is never numerically classified as within or over an AUD cost subtotal. Review
the funding terms and cost basis separately. Non-cash routes remain **No grant
cash**. Existing records without a currency retain their earlier AUD meaning;
changing that meaning requires an explicit edit. Save the campaign to retain the
choice across reopening and backup restoration. Historical reports retain their
original recorded denomination.

Linking or clearing a requirement's registered source keeps its explanatory note.
A different source clears the earlier quoted wording and resets any met/not-met
assessment to **Not checked**. Unknown and clarification states stay unresolved.
Re-read the new source, replace the excerpt and check date, and review the note
before changing the assessment. The source's recorded date remains user-entered
metadata; selecting it is not proof that you checked the quoted wording.

Save revisions on this computer, export a JSON backup, or import a backup to continue. A stale revision is rejected and leaves your unsaved edits in the editor. Sinter does not submit applications, fetch funder pages, or treat a prepared brief as approval.

In development after 0.5.4rc2, an action can be **On hold**. Use it for work that
is paused or superseded but has not been completed. Its exact task, owner and
proposed date stay recorded. Held actions appear separately and are excluded
from current next actions and calendar exports. Change the status explicitly to
**To do** to resume; existing scope and route checks still apply. Older previews
cannot open a campaign containing this status. Keep a separate backup before
changing versions; do not mark work completed merely to satisfy an older app.

The development backup controls also provide **Copy backup text**, **Refresh
backup text** and **Select backup text** under **Import or back up a campaign**.
These capture every current input, including unsaved and oversized edits, without
a server connection. Paste the complete text into a private text file to retain
it. Copying does not save the campaign or create a file. If clipboard access fails
or stalls, refresh and select the complete text for manual copying. An earlier
capture or clipboard value does not include later edits. An oversized backup
preserves those edits but still needs scope reduction before Sinter can save or
restore it; retain the full backup while making a smaller working copy.

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

Choose **Save to My workspace** to keep the report inside Sinter. The published
0.5.4rc3 preview calls the same workspace action **Save to this computer**; its
installed files have not changed. **Save Word copy on this computer** creates a
separate Word file and does not save the report in My workspace.

You can copy the readable draft, download Markdown or a portable HTML document, or export a Word file built only from the current draft text. The JSON evidence pack keeps the original model output, sources and any later edits. Browser printing also supports Save as PDF through your browser. Sinter does not upload saved reports to a cloud account, send official communications or approve records.

A download notification means Sinter requested the browser transfer. Check your
browser's downloads for the actual file. Clicking **Download Word** again with
the same applied wording reuses the prepared local file. Changed wording or a
changed title prepares a new file; edits made during preparation remain in the
editor and must be applied before downloading. No model request is repeated by
this local export action.

To keep an operator's front page separate from the supporting evidence, open
**Edit draft**, place the cursor after the front-page wording and choose **Insert
page break**. For a campaign, use **Edit decision brief**. The control retains
selected text; it does not replace it. Choose **Apply edits**, then
**Save to My workspace**. Word and printed HTML begin the following content on a new page.
Review the exported layout: Sinter does not shorten or remove evidence to make a
front page fit.

The saved Markdown keeps `<!-- sinter-page-break -->` on its own line, separated
from surrounding blocks by blank lines. This exact top-level marker is the
portable Sinter page boundary; other Markdown readers may ignore it. Markers
inside quotations, code, lists or table cells remain literal source text.
Copying readable draft text omits the page-boundary label. Original report text,
source evidence and previously saved reports remain available separately.

Complete generated passage-reference records use tighter paragraph spacing in
Word. This is a layout hint, not verification of sources or citations. All words,
identities and character ranges remain present; edited or lookalike records may
retain ordinary spacing. Check the actual exported pages before sharing them.

Development after RC3 also links generated Word handover passage labels to
included quotations and reference keys. These links help a recipient find the
supplied wording; they do not establish that it answers a question or is true.
Ambiguous or larger reference sets retain their wording without optional links.
Compact handovers identify omitted passages and ask the recipient to obtain the
originals or project backup from the sender. The published RC3 installer retains
its earlier presentation; see the [source review](WORD_HANDOVER_NAVIGATION_2026-10-01.md).

Data is stored without encryption in `~/.sinter/workspace.sqlite3` (or your `SINTER_DATA_DIR`). Back it up responsibly. Unsaved inputs are retained only during this browser session; reload or closing the app can lose them. Returning to Overview lets you continue an unsaved real project without erasing its inputs.

In a casebook, **Project save state** beside the document count describes the
project inputs. A pending source must be added or cleared before saving; it is
not silently included in the saved project. Changes after a save are labelled
unsaved. An edited report has its own **Save to My workspace** action; saving
that draft does not update the original project inputs or its revision.

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
