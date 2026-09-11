# Use RKC knowledge in Sinter

[Back to Sinter](../README.md)

RKC is an optional, separately installed [Repository Knowledge Compiler](https://github.com/neuroforge-io/RKC). Its compiler creates a canonical atlas without a model. Sinter's adapter is a consumer of that evidence, not a replacement for RKC's validation or model-qualification policy.

## Start with an export

Open **Knowledge atlases**, select an RKC `bundle.json` or a `rkc-context/v1` JSON packet, and enter a question. Choose **Find supporting material**. Nothing is sent to an AI for this operation.

Imports are bounded to 4 MB. Bundle search uses exact node names/signatures, not all original source text. Context packets can contain richer indexed text; producer truncation warnings are retained. Paths inside an imported atlas are labels, never instructions to open local files. Unexpected schemas and duplicate/mismatched citation identities are rejected.

The output preserves snapshot identity, source paths, evidence identifiers and JSON locations. The imported packet's producer integrity/digest label is **not independently verified** by Sinter. A local normalized import hash is provided separately. Exact excerpts can still be incomplete, stale or false.

## Read richer context from a local RKC

Start the read-only RKC API for an already compiled atlas:

```sh
rkc serve --dir ./my-project/.rkc --addr 127.0.0.1:8787
```

Set the matching local port in **Settings > Advanced**, then choose **Read context from local RKC**. Sinter connects only to `127.0.0.1`, rejects redirects and checks that the packet snapshot agrees with the response header. It does not accept arbitrary remote retrieval destinations.

## Create a new atlas

Install a trusted RKC binary separately and enter its absolute executable path in Settings. Select up to 60 ordinary text files, at most 500 KB combined, and confirm **Create an atlas from these files**.

Sinter writes only those selected files into a temporary collection, invokes `rkc quickstart` without a shell and returns the resulting bounded bundle. Compilation has a three-minute limit and cooperative cancellation. Temporary source files are removed when the operation ends; download the resulting bundle to keep it.

RKC retains its own resource controls. On Linux, compilation may require its documented user-systemd/cgroup configuration. Sinter does not disable that policy. Importing an existing atlas or serving its context can be a better route for larger projects.

## Ask Fracture to help

After reviewing the source context, explicitly approve transfer of the selected excerpts and question. **Draft with Fracture** uses the API address/model chosen in Settings and creates a separately labelled draft. It sends at most twelve selected excerpts under a bounded input budget, not the complete atlas.

Unknown citation numbers cause the generated answer to be withheld. Existing citation numbers only prove that a reference exists: they do not prove a claim follows from it. Read the cited material and the model draft before use.

This supplies Fracture-powered reasoning **over RKC context in Sinter**. It does not register a provider inside RKC, bypass qualification, mark any model qualified, or use model prose to alter canonical atlas records. That deeper provider integration remains separate work requiring RKC's own contract and qualification tests.

## Interoperability checks

The CI test builds the actual RKC at pinned commit `37a908e9f99cc246d8185bdc202981c0b55e9ef5`, compiles a small fictional collection, imports its bundle, starts the local read API and checks context/citation handling. Its receipt records the tested snapshot and revision. No live AI call or private repository source is used.

The browser test separately exercises import, local selection and the transfer-consent boundary. Test fixtures are not a claim that every historical or future atlas schema is supported.
