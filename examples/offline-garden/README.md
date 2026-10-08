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

Start with those built-in examples. You do not need a source checkout or local
copies of `casebook.json` and `campaign.json`. The steps below export real backup
files from your practice work, then restore those downloaded files. Check that
each file actually appears in your browser's downloads before relying on it.
These steps use the browser workbench; older installers retain their own
interface and capabilities.

These steps use local storage. Do not choose an optional AI draft, campaign
assistant, search or model connection during this offline walkthrough. Local
storage and downloaded backups are unencrypted.

## Prepare a useful handover

1. Choose **Open garden handover**. In **Community casebooks**, inspect the
   practice project; it starts as an unsaved copy.
2. Expand each source. Read the original funding review, handover plan and action
   table. The review note is also fictional; it is not funder confirmation.
3. Check that **Prepare a** is **Volunteer handover**. Choose **Prepare
   source-only report**.
4. Read the Document, then open Evidence. The quote has not been received; no
   person has accepted the guideline action; the treasurer's owner type remains
   unconfirmed. The insurance question has no wording match. Related wording
   alone does not establish an answer.
5. Change **Recipient or audience**. The previous report disappears because it
   reflects earlier inputs. Prepare the source-only report again. Choose **Edit
   draft**, add a fictional operator note such as "Quote still pending; no enquiry
   has been sent", and choose **Apply edits**. Review the Document and Evidence.
6. Choose **Save project** and wait for the project revision confirmation. This
   keeps the inputs and originals, not the edited report. On the report, choose
   **Save to My workspace** and wait for **Saved**. In published RC3 this report
   button is **Save to this computer**. Preparation saves project inputs locally;
   report edits still require their own explicit save.
7. Choose **Quit Sinter**. In current development, an earlier prepared report can
   still be unsaved after you save the newer version. If **Quit Sinter?** appears,
   choose **Keep working**. In **My workspace**, use **Pending work in this
   session** → **Open unsaved draft** to review and save the versions you want to
   keep. Choose **Quit Sinter** again and confirm only when you are ready to leave
   any remaining unsaved session copies behind; saved projects and reports stay.
   Reopen the browser workbench. In **My workspace**, choose **Open draft** on the
   saved handover and check that your operator note and Evidence remain.
   Separately open the project from the saved shelf in **Community casebooks**
   and check its recipient, originals and handover format. Closing only the
   browser tab leaves the server running.
8. In the project, choose **Export project backup** and keep the actual downloaded
   `sinter-casebook.json` file. This contains project inputs and originals; it does
   not contain the edited report. Export that report separately with **Download
   Word (.docx)** or **More options** → **Download Markdown**, and check the file.
9. Expand **Backups and project removal**, choose **Restore a casebook backup**,
   and select the project backup you just exported. It opens as a new unsaved
   project. Give it a distinct title and choose **Save project** to keep a
   separate copy; the previous saved project and report remain.

An unchanged reopened saved project does not require an unsaved-work warning.
Actual edits and an unsaved restored backup do. A browser warning cannot replace
an exported backup.

### Optional opening summary in current development source

This feature is not in the published RC3 installer. In a prepared source-only
volunteer handover, expand **Write handover opening**. Enter a recorded status
and a proposed next step for each item. Choose the owner type explicitly; a
suggested role is not an accepted person. Dates remain unconfirmed targets.
For evidence, choose a retained passage, select the literal wording and use
**Use selected wording**. Keep the insurance answer unknown with no citation.

Choose **Preview opening summary** and read the selected wording. **Apply
reviewed opening summary** asks before replacing an already edited draft;
Cancel keeps it. Then choose **Save to My workspace**. The saved document keeps
the original checklist, sources, citations and review state. Unapplied rows are
session-only work, not a separately saved form. On a phone, the opening is shown
as labelled cards; wider screens and Word exports retain a table.
The five-item Word opening can span two pages and remains a formatting limit.

## Operate the action and funding review

1. Choose **Open garden campaign**, then **Next actions**. Compare:
   **Check current funder guidelines** has no owner; **Obtain equipment quote**
   has an unknown owner type; **Volunteer coordinator** is only a suggested role.
   None records an accepted person.
2. Edit the quote action. For practice, replace its owner with **Casey Example**
   and select **Named person**. Leave **This person has accepted** unchecked.
   Its 9 October 2026 date remains a proposed practice target, not a confirmed
   due date or programme closing date. Choose **Save campaign** and wait for
   **Saved on this computer**.
3. Open **Opportunities** and inspect the supported-cost check. Its earlier URL
   and 12 September check date differ from the current fictional source record.
   The earlier quotation and user mark remain visible; they do not establish
   current eligibility. Applicant conditions and the application window remain
   unknown. The budget total remains incomplete while the quote is missing.
4. Choose **Prepare campaign brief**. Read its unresolved conditions and next
   move. Edit an action after preparation: the old brief becomes stale and its
   copy, save and export controls are held. Save the campaign again, wait for the
   confirmation, then re-prepare before using the brief.
5. Inspect the closed earlier round. Its answer and action remain historical
   records. The answer is held from current drafting and copying; its presence
   does not imply an application was sent.
6. Expand **Import or back up a campaign** and choose **Export campaign backup**.
   Keep the actual downloaded `sinter-campaign-backup.json` file. Reopen the saved
   campaign in a fresh browser tab and check the edited owner, unconfirmed date
   and historical records. Choose **Import campaign backup** and select that
   exported file. Give the imported copy a distinct title and choose **Save
   campaign** to keep it separately. The JSON backup retains the historical
   answer; the shareable brief intentionally holds it.

For a conflict exercise, open the same saved campaign in two tabs. Save an edit
in the second tab, then try saving different edits from the first. Sinter rejects
the older revision and keeps the first tab's unsaved edits. Export them before
reopening the newer version. Reconcile deliberately; Sinter does not silently
merge or discard either version.

If a save or quit is not confirmed, keep the current view open and back up the
local work before recovery. Check the saved project, report in **My workspace**
or campaign before explicitly trying again: the request may have finished even
though its reply was lost. Do not assume an error means nothing was saved. Keep
the original project backup as well as exported report text; selected report
evidence is not the complete source history. These local files are unencrypted.

## What this walkthrough establishes

Record what you actually observed: source inspection, useful source-only output,
action editing, save and fresh reopen, export and restore, unresolved ownership
and timing, changed source snapshots, stale brief controls and revision conflict
recovery. Passing this fictional exercise is not customer acceptance, proof of
live model quality, a funding result or a 10/10 product rating.
