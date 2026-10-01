# RC3 qualification requirements

Status: requirements and historical tooling scope. Linux x64 v0.5.4rc3 was
published from `246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe`; see the
[publication receipt](releases/PREVIEW_0.5.4rc3_PUBLICATION_RECEIPT.md) for its
exact assets, evidence and limits. This requirements document does not itself
qualify an installer. Earlier releases remain unchanged. Keep the exact build
commit in each receipt; source-tree equality with another commit does not change
that build identity. Hosted review builds do not publish this scoped prerelease.

The existing hosted installed-gate job still targets its historical qualification
branch; it does not automatically qualify current main. A fresh source-pinned run
must consume its own newly built Linux x64 installer. Prepare a tooling image,
then use the existing local runner for the three pinned copied/installed upgrade producers
and both installed browser producers with application-test networking disabled.
Its `sinter-linux-installed-gates/v1` receipt records partial progress and cleanup;
independent Python-free installation and the final canonical candidate gate remain
explicitly false there, even when those workflow gates pass. Image preparation
and checksum-pinned public prior downloads precede offline application tests.
These gates cannot publish and do not establish customer-device or AI quality.

The retained D9 artifact (`d9b36a6853bab0d715dc91e726f984a8ab16a747`) is
historical installed-workflow/v1 evidence. `tools/finalize_linux_preview.py`
audits only its pinned archive; it does not qualify published E
(`246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe`) or current main. Its digest-pinned
Ubuntu image contains no system Python/account packages, but explicitly installs
`libx11-6`. That audit is not the bare no-X11/XCB install required below. The
published E bare-image evidence remains separate and unchanged.

The historical auditor checks the original package and source, inventories actual
Python/account absence, runs the installed self-test offline and removes owned
resources. It records the audit tooling identity separately and preserves original
receipts. It then refuses publication staging: current RC3 notes promise E's
workflow/v2 Word recovery, which D9 lacks. The retained audit marks the canonical
candidate gate and staging unsupported and produces no independent final-review
receipt or new release plan. After a completed audit, its CLI prints one concise
staging-refusal message to stderr and exits with code `3`, preserving the audit
receipt. Unexpected errors remain failures and are not caught as that refusal.
This historical CI step cannot publish a release; exit `3` must not be reported
as a sealed-plan pass.

The retained-candidate job lives in `final-linux-rc3.yml`, a review-only workflow
that cannot be called by the release workflow. Its existing artifact-read grant
stays scoped to that same-repository job. The reusable `native.yml` keeps only
the release caller's existing contents-read grant. GitHub validates nested job
permissions before conditions, so even a skipped artifact-reader would prevent
that narrower caller from starting. A skipped native-call probe in the review
workflow exercises this actual permission admission without building packages or
publishing. See [GitHub's reusable-workflow permission rules](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows#nesting-reusable-workflows).

The final branch also runs the existing installed upgrade, workflow and recovery
job against its newly built same-run package. That receipt binds the current
combined source commit and binary; it is separate from the unchanged retained
RC3 clean-install and canonical-stage proof. A retained-artifact pass cannot
qualify later native-window or campaign changes. The current package's mapped
native-window smoke check runs in the Linux x64 build job; its installed browser
workflows do not establish a complete native-widget journey.

RC3 retains noticed terminal libraries including tinfo/ncurses. Its independent
review requires readline exclusion and actual terminal-library notice/reference
bytes, checked against the Debian payload. The older RC1/RC2 independent exclusion
requirements remain intact. The nine-target publisher must still reject Linux-only
promotion. Use process-only `TZ=UTC` when reproducing the hosted Git source archive;
Git ZIP timestamps depend on the archive process's timezone.

The published RC3 candidate is Linux x64 on Ubuntu 22.04/glibc 2.35 only. Other
platforms need their own installed evidence. Packages remain unsigned and not
notarised; do not disable OS protections to install them.

## Required evidence

1. Seal the candidate version and exact source commit. Build its installer,
   source ZIP, dependency notices, asset hashes and native test receipt using
   the existing release machinery.
2. Test the actual package in the disposable offline qualification image.
   Replace each checksum-pinned published prior separately: v0.5.3, RC1 and RC2.
   Preserve copied fictional workspaces, preferences and explicit model choices.
   RC2 also retains changed source snapshots, stale user-marked reviews,
   historical reports and unknown versus unassigned owners.
3. For current source with the local Word-copy operation, run
   `installed-workflow/v2`; historical v1 receipts keep their original meaning.
   Inspect sources, prepare a useful source-only handover, edit, save, quit,
   restart, reopen, export Word and JSON, and restore distinct copies. Verify
   the actual 53-operation installed catalogue and all thirteen artifacts:
   pending-edit refusal, changed wording in a distinct saved copy, lost save
   confirmation without replay, and unchanged originals/preferences. Read all
   three actual Word files again after the installed process has quit.
4. Run `tools/installed_recovery_browser.py` in installed mode against the same
   binary. Retain all fourteen recovery artifacts and ten complete campaign
   phases. Observe four actual process runs and their exits. Check held actions,
   cold reopening, explicit resume and closed-route calendar exclusion, including
   truthful unknown owners and proposed dates. Exercise failed Save with the
   process stopped, both clipboard and denied/unavailable clipboard recovery,
   and restoration without changing the saved original.
5. Independently install the same actual Debian package on a digest-pinned
   Ubuntu 22.04 base without preinstalled Python, account libraries or X11/XCB.
   Disable test networking; verify the bundled toolkit imports, complete the
   installed self-test and remove the package. Keep this cold import/install
   proof separate from graphical launch and from the Python-equipped tooling image.
6. Run the current native launch qualifier against the fresh frozen executable
   on an isolated display. Retain its full bounded receipt; inspect both mapped
   launches, clean stderr, shutdown and saved fictional workspace/preferences.
   This launch check does not establish the full native editing experience.
7. Independently inspect the actual artifact contents and installer, then verify
   the complete staged publication plan. Do not publish a renamed source
   rehearsal, a list of claimed passes or receipts from a different binary.

`--source-fixture` is useful for development rehearsals. Its receipt is explicitly
`sinter-source-recovery/v1`, not frozen and not installed qualification. Installed
mode requires the real candidate package, source ZIP, native receipt and preceding
installed workflow receipt. The producer uses an existing disposable image with
network disabled; it does not pull an image or use a real private workspace.

The existing Chromium CI job runs this source rehearsal and retains its receipt
and artifacts. Qualification launchers explicitly request browser presentation
for RC3/current source using the same runtime. Published browser-default priors
and historical candidates retain their original launch arguments. Bare native
application startup remains unchanged. A passing source rehearsal does not
qualify an installed candidate or remove a managed browser's loopback policy.

Copying or selecting complete backup text does not save the campaign or create
a file. Recovery above the product's saved-work size limits is not certified as
an installed restore. Campaigns containing On hold need a newer preview; keep
an unchanged older workspace copy when testing a return to an older version.

## Capability limits

The core fictional workflow must need no account, internet, API key, downloaded
model or successful generation. These checks do not establish grant eligibility,
customer-device acceptance, scientific validity, general native assistant quality
or completed live ChatGPT generation. Native NeuroForge remains an optional
buffered profile with its existing bounded contract; the public API fixture and
provider identity checks are not relaxed by release qualification.

Local work and backups are unencrypted. Sinter remains a single trusted user's
local workbench, without automatic grant submission or email sending.
