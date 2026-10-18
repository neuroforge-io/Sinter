# Saved preview qualification — 18 October 2026

This is source qualification for the saved-copy preview change on parent
`45b55e44b5dcc8c254fe79d9e03d744b44ddca31`. It does not qualify an installed
release, upgrade, other platforms, hosted model quality or the whole product.

## Behavior

The full renderer and preview use one block lexer. Preview sections contain at
most 2,400 Unicode code points and retain original source offsets, line endings,
trailing whitespace and evidence. Fitting complete blocks retain formatting;
oversized, continued and unfinished blocks stay literal through their actual end.
Original page-break eligibility is carried into bounded rendering, so a section
edge cannot manufacture a divider.

Only the selected copy has a cached source index. Next/Previous reuse it, without
refetching the report or granting save/draft authority. Closing, filtering,
switching and disposal retain the existing cancellation and generation checks.
Incomplete and recorded stale qualifications remain on every section.

Phones use page scrolling through the preview. Desktop keeps its bounded
scroller. Opening and explicit section navigation focus and immediately reveal
the preview heading; unrelated asynchronous completion cannot steal focus.

## Evidence and failures

The focused Node suite passed 26 checks, including 38 frozen semantic DOM cases
from the original renderer. Coverage includes exact Unicode/CRLF/bare-CR
reconstruction, code fences, nested lists/quotes, tables, safe links, hostile
HTML as text, original page-break context, cached navigation and late replies.

Three sequential offline Browser runs used the production local application and
one isolated four-report fictional workspace. The final run verified code
continuation followed by rich prose, literal versus genuine page breaks, and
seven immediate focused-heading checks at 390×640, 320×568 and 1280×720.
Both phone widths had no document horizontal overflow or nested preview scroll.
Visible phone controls met the 44px height target in the first run.

The first run exposed an off-screen focused heading. An intermediate repair
reached the right position only after the page's smooth animation. Those failure
receipts were retained; explicit immediate section scrolling fixed the final run.
Every run ended through an acknowledged Quit, drained all handlers and retained
all four original raw rows unchanged. Each selection fetched its full report
once; section navigation did not refetch. The final explicit reopening fetched
that report a second time. No save/delete or model request was sent; the only
POST was local Quit. Owned tabs closed and viewport overrides were reset.

An earlier pre-packing-repair Node profile under a 256 MiB resident-memory limit, swap disabled and
25% CPU quota peaked at 172,960 KiB RSS for the tested workloads. A dense admitted
input produced 740,000 compact spans; sampled sections stayed within 2,400 code
points. These measurements exclude the browser, installed app and customer
hardware, and do not establish a speed comparison.

Eight relevant JavaScript files passed 87 checks after the packing repair.
Six offline Python files passed 85 tests before that final window-only change;
fatal lint and public-boundary checks passed in that stage.

The local ten-journey Chromium attempt did not pass. It reached the 512 MiB
resident-memory ceiling and produced screenshot failures. It also exposed a real
packing defect: a short heading before an oversized paragraph wasted the first
section. The repair fills remaining space only for a block that cannot fit any
whole section; fitting blocks still move intact. Regression cases cover a full
first section, closing wording in the second, exact 2,400-character boundaries
and emoji. The owned suite was stopped and reaped; its zero stop status is not a
passing test receipt. The final packing journey and full-suite qualification
remain subject to the exact committed source's CI and further interface review.

## Limits

This pass does not requalify save/export, interrupted hosted requests, installed
upgrade, Windows process ownership or RC4 publication. The previous real
saved-copy operator receipt remains separate. Preview metadata is still bulky
on phones. Provisional workflow ratings remain below 10; more product and
installed-release work is required.

The shared-machine checks, logs and original failure evidence are retained
privately. No runtime workspace or private correspondence is committed.
