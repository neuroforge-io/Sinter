# Browser Quit source review — 2 October 2026

Development `0.5.4rc4.dev0` uses the existing in-page confirmation component for
browser Quit. **Keep working** receives focus first; Tab stays within the dialog,
Escape cancels and cancellation restores focus without sending a quit request.
Quit is available on narrow screens. A grid sizing correction also keeps the
pending report editor within the phone viewport without cutting its text.

An unconfirmed response retains browser project/report inputs and warns the user
to check whether Sinter is running before explicitly retrying. No quit request
is automatically replayed. A standalone acknowledgement clears browser drafts
only after that explicit choice. The stopped state disables navigation and drops
late content/error responses. It releases the unload guard after confirmed stop;
uncertain, pending or cancelled dirty work retains the appropriate protection.
The native-owned workbench requests its separate native confirmation and keeps
browser work. This does not make unsaved inputs durable after process exit.

## Adversarial review and conservation

The first private proposal failed independent review: an already admitted
workspace-list response replaced the stopped view after Quit. The V1 HOLD and
all 27 original evidence files remain retained. A second proposal fixed that
race but incorrectly kept an unload warning after confirmed stop. Its separate
six-pass/one-failure probe is retained. The accepted V3 passes the same seven
unload checks.

Independent acceptance receipt
`1c79414b0c64b005f4828b49b217ebe5a843052aea3b380635c19ecce30edb75`
binds the 405-file V3 source freeze
`7618c165c27888de8c470f645ffd8bc867dc41349138a1f52106693e2da8d059`.
The review passes the original 17-check witness, 33 lifecycle checks, 17 separate
late-error checks and seven unload checks. These overlapping scopes are not
added into a total. Callback acknowledgement and synthetic unload policy remain
distinct from real process exit or a physical browser confirmation.

Root's 410-file composition on `1382ce3d8449a29bf1dfb39eea10b5790ad6fcd3`
keeps the existing evidence/context work and diagnostic checker. Its freeze
`791fcd5778e4dd6fcdb0925160e21933b91c07bc089f95cbc94eb181a48c3230`
passes 185 focused Python tests in 19.19 seconds, 294 JavaScript tests, 26 original
quit checks and 51 evidence-context checks. The generic offline browser and
casebook confirmation producers pass. Four actual source-process launches save,
quit, reopen, interrupt with SIGTERM and reopen again. Saved SQLite logical rows,
persistent metadata and preferences stay exact; ports/process groups close,
all four exits are zero and no provider request is made. Receipt
`8f46be0f557cf520c4b5dab132e7ac6340ca39dc5a96f08d04d6a214641ec96c`
binds those results. No fresh blanket backend suite is claimed.

The reusable quit producer additionally covers delayed successful and failing
local workspace-list responses at desktop and phone widths. Its eight journeys
pass 38 checks in the author's fresh current composition. Applied to held V1,
the same new oracle passes 28 checks before refusing the replaced stopped view.
The exact source/QA handoff is
`87423f0fc1ba45105a9d9887da413bb61dadc2f209b3d119da9e9a6251352489`;
accepted runtime bytes and the original 26 checks remain unchanged.

Root also executes those 38 checks against current main after the separate
upgrade-tool checkpoint `01ad17e670d3d966ea07b2eec553cc741bad5a4e`; all eight
journeys pass. Routine Chromium CI now includes this producer and the source
coverage, question-evidence and project-decision producers. Their fictional
temporary artifacts are retained by the existing always-upload step. This is
source CI coverage; its addition does not establish a completed hosted CI run.

Before adoption, root freezes all 411 current source/documentation files over
`01ad17e` as
`b40f2c3e2260632385e95e607155632f2727a8743810a2d481071349177b1243`.
The fresh full Linux/Python 3.12 suite passes 3,226 tests with nine explicit skips
in 283.40 seconds. Those skips cover four native display tests and five Windows
wrapper tests. All canonical hashes remain exact after testing; 294 JavaScript
tests, five workflow tests and the desktop/phone question-evidence producer also
pass. The latter captures two actual Word payloads and a cold source-app reopen.
Root receipt
`dc4c9f258f630442c0268f1fc6681a1af3c0f6859d199a2882c91b97b7d0b25e`
binds these checks. This later documentation note changes no tested runtime or
QA byte and does not constitute installed or cross-platform qualification.

The first root current-composition run encountered a full temporary filesystem:
179 Python passes/six setup or database errors and browser page crashes. Those
logs and failed receipts remain intact. The unchanged source passed using an
owned home-drive temporary directory. One initial rerun used the wrong working
directory and exited four before tests; that orchestration error is also retained.
Other processes' exposure to temporary-drive exhaustion was not assessed.

In this single context-browser run, local surrounding-text inspection took
40–49 ms; the capacity source-list rendering took 77–93 ms. These observations
are source/host measurements, not a device-independent performance guarantee.

## Remaining qualification

The user intentionally closed their app; it was not reopened or classified as a
crash. The earlier isolated in-app-browser tab still needs its browser-native
dialog dismissed before control/cleanup can be verified. This source repair
does not retrospectively qualify that old tab. Native requested/cancelled state
checks use the actual owner event plus controlled state changes, not a physical
Tk confirmation. Actual package entry invocation, native/browser shutdown,
upgrade from published RC3 and a fresh bare installation remain separate gates.
No new installer, whole-product rating, funding eligibility or submission is
claimed. Published RC3 and its historical receipts remain unchanged.

The wider `1382ce3` source CI retains macOS failed-launcher subprocess timeouts
and Windows cleanup-retry/wrapper failures. Exact result XMLs are preserved for
separate diagnosis; this quit change does not resolve or relabel those tests.
