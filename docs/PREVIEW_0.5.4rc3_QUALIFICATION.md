# RC3 qualification requirements

Status: sealed version for candidate building and installed qualification. This
document is not an installer qualification or a publication receipt. Published
v0.5.3, v0.5.4rc1 and v0.5.4rc2 remain unchanged. Keep the exact build commit in
each receipt; source-tree equality with another commit does not change that
build identity. Hosted review builds do not publish this scoped prerelease.

The dedicated same-repository qualification branch additionally consumes its
same-run Linux x64 artifact in hosted CI. It prepares a small tooling image,
then runs the existing three pinned copied/installed upgrade producers and both
installed browser producers with application-test networking disabled. The
`sinter-linux-installed-gates/v1` receipt records partial progress and cleanup;
independent Python-free installation and the final canonical candidate gate
remain explicitly false there, even when those installed workflow gates pass.
Image preparation and public checksum-pinned prior downloads happen before the
offline application tests. This job cannot stage a release, create a tag or
publish, and does not establish managed cloud-browser access or real AI quality.

The separate final qualification branch consumes the unchanged retained installed
artifact, preserving its original build commit. Its clean Ubuntu image contains
no system Python/account packages: inspect the actual root filesystem and package
inventory before installation, install the exact Debian bytes with networking
disabled, compare the complete frozen self-test JSON to the original installed
receipt, then remove the package and owned container. Only after those checks may
the existing canonical candidate `prepare`/`verify` produce a local stage.
The audit tooling commit is recorded separately; it never changes the build pin
or rewrites historical partial receipts. This CI job cannot publish a release.

RC3 retains noticed terminal libraries including tinfo/ncurses. Its independent
review requires readline exclusion and actual terminal-library notice/reference
bytes, checked against the Debian payload. The older RC1/RC2 independent exclusion
requirements remain intact. The nine-target publisher must still reject Linux-only
promotion. Use process-only `TZ=UTC` when reproducing the hosted Git source archive;
Git ZIP timestamps depend on the archive process's timezone.

The prospective candidate is Linux x64 on Ubuntu 22.04/glibc 2.35 only. Other
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
3. Run the existing `installed-workflow/v1` browser gate unchanged. Inspect
   sources, prepare a useful source-only handover, edit, save, quit, restart,
   reopen, export Word and JSON, and restore distinct copies.
4. Run `tools/installed_recovery_browser.py` in installed mode against the same
   binary. Retain all fourteen recovery artifacts and ten complete campaign
   phases. Observe four actual process runs and their exits. Check held actions,
   cold reopening, explicit resume and closed-route calendar exclusion, including
   truthful unknown owners and proposed dates. Exercise failed Save with the
   process stopped, both clipboard and denied/unavailable clipboard recovery,
   and restoration without changing the saved original.
5. Independently inspect the actual artifact contents and installer, then verify
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
