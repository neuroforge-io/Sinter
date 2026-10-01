# Native-to-browser source acceptance — 1 October 2026

Current `0.5.4rc4.dev0` source lets the native source window explicitly open the
full browser workbench over its current application and workspace. A normal
close waits for admitted HTTP handlers and listener cleanup before releasing
that application. Published RC3 assets remain unchanged; this is not a new
installer, OS-browser launch or upgrade qualification.

## Behavior and recovery

Opening the workbench requires an explicit action. Native source edits can be
saved first, retained in that window or cancelled. The browser sees saved work;
separate unsaved native inputs remain there. The local address contains no
source text, workspace path or credential. Watch scheduling stays paused in
this owned session; Check now remains a separate explicit service request.

The owned listener atomically tracks admitted handlers. Close stops admitting
new requests and polls without blocking Tk. If a handler or cleanup does not
finish within the five-second bound, Sinter refuses close and retains its native
runtime and inputs for explicit retry. Keep window open cancels the drain before
listener cleanup starts. Cleanup failures are retained and retryable; no request
is automatically replayed. Browser Quit requests native confirmation instead of
prematurely clearing browser inputs. Edits made while waiting keep the native
window open after listener shutdown.

Cooperative job cancellation is not a guarantee that every background job has
finished. If Tk has already failed, emergency cleanup is bounded and honest:
a continuing Python caller owns its in-process work, but the graphical launcher
returns exit 1 and process memory is not a durable recovery copy. Hard process
termination likewise cannot guarantee unsaved work or unfinished requests.

## Evidence and limits

The reviewed eight-path proposal is bound to freeze
`24375a0a3c63d4446bb72528ca07f548f4d3220157ab556a0fbe638e301439f0`
and patch `946b62878bb4c844237920977087de0a1e38ea017757565d4817e52f3558ea58`.
Independent review `1d73644575e098e01597001ad055513153ecf6d00101f561826efe5075378d4d`
retains the original failed lifetime/cleanup/confirmation witnesses, verifies
all 49 referenced authored artifacts, and accepts the corrected tracked-handler
source scope. Its own checks include 293 Python passes with four display skips,
33 real-loopback lifecycle checks, 13 cleanup checks and 44 headless browser
checks at 1440/390 widths. These scopes overlap; their counts are not added.

The author's separate actual source-Tk/Xvfb proofs pass 58 checks and 17 default
timeout checks. The latter refuses at 5.022 seconds, keeps inputs/runtime intact
and completes one held save only after explicit release, before explicit close.
These are not independent installed or physical customer-display tests.

Root first composed the repair on `bb0b604`: 3,146 Python passes/nine skips in
187.06 seconds, 282 JavaScript passes, 44 owned-browser checks, seven handover
browser journeys and 50 Word-copy recovery checks. After upstream merged the
Linux menu work, root made a fresh 403-file composition on
`917bb92a8d8f762f7885caddd5b8fbc79e3f46c0`. All nonowned files and the new Help
wording are retained. Freeze
`70dc16d656f3081895a8174d62a1acb4ab93ee6d6deb79aea43754819cc7c93d`
passes 3,173 Python tests/nine skips in 201.67 seconds, 282 JavaScript tests and
44 fresh browser checks. Fatal lint and the public-boundary gate pass. Canonical
files stay exact; generated test bytecode is recorded separately. Receipt
`a7d840b0d288a08ad1ad4cc8c4e5581fd3f4e7565f1d4e6d5891bb224352ba2e`
binds the new source and results. Later acceptance documentation is not runtime
requalification. The nine skips are four explicit Tk display tests and five
Windows wrapper tests, not passes.

An actual in-app-browser run on an isolated NeuroForge case opens all 11
original sources, chooses three sources for one question, prepares a 16-passage
handover and explicitly saves a separate report. Original source identities,
200,553 characters and exact Unicode quotation ranges survive a read-only cold
inspection. This does not verify eligibility, spending, supplier agreement,
submission or current programme facts. It reproduces selected-but-unused sources
and a table heading cut off before its values; those remain substantive work.

The manual Quit confirmation stalls the browser-control interface. Its documented
dialog/close controls do not recover the temporary tab, and targeted Linux screen
capture is denied. User dismissal is pending; no in-app cancellation or normal
native-close pass is claimed. The owned test service is stopped. Its initial
post-close observer omitted the scoped-casebook capability and was correctly
refused; a separate direct read-only repository inspection verifies conservation.
Original failure logs remain intact. The user's earlier intentional app closure
was never treated as a crash or reopened for these tests.

An independent read-only check of the actual scoped project passes 19 probes
and three existing conflict/no-op regressions. Its review
`33ffe818aab256338876cd7380b5ac40084a0cecf2363eb840de80b93815cc95`
binds all 403 composed source files and verifies all original documents, the
full source register, selected excerpts and stored report bytes without writes.
Native v2 editing remains unsupported: open and dirty v1 replacement refuse
before mutation. Keep the v2 backup and use the full workbench; do not reset
source choices automatically. An unchanged native save can return an obsolete
cached revision without writing. No fresh-revision validation is claimed for
that no-op, and clearer two-view feedback remains work.

The independent component scores are UX 7.2, functionality 7.8 and aesthetics 7.0.
They cover the owned handoff and normal-close design, not the whole product.
Two-view save coordination, native presentation limits, in-app confirmation
control and fresh installed/upgrade proof remain work. No 10/10 is claimed.

See [the runtime guide](PORTABLE_RUNTIME.md) and the focused
[shutdown regressions](../tests/test_native_browser_handoff.py).
