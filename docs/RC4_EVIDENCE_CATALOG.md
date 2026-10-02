# RC4 retained-evidence transport

`tools/rc4_evidence_catalog.py` reads a finite, externally approved catalog from
an extracted evidence tree. It returns original bytes and scoped metadata. It
cannot validate a semantic gate, establish historical qualification, or assert
installed execution. Its records always identify themselves as transport only
and set those three claims to `false`.

The caller supplies both the exact SHA-256 of `catalog.json` and strict UTF-8
authority JSON bytes from an independent approval. A receipt-supplied role list,
a self-resealed catalog, or an admission boolean is not approval. The caller
must approve the complete inventory for the intended gates before invoking this
reader. This module does not decide which evidence those gates require.

## Closed authority and index

Authority has exactly these fields:

```json
{
  "schema": "sinter-rc4-evidence-authority/v1",
  "identities": [{"name": "source", "kind": "git-commit", "value": "FULL_COMMIT"}],
  "labels": [{"scope": "gate/phase", "name": "original", "namespace": "host", "value": "/original/opaque/path"}],
  "roles": [{"scope": "gate/phase", "role": "raw-receipt", "identity": "source", "label": "original", "bytes": 1, "sha256": "FULL_SHA256"}],
  "directories": ["blobs", "empty", "empty/runtime"]
}
```

The example placeholders must be replaced by a lowercase 40-character commit
and a lowercase 64-character SHA-256. Identity kinds are `git-commit`, `sha256`,
and `text`; their names are unique. Labels are unique by `(scope, name)` and have
namespace `host` or `container`. Roles are unique by `(scope, role)` and refer to
an approved identity and a label in the same scope. Every identity and label
must be used. No receipt can add an unknown field, role, identity, or directory.

The index has precisely the same schema and values, except its schema is
`sinter-rc4-evidence-catalog/v1`. JSON object key order and inventory list order
may differ; the external index digest still pins its exact bytes. Duplicate
JSON fields, invalid UTF-8, unknown or missing fields, wrong builtin types,
floats, nonfinite numbers, and conflicting deduplicated sizes refuse. The only
numeric field is a nonnegative builtin integer byte count; booleans refuse.

The retained physical tree contains exactly `catalog.json`, one regular file
`blobs/<sha256>` for each unique digest, and every explicitly approved directory.
Directories include all ancestors and all required empty directories. Names
are canonical relative POSIX strings, parsed with `PurePosixPath`; absolute
paths, backslashes, NUL, dot components and parent traversal refuse. Extra,
missing, repeated, linked or special entries refuse before payload reads.
Regular files with more than one hard link also refuse.

Several independently scoped roles can refer to one identical physical blob.
Deduplication preserves every role, identity and opaque original label; it does
not remove required evidence. Original host/container labels are UTF-8 data:
they are never normalized, interpreted, opened, rewritten or symlinked. A label
containing an absolute path, literal braces, a newline or `..` remains opaque.

Every retained member, including the index, is at most 64 MiB. The index plus
the sum of unique physical blobs is at most 256 MiB. The authority parser also
accepts at most 64 MiB of JSON. Enumeration is bounded by the finite approved
entry set and stops at the first unknown or repeated entry before payload reads.
There is no extra small role or directory count limit. These controls do not
prove that the eventual complete four-prior and all-gate evidence inventory
fits the existing bounds; that remains a final-inventory qualification step.

## Read-only API and platform boundary

```python
from tools.rc4_evidence_catalog import Catalog

reader = Catalog(extracted_root, index_sha256=approved_pin, authority=approved_bytes)
raw = reader.read_role("gate/phase", "raw-receipt")
original = reader.original_label("gate/phase", "original")
identity = reader.identity("source")
transport_record = reader.records()
```

Construction and `records()` recheck the complete inventory, pinned index and
every unique blob's exact size and SHA-256. Inventory is checked before and after
those reads. `read_role()` rechecks the inventory before and after its reads,
checks the index, and returns only the requested role's verified bytes. It does not
assert a new whole-catalog or semantic decision. Metadata lookups return the
already approved opaque labels and identities; they make no filesystem read.
Every returned record is a fresh value with transport-only claims.

The portable `validate_authority()` schema and authority controls do not need
POSIX resources. Physical reads require descriptor-relative `open`, `stat` and
directory enumeration, `O_NOFOLLOW`, and `O_DIRECTORY`. Unsupported hosts raise
`UnsupportedReader`; they do not get a weaker pathname reader. Physical tests
are narrowly marked for those capabilities, while portable hostile schema and
authority controls run everywhere.

The physical reader opens each actual root and directory component with
no-follow directory descriptors, checks regular file identity and size before
and after opening, and hashes bounded complete reads. It has no writer, archive
extractor, subprocess, network, command dispatcher, dynamic archive import, or
original-label pathname API. Retained source code is data even if its contents
are executable. The actual root accepts only a builtin string or concrete host
`Path`, refusing arbitrary `PathLike` callbacks, NUL and ambiguous parents. The
extraction root and its ancestors must be stable for the
read; this does not claim an atomic snapshot against a concurrently privileged
filesystem writer or mount replacement. Catalog checks are repeated on each
byte lookup and whole-catalog record request.

Every opened descriptor is closed even when a read fails. If close operations
also fail, the original error remains primary and its `cleanup_errors` tuple
retains all close errors. Without a primary error, a `CatalogError` retains that
same complete tuple. The fault controls use injected close failures; they do not
claim actual kernel close faults were induced.

Gate-specific pure validators, retained raw lifecycle and diagnostic semantics,
actual installed producer runs and independent before/after instrumentation
remain separate future work. External Chrome/Node executables, host browser
libraries and Docker infrastructure are outside the retained customer payload
boundary. This transport neither requires their binaries nor proves their
reproducibility. Required DEB, customer dependency, notice and runtime payload
bytes must be included by the eventual independently approved role inventory.
No old RC1–RC3 policy is widened by this new module.
