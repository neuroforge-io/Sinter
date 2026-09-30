# Use RKC knowledge in Sinter

[Back to Sinter](../README.md)

RKC is an optional, separately installed [Repository Knowledge Compiler](https://github.com/neuroforge-io/RKC). Its compiler creates a canonical atlas without a model. Sinter's adapter is a consumer of that evidence, not a replacement for RKC's validation or model-qualification policy.

## Start with an export

Open **Knowledge atlases**, select an RKC `bundle.json` or a `rkc-context/v1` JSON packet, and enter a question. Choose **Find supporting material**. Nothing is sent to an AI for this operation.

Imports are bounded to 4 MB. Bundle search uses exact node names/signatures plus supplied Markdown sections from source documents bound to matching `document_section` nodes. A section body keeps the existing node citation identity and its exact JSON field location. Other document content and complete original source files are not imported. Context packets can contain richer indexed text; producer truncation warnings are retained. Paths and anchors inside an imported atlas are labels, never instructions to open or fetch files. Unexpected schemas, conflicting source bindings and duplicate/mismatched citation identities are rejected.

The output preserves snapshot identity, source paths, supplied source-location fields, evidence identifiers and JSON locations. Source locations describe the producer's source object; they do not establish exact positions for an indexed excerpt. Sinter's `start`/`end` are character offsets within retained packet text, separate from producer byte, line and column coordinates. Omitted coordinates remain omitted. Markdown section output also retains its document/section identity, generator and producer status. The imported packet's producer integrity/digest or status label is **not independently verified** by Sinter. A local normalized import hash is provided separately. Exact excerpts can still be incomplete, stale or false.

## Read richer context from a local RKC

Start the read-only RKC API for an already compiled atlas:

```sh
rkc serve --dir ./my-project/.rkc --addr 127.0.0.1:8787
```

Set the matching local port in **Settings > Advanced**, then choose **Read context from local RKC**. Sinter connects only to `127.0.0.1`, rejects redirects and checks that the packet snapshot agrees with the response header. It does not accept arbitrary remote retrieval destinations.

Source updates require an explicit new import or local context read from the selected updated atlas. Retained packets remain unchanged; a new snapshot changes citation IDs. Replacing or attempting to replace an import, reading local context, or editing the question clears prior transfer consent. Review the new source packet and approve its transfer again before requesting a draft.

## Create a new atlas

Install a trusted RKC binary separately and enter its absolute executable path in Settings. Select up to 60 ordinary text files, at most 500 KB combined, and confirm **Create an atlas from these files**.

Sinter writes only those selected files into a temporary collection, invokes `rkc quickstart` without a shell and returns the resulting bounded bundle. Compilation has a three-minute limit and cooperative cancellation. Temporary source files are removed when the operation ends; download the resulting bundle to keep it.

RKC retains its own resource controls. On Linux, compilation may require its documented user-systemd/cgroup configuration. Sinter does not disable that policy. Importing an existing atlas or serving its context can be a better route for larger projects.

## Ask your configured model to help

After reviewing the source context, explicitly approve transfer of the selected excerpts and question. **Draft with your model** uses the API address/model chosen in Settings and creates a separately labelled draft. It sends at most twelve selected excerpts under a bounded input budget, not the complete atlas.

Unknown citation numbers cause the generated answer to be withheld. Existing citation numbers only prove that a reference exists: they do not prove a claim follows from it. Read the cited material and the model draft before use.

This supplies Fracture-powered reasoning **over RKC context in Sinter**. It does not register a provider inside RKC, bypass qualification, mark any model qualified, or use model prose to alter canonical atlas records. That deeper provider integration remains separate work requiring RKC's own contract and qualification tests.

## Interoperability checks

The CI test builds the actual RKC at pinned commit `37a908e9f99cc246d8185bdc202981c0b55e9ef5`, compiles a small fictional collection, imports its bundle, starts the local read API and checks context/citation handling. Its receipt records the tested snapshot and revision. No live AI call or private repository source is used.

The browser test separately exercises import, local selection and the transfer-consent boundary. Test fixtures are not a claim that every historical or future atlas schema is supported.

## Free fictional source-inspection exercise

Use the supplied fictional fixtures without a model: import
`tests/fixtures/rkc_markdown_bundle.v1.json`, search **renewals**, and inspect the
14-day lending statement, producer source location and exact section JSON pointer.
Download both context JSON and Markdown and compare the retained body with the
supplied section. A Sinter context download is an output record, not an RKC input
packet; it is not advertised as reimportable.

For the explicit update exercise, use the `packets.before` and `packets.after`
objects from `tests/fixtures/rkc_sinter_context_bridge.v1.json` as separate RKC
JSON imports. The first says 14 days and the second says 21 days. Confirm that
new consent is required after replacement, the new snapshot/citations differ,
and an earlier downloaded packet remains unchanged. Never use real learner,
customer or account data for this practice.

`python tools/atlas_source_browser.py` runs these fictional import, selection,
source inspection, download, corruption rejection and consent-update journeys
through a disposable real app/browser. Add `--chromium /path/to/chromium` to use an
installed browser. Unique receipts, downloads and screenshots are retained under
`browser-artifacts/atlas-source-*`; model, search, credential and external-call
attempts are blocked and counted. This is Sinter consumer/UI qualification with
recorded fixtures, not live RKC producer, model quality or platform qualification.

### Scope of the September 30 source-preservation checks

The original recorded bridge remains separate from the current producer-only
fixture in `rkc_sinter_context_bridge_source_bound.v1.json`. The reviewed Sinter
consumer retains that fixture's whole-document `handbook.md` range (lines 1–12)
and four supplied evidence IDs for the 14-day, 21-day and retained-old packets,
and rejects its snapshot-only swap and corrupt citation packets. Recorded RKC
canonical/reimported reference rows are compared locally; no evidence endpoint
is called and no RKC producer is rerun by this Sinter test.

The legacy RKC verifier's audited Sinter source hash remains unchanged. That
optional check was not run against modified consumer source and its pin was not
relaxed; the new consumer regression and receipt are separate reviewed evidence.
The source-document Markdown bundle fixture is constructed from the verified
existing schema, while the context packets are recorded RKC output. These local
checks do not qualify live model grounding, general quality or Windows/macOS.
