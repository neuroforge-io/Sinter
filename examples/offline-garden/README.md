# A fictional garden project you can run in Sinter

This small practice project pairs a source casebook with an editable funding
campaign. Every organisation, programme, person and commitment is fictional.
No funding opportunity is researched or verified. Source links use
`example.invalid` and should not be opened.

The three original practice documents came from the agreed fictional customer
preview: `example-funding-review.md`, `example-handover.md` and
`example-actions.csv`. Their text is retained inside the casebook. An additional
fictional review note explains the deliberately unresolved conditions. The old
table's `in_progress` quote task is represented as an open campaign action; its
original status remains in the source text and action description.

The two files serve different purposes:

- **casebook.json** keeps original notes, questions and the volunteer handover
  format. Its report selects literal passages and leaves missing answers visible.
- **campaign.json** keeps editable actions, unknown costs, funding checks and
  historical records. Owner type, acceptance and proposed dates are separate.

## Open the example

In the published `0.5.4rc3` Linux browser workbench, open **Overview** or
**Getting started** and choose **Open garden handover** or **Open garden campaign**.
After Debian installation, open that workbench with
`/opt/neuroforge/sinter/Sinter app --mode browser`; the application-menu entry
opens the smaller native source workspace. Each example opens a
new unsaved copy of this bundled data; the on-page guide links to its paired
editor. Switching between them resumes your session edits. Existing saved work
is unchanged, and replacing different unsaved inputs requires an explicit choice.
Preparing a casebook report saves the project inputs; edited document text needs
its separate **Save to My workspace** action in current development. The published
0.5.4rc3 preview labels this **Save to this computer**; it saves the report inside
Sinter, while **Save Word copy on this computer** creates a separate Word file.
Direct example entry is also
available in rc2; it is not part of the frozen 0.5.4rc1 installers.

To practise restoring backups, use the file path below. These steps use the
browser workbench; older installers retain their own interface and capabilities.

Start Sinter and open **Community casebooks** (`#casebooks`). Expand **Backups
and project removal**, choose **Restore a casebook backup**, and select
`casebook.json`. This opens a new unsaved project. Select **Save project**.

Open **Funding campaigns** (`#campaigns`). Expand **Import or back up a
campaign**, choose **Import campaign backup**, and select `campaign.json`.
Choose **Save campaign**. Importing creates a separate copy when saved; it does
not overwrite an existing campaign.

These steps use local storage. Do not choose an optional AI draft, campaign
assistant, search or model connection during this offline walkthrough. Local
storage and downloaded backups are unencrypted.

## Prepare a useful handover

1. Return to **Community casebooks** and open the saved garden handover.
2. Expand each source. Read the original funding review, handover plan and action
   table. The review note is also fictional; it is not funder confirmation.
3. Check that **Prepare a** is **Volunteer handover**. Choose **Prepare
   source-only report**.
4. Read the Document, then open Evidence. The quote has not been received; no
   person has accepted the guideline action; the treasurer's owner type remains
   unconfirmed. The insurance question has no wording match. Related wording
   alone does not establish an answer.
5. Change **Recipient or audience**. The previous report disappears because it
   reflects earlier inputs. Prepare the source-only report again, then use its
   copy or download controls.
6. Choose **Save project**, use **Quit Sinter**, then reopen the browser workbench
   and open the project from the saved shelf. Check that the recipient, originals
   and handover format remain. Closing only the browser tab leaves the server
   running.
7. Choose **Export project backup**. Restore that file through **Restore a
   casebook backup**. It opens as a new unsaved project. Save it as a separate
   copy; the previous saved project remains.

An unchanged reopened saved project does not require an unsaved-work warning.
Actual edits and an unsaved restored backup do. A browser warning cannot replace
an exported backup.

## Operate the action and funding review

1. Open the saved garden campaign and choose **Next actions**. Compare:
   **Check current funder guidelines** has no owner; **Obtain equipment quote**
   has an unknown owner type; **Volunteer coordinator** is only a suggested role.
   None records an accepted person.
2. Edit the quote action. For practice, replace its owner with **Casey Example**
   and select **Named person**. Leave **This person has accepted** unchecked.
   Its 9 October 2026 date remains a proposed practice target, not a confirmed
   due date or programme closing date. Save the campaign.
3. Open **Opportunities** and inspect the supported-cost check. Its earlier URL
   and 12 September check date differ from the current fictional source record.
   The earlier quotation and user mark remain visible; they do not establish
   current eligibility. Applicant conditions and the application window remain
   unknown. The budget total remains incomplete while the quote is missing.
4. Choose **Prepare campaign brief**. Read its unresolved conditions and next
   move. Edit an action after preparation: the old brief becomes stale and its
   copy, save and export controls are held. Re-prepare before using it.
5. Inspect the closed earlier round. Its answer and action remain historical
   records. The answer is held from current drafting and copying; its presence
   does not imply an application was sent.
6. Export a **campaign backup** from **Import or back up a campaign**. Reopen the
   saved campaign in a fresh browser tab and check the edited owner, unconfirmed
   date and historical records. Import the exported backup and save a separate
   copy to demonstrate recovery. The JSON backup retains the historical answer;
   the shareable brief intentionally holds it.

For a conflict exercise, open the same saved campaign in two tabs. Save an edit
in the second tab, then try saving different edits from the first. Sinter rejects
the older revision and keeps the first tab's unsaved edits. Export them before
reopening the newer version. Reconcile deliberately; Sinter does not silently
merge or discard either version.

## What this walkthrough establishes

Record what you actually observed: source inspection, useful source-only output,
action editing, save and fresh reopen, export and restore, unresolved ownership
and timing, changed source snapshots, stale brief controls and revision conflict
recovery. Passing this fictional exercise is not customer acceptance, proof of
live model quality, a funding result or a 10/10 product rating.
