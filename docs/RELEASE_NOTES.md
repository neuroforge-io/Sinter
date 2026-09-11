# Sinter 0.4 - Community desktop preview

Interpreter-bundled installers, a configurable local workbench, everyday community tools and optional RKC knowledge workflows.

## Downloads

- Windows: x64, x86 and ARM64 per-user installers.
- macOS: Intel x64 and Apple Silicon ARM64 `.pkg` applications.
- Debian/Ubuntu Linux: x64, x86, ARM64 and ARMv7 `.deb` packages and portable runtime archives.
- Source ZIP and Python zipapp for source-based use and optional speech installation.

All nine targets must build and run installed-app smoke checks before this release is published. x86 runs use host compatibility execution; ARMv7 is tested under QEMU, not physical hardware. Per-target receipts, `build-manifest.json` and `SHA256SUMS.txt` record the exact source and hashes.

**Preview packages are not publisher-signed or notarised.** macOS app bundles are ad-hoc signed only. OS policy may warn or block installation; do not disable protections. Python is bundled for core desktop use, but speech engines, RKC and model weights are not. Optional speech uses a source installation. The UI opens in your existing browser; it is not a separate embedded browser engine.

Linux x64/ARM64 require glibc 2.35+; Bookworm x86/ARMv7 packages require glibc 2.36+. Windows requires Windows 10+; native ARM testing uses Windows 11. macOS Intel/ARM validation uses macOS 15/14. No modern 32-bit macOS or Windows ARM32 support is claimed.

## Useful additions

Local preferences for theme, reading size, layout and reduced motion; session-only API keys and configurable compatible endpoints; action/volunteer plans with CSV/JSON/calendar exports; line-oriented document comparison; eight community drafting recipes; optional RKC bundle/context import, bounded selected-file compilation and Fracture-assisted knowledge drafts.

## Trust boundaries

Exact excerpts establish provenance, not truth. Generative recipes and atlas answers are unverified drafts. Fracture operates as a Sinter sidecar over RKC context, not as an internally qualified RKC provider. Canonical atlas evidence is unchanged. Saved data is unencrypted; API transfer is explicit and scheduled searches run only while Sinter is open. No official letters or applications are sent automatically.

The public API is a capacity-limited preview, not a service-level guarantee. No proprietary ERAIS/Fracture implementation or model weights are bundled. Sinter source remains Apache-2.0; runtime components and optional packages retain their own licences.
