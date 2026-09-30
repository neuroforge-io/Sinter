# Public preview download review — 30 September 2026

The standalone Sinter download page now recognises canonical release candidates,
including the published `v0.5.4rc1` Linux preview. Numeric version ordering selects
one current published version. Each installer must match that version's exact
filename, target, GitHub download URL and positive integer size.

A missing current installer does not silently select an older package. Linux
x64 has the current installer; the other targets explain that no installer is
available for this version and point to its qualification notes. Earlier previews
remain accessible through the all-releases page. Failed or malformed metadata
leaves the release-page recovery link available without a guessed download.

This page does not qualify a platform. Installed qualification remains limited
to Linux x64 / Ubuntu 22.04 / glibc 2.35, recorded separately in
`releases/PREVIEW_0.5.4rc1_PUBLICATION_RECEIPT.md`. Neither that release nor its
source-pinned assets were changed by this page update.

## Evidence

Seven focused JavaScript policy tests and their Python wrapper passed. Nine real
isolated browser journeys covered current Linux selection, Windows/macOS absence,
older-preview links, malformed assets, unavailable metadata and narrow layout.
No installers were downloaded or executed during these interface checks.

An independent adversarial review passed twelve combined download/citation tests,
the Python wrapper and additional unsafe URL, invalid size, numeric version,
missing-current-asset and reusable citation-matcher probes. Its inspection of the
nine-journey browser receipt confirmed the held source hash; it did not claim a
second browser run.

The pushed page deployment at `94386868d7a98080dbd230ec96c59fb519316093`
passed GitHub Pages deployment. A separate human-style in-app-browser check of
`https://neuroforge-io.github.io/Sinter/` selected the current Linux preview,
verified its exact download link, switched to macOS and confirmed that no older
installer appeared. Screenshots are retained as
`browser-artifacts/public-preview-human-linux.jpg` and
`public-preview-human-macos.jpg`; the owned tab was closed. No download was
triggered in that check.

Local retained evidence is in `browser-artifacts/site-download-preview/`:
`browser-receipt.json`, `review-summary.json` and
`independent-critic-review.json`. Browser and server resources were closed. This
work edits Sinter's own `site/`; the sibling NeuroForge site remains read-only.

## Remaining quality limits

The implementation review scores this bounded download surface UX **7.5**,
functionality **8**, aesthetics **7**. Independent review found no concrete scoped
blocker; these scores are not whole-product acceptance. Repeated unavailable-target
copy and the existing visual treatment are useful but not exceptional. Customer
device acceptance and the other installer platforms remain outstanding.
