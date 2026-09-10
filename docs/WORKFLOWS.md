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

Import TXT, JSON, SRT or VTT, or use [local audio transcription](TRANSCRIPTION.md). Confirm speaker labels manually. Recognition flags remain visible in minutes, and corrections keep the original text plus the human reviewer's reason.

Action/decision keywords identify **candidates for review**, not actual resolutions. Check whether a statement was a proposal, a negated action, someone else's claim or a real commitment. Do not infer attendance, owners, dates or voting outcomes from fluency.

## Generative templates

**Explore Fracture** is deliberately separate from the evidence workbench. It includes ordinary chat and ten built-in templates: chat, code review, research, summarise, explain, custom, enquiry letter, agenda item, action register and grant preparation checklist.

The community templates use three passes: extract supplied context, draft, then check the draft against that original context. They preserve prior-step history and instruct the model to leave unknowns explicit. Their final self-check is **not independent verification**. Check every substantive statement and citation before using model-generated prose.

A custom template cannot turn an unverified generative output into a verified report just by describing it as one. See [the developer guide](DEVELOPMENT.md) for the supported JSON/YAML format.

## Saving and sharing

Save explicitly in **My workspace**, download Markdown for editing, or export the JSON evidence pack. Browser printing also supports Save as PDF through your browser. Sinter does not upload saved reports to a cloud account, send official communications or approve records.

Data is stored without encryption in `~/.sinter/workspace.sqlite3` (or your `SINTER_DATA_DIR`). Back it up responsibly. Unsaved inputs are retained only during this browser session; reload or closing the app can lose them. Returning to Overview lets you continue an unsaved real project without erasing its inputs.
