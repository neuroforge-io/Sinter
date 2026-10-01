# Community casebooks

A casebook brings fragmented information together without turning guesses into facts.
Use it for a committee handover, a venue enquiry, a policy question, a school project,
or the history behind a proposal. Original wording stays available.

## Start with one question

Open **Community casebooks**, choose the fictional community example, and prepare a
source-only report. The example deliberately contains a provisional booking, an
unassigned roster and an unanswered insurance question. Nothing is a real offer or
commitment. No model or network connection is needed.

For real work, name the project, write up to 20 questions (one per line), and add
notes or UTF-8 files. Give sources identifiable titles; dates and URLs are optional.
A URL is a reference, not an instruction to fetch the page. PDF/DOCX extraction is
not included. Copy the relevant original text or use a trusted text export.

Choose a briefing note, enquiry letter, agenda item or volunteer handover.
Sinter indexes the admitted text, retrieves exact passages, and shows questions
without wording matches and documents not represented in the selection. A lexical
match **does not mean a question was answered**, and no match does not prove absence.
Read the originals for qualifications, negation, contradictions and chronology.

## Choose sources for each question in development

The unreleased development version offers **Choose sources for each question**.
Save newly added sources first to give them stable references, then choose
**Choose sources** for a question. Choosing no sources deliberately leaves it
without evidence; Sinter does not substitute other documents. **All supplied
sources** restores the unscoped search for that question.

These choices bound wording searches and optional draft context. They do not
select exact passages, answer questions or establish a complete source review.
Inspect the retrieved wording and its original context. All originals stay in the
project, including sources not represented in the report. Changed questions,
question positions and removed sources require reviewing the affected choices
before saving or preparing again. Earlier reports keep their earlier evidence.

Explicit choices use casebook v2 and separate local storage. Older previews cannot
show these projects or restore their backups. Keep an unchanged workspace copy
before switching versions; return to a supporting version for newer work. These
controls are not in the published 0.5.4rc2 installers.

An older open page must not erase or widen these choices. The current server
refuses scoped projects and backups from interfaces that cannot preserve them.
Reload the current web workbench before opening newer work; the native source
window cannot edit these choices yet. Restoring a scoped backup still opens an
unsaved copy. Clearing every choice is deliberate and must be saved successfully
before the project returns to the older unscoped format. A conflict or refusal
keeps the saved source choices and your working copy intact.

Within a question's choices, **Inspect this local source** opens the retained original text
without selecting it or changing the project. Use its stable reference to tell
apart sources with the same title, date or link.

## Choose what a source-only handover carries

The default **Compact notes** handover quotes up to four selected passages. Its
reference key identifies later passages, which remain in Sinter's Evidence view.
This format is useful for a short checklist, but it does not carry every selected
passage into Word.

For a reader who needs the selected wording without Sinter, choose **Include every
selected passage · with appendix** under **Evidence in source-only handover**.
Prepare the report again. The first four passages stay in the main notes; later
selected passages appear in its appendix with supplied source titles, links and
date labels. The reference key retains exact source/excerpt identities and Unicode
ranges. Sinter keeps each quoted paragraph together in Word when it fits on a page;
bounded source captions and date labels stay with their next quoted note. Long or
unsupported layouts can still cross pages.

This option reproduces the existing selection, not all original sources or their
unselected surrounding text. It does not answer the questions, verify source
metadata, accept owners or confirm dates. Inspect the selection and originals
before sharing. **Download Word** exports the document wording currently shown;
applied edits can change or remove evidence. The option applies to source-only
handovers, not optional model-generated drafts.

The explicit choice survives project save, reopen and backup restore. Changing it
retires the current preparation and invalidates its old model-transfer preview;
prepare again before using the new scope. Historical saved reports and exports
retain their original wording. Share a project backup separately if the reader
needs the full admitted collection.

## Save, reopen and hand over

**Save project** writes to the local Sinter workspace. A revision check prevents a
second tab overwriting newer edits. On a conflict, export your editor first, then
reopen the saved version and reconcile them. Originals and questions remain editable.

**Export project backup** creates a JSON casebook containing all admitted originals.
Restoring a backup opens a new unsaved editor rather than replacing an existing
project. A report's evidence pack includes selected-source originals plus a complete
source register; use the casebook backup for the full collection.

Local data and exports are unencrypted. Check permissions and private material before
sharing. There is no shared-account synchronization, background cloud backup or
automatic publication. Removing a saved project does not erase exported copies.

In development, **Copy backup text** under **Backups and project removal** offers
complete JSON for manual recovery if the browser download does not arrive. Add or
clear a pending source first. **Refresh backup text** captures current project
inputs without writing to the clipboard; **Select backup text** lets you copy it
manually when clipboard access is missing or stalls. Paste and keep the text
yourself. These actions do not save the project or establish that a file exists.
Backup text preserves work awaiting admission, including stale source choices;
restoring or saving still requires resolving those choices explicitly.

## Optional model assistance

First prepare the source-only report. Expand the exact-transfer preview: up to eight
questions and eight selected passages, not the entire collection. Approve transfer
before asking an explicitly configured capable provider for a richer draft. Changing
the project removes the previous preview and requires preparing it again.

For a scoped project, each previewed question shows its own allowed passages.
An answer section cannot cite another question's passages; a question with no
previewed evidence remains unanswered. The eight-question/eight-passage limit can
exclude additional material from the draft even when the source-only report
contains it. The preview shows what will actually be sent.

Unknown or missing excerpt IDs cause the generated draft to be withheld. Valid IDs
establish only that references exist: they do not prove an assertion follows from
its source. The generated draft is labelled unverified and is kept separate from
original evidence. No official communication is sent automatically.

A provider or model profile may refuse a task that exceeds its input/output or
request-field limits. NeuroForge's compact native profile does not establish
support for a long structured casebook draft. Retain the useful local report and
choose a smaller task or explicitly configure a capable provider. Incomplete or
invalid response text is retained locally when available, with an incomplete
status rather than accepted answers. No uncertain request is replayed
automatically; inspect Recent activity before deliberately trying again.
Invalid Unicode code units use a labelled, reversible escaped representation so
the recovery result remains readable and can be saved; valid response text stays
unchanged. A retained response is not a validated answer.

## Large inputs and recovery

The initial limits are 300 documents, 200,000 characters per document, 2,000,000
characters per collection, 20 questions and 6,000 indexed passages. These are local
retrieval limits, **not** a model context-window claim. Split oversized collections
into purposeful casebooks. No silent claim of exhaustive review is made.

At most 50 casebooks and 200 reports are retained. A single report save is capped at
2 MB; large evidence packs can be downloaded, while the full casebook can be saved
up to its separate 10 MB encoded limit. Recent activity is temporary, not a backup.

**Recent activity** recovers a task after a page reload or lost polling connection
without submitting the original request again. Jobs survive browser disconnection,
not application restart. Completed results expire after 30 minutes or under the
20-task retention cap. Save/download results promptly. Cancelling is cooperative:
it takes effect at the next bounded operation, not necessarily instantaneously.
