# Relocatable local audio runtime — 25 November 2026

## What changed

`scripts/install_sinter_native.py` now writes a **self-contained source
snapshot** beside the worker launcher:

```text
~/.local/share/sinter/erais-audio/
    manifest.json              runtime identity and digests
    worker.sh                  $BASE-relative launcher
    speech-manifest.json       selected model identity
    speaker-encoder.onnx       CAM++ when clustering is enabled
    runtime/
        erais/                 pinned package snapshot (3,121 files, 73.9 MiB at 4cf17e04)
```

The launcher resolves its own directory and uses `$BASE/runtime` on
`PYTHONPATH`. It no longer references the ERAIS development checkout. A
supplied speech manifest is copied into the install directory, so the runtime
does not depend on the file it was installed from either.

`manifest.json` records `self_contained_source` and `runtime_bundle`
(`tree_sha256`, `files`, `bytes`). `--no-bundle-runtime` retains the previous
development-checkout mode for editing. `--verify` recomputes the tree, model and
speaker digests and re-runs the launcher import check without changing
anything.

## Relocation evidence

Installed on the desktop, copied to `/tmp/relocated-audio`, then executed from
`/tmp`:

```text
erais.__file__
  /tmp/relocated-audio/runtime/erais/__init__.py
sinter_worker.__file__
  /tmp/relocated-audio/runtime/erais/integration/sinter_worker.py
worker exit code                 0
events                           7
segments                         5
last segment end                 21.74 s
```

The input was a 30 s 44.1 kHz stereo MP3; output matched the in-place install
exactly (same five segments and final end time).

## What is still not standalone

- **Python and dependencies are not bundled.** The launcher still names the
  host interpreter that supplies `numpy`, `onnxruntime`, `torch`, `librosa`,
  `scipy` and `soundfile`. A truly one-click install still needs a frozen or
  embedded interpreter per platform.
- Models are referenced by absolute path and are not copied by default.
- There is no signature/trust root on the snapshot yet; the manifest carries
  digests but not a verified publisher signature.
- Upgrade is now atomic enough to recover from a bad install: the previous
  source tree is kept as `runtime.previous`, a valid `manifest.json` is copied
  to `manifest.previous.json` only after the new launcher passes its import
  check, and `install_sinter_native.py --rollback` swaps them back and verifies
  the restored launcher. Model files are shared by absolute path, so a rollback
  does not revert a model swap.
- Linux x86-64 only; Windows and macOS remain unqualified.

## Verification

```text
tests/test_install_sinter_native.py   11 passed
  including a bundled-snapshot test that runs the launcher from a foreign
  working directory with no repository PYTHONPATH
```
