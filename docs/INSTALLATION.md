# Install Sinter

[Back to Sinter](../README.md)

## The simplest route: a desktop package

Choose an actual published asset from [Releases](https://github.com/neuroforge-io/Sinter/releases). Versioned assets include a runtime, web interface, original licence notices and build receipts. The default experience is local and opens in your existing browser, without installing another browser engine.

Windows: choose `windows-x64-setup.exe` for most Intel/AMD PCs, `windows-arm64-setup.exe` for an ARM64 installation, or `windows-x86-setup.exe` for a 32-bit installation. Run it as your normal user; it installs under Local AppData and creates a Start menu entry. Desktop shortcuts are optional. Uninstall through Installed apps.

macOS: choose `darwin-arm64.pkg` for Apple Silicon or `darwin-x64.pkg` for an Intel Mac. The package installs `/Applications/Sinter.app`. Open it from Applications. There is no 32-bit macOS package. Remove the app using normal administrator-approved software management when it is no longer needed.

Debian/Ubuntu: open the `.deb` for your architecture in your software installer. An application-menu entry launches Sinter. Package-manager installation/removal requires the usual administrator permission. A `.tar.gz` runtime archive is also available for compatible Linux environments; it is not a universal binary for every distribution.

These preview packages are **not publisher-signed or notarised**. macOS application bundles are ad-hoc signed for integrity, not verified publisher identity. A managed machine can refuse them. Do not disable operating-system protections; follow your organisation's policy or use an approved source installation.

## What is included?

The core workbench, settings, source-linked reports, transcript import/review, community tools, optional RKC adapters, Python and browser assets are included. No API account is required for local examples.

Speech engines, model weights and the RKC executable are **not** bundled. Optional transcription currently uses a source checkout with the speech extra. Importing an existing TXT/SRT/VTT/JSON transcript works in the core installer. RKC atlas import works without installing RKC; creating atlases or reading its live local context needs RKC separately.

## Platform qualification

| Target | Build / installed-app execution |
| --- | --- |
| Windows x64 | Windows Server 2022 x64 runner, Python 3.13 |
| Windows x86 | 32-bit Python 3.13 under Windows x64 compatibility mode |
| Windows ARM64 | Windows 11 ARM runner, native ARM64 Python 3.13 |
| macOS Intel | macOS 15 Intel runner, Python 3.13 |
| macOS Apple Silicon | macOS 14 ARM64 runner, Python 3.13 |
| Linux x64 / ARM64 | Ubuntu 22.04 target runners, Python 3.13; glibc baseline recorded |
| Linux x86 | Debian Bookworm 32-bit userspace, Python 3.11, host compatibility execution |
| Linux ARMv7 | Debian Bookworm armhf userspace, Python 3.11, QEMU emulation |

Actual release receipts are authoritative for the build in your download. Windows installer minimum is Windows 10. macOS tests are not a claim of support for every earlier release. Linux 64-bit Ubuntu-built packages require glibc 2.35 or newer; the Bookworm 32-bit packages require glibc 2.36 or newer. Check the specific receipt and package dependencies. ARMv7 has not been validated on physical boards in this release.

Checks install the package, start the installed executable, serve its assets and exercise offline workflows. Windows and Linux checks also remove it. These checks do not establish real meeting accuracy, current hosted API availability or automatic operating-system trust.

## Open, close and keep your work

Choose **Try an example** for a fictional offline demonstration. Use **Settings** for reading size, theme, motion and connection choices.

The desktop app selects an available local port. Keep the app running for watch checks. Use **Quit Sinter** in its navigation to stop the local process; closing a browser tab alone does not stop it. Source-launcher users can press Ctrl+C in the terminal.

Reports and preferences are local and unencrypted. Unsaved browser work is not a backup. Export or save before quitting. Uninstalling a core application does not delete `~/.sinter`; remove that directory only after preserving any reports you need. Model caches are managed separately by the optional speech tools.

## Source and speech installation

Python 3.10+ and a current browser are needed for a source installation:

```sh
git clone https://github.com/neuroforge-io/Sinter.git
cd Sinter
python3 start.py
```

With no arguments, `start.py` opens the local workbench. Windows uses `py start.py`
or `Start-Sinter.bat`; macOS can use `Start-Sinter.command`, and Linux can use
`./start-sinter.sh`. The platform wrappers prefer `.venv` when present and pass
arguments through, including paths containing spaces.

Explicit help, version and commands retain their CLI meaning: `python3 start.py
--help`, `python3 start.py --version`, or `python3 start.py serve --no-browser
--port 9000`. A bare installed `sinter` or `python -m sinter` prints help and exits;
use `sinter serve` to open the workbench from those entry points.

For speech recognition, stop Sinter and run `python3 setup_speech.py` (`py setup_speech.py` on Windows). The helper asks before installing into `.venv`; it does not install a model without the later model-download choice. See [transcription](TRANSCRIPTION.md).

For a previously installed Python package, reinstall after pulling changes (`.venv/bin/python -m pip install .`, or the Windows equivalent). Launching `start.py` directly always uses the checkout's source.

## Publishing the site

The static page is in `site/`. It never accepts private context and only requests public release metadata. The repository's `Public Sinter site` workflow deploys that folder to GitHub Pages on relevant main-branch changes.

One-time administrator setup: **Settings > Pages > Build and deployment > Source: GitHub Actions**. Then run the `Public Sinter site` workflow. The workflow intentionally has no administrator token and does not bypass repository settings. Its successful deployment reports the actual site URL; the expected project address is `https://neuroforge-io.github.io/Sinter/` once enabled.

A missing Pages setting is not a failed application build. Release downloads remain available through GitHub Releases independently.

## Building releases

`Native installers` builds nine targets using `tools/package_native.py`. `Sinter quality` runs the core, browser, real speech and RKC integration tests. `Publish tested community release` calls both workflows at a new main-branch version and publishes a preview only after every required job succeeds.

The publisher checks all nine installer receipts, source commit identity and SHA-256 digests before attaching files. It does not overwrite an existing release. `SHA256SUMS.txt` and `build-manifest.json` accompany the packages. This is artifact integrity and test provenance, not publisher code signing.
