# Install Sinter

[Back to Sinter](../README.md)

## The simplest route: a desktop package

Choose an actual published asset from [Releases](https://github.com/neuroforge-io/Sinter/releases). Versioned assets include a runtime, local interfaces, original licence notices and build receipts. The current rc3 app defaults to a native source workspace. Its full campaign, scoped casebook, rich-document and account sign-in screens use the explicit browser mode below. The previous rc2 package keeps its browser default.

The current [0.5.4rc3 preview](https://github.com/neuroforge-io/Sinter/releases/tag/v0.5.4rc3)
qualifies **Linux x64 on Ubuntu 22.04/glibc 2.35 only**. Choose its
[Debian/Ubuntu installer](https://github.com/neuroforge-io/Sinter/releases/download/v0.5.4rc3/Sinter-0.5.4rc3-linux-x64.deb)
or [native runtime archive](https://github.com/neuroforge-io/Sinter/releases/download/v0.5.4rc3/Sinter-0.5.4rc3-linux-x64.tar.gz).
The exact package source is `246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe`.
Windows, macOS and other Linux architectures have no qualified rc3 installer.
The platform descriptions below explain the packaging machinery and earlier
downloads; they do not qualify additional rc3 targets. See
[public download and installed workflow evidence](releases/PREVIEW_0.5.4rc3_PUBLICATION_RECEIPT.md).

After installing the Debian package, open the full workbench with:

```sh
/opt/neuroforge/sinter/Sinter app --mode browser
```

From its Overview, choose **Open garden handover** or **Open garden campaign**.
The fictional walkthrough needs no account, internet or downloaded model. The
application-menu entry opens the smaller native source workspace; its repeat
launch and shutdown are qualified separately from the full browser workflow.

Windows: choose `windows-x64-setup.exe` for most Intel/AMD PCs, `windows-arm64-setup.exe` for an ARM64 installation, or `windows-x86-setup.exe` for a 32-bit installation. Run it as your normal user; it installs under Local AppData and creates a Start menu entry. Desktop shortcuts are optional. Uninstall through Installed apps.

macOS: choose `darwin-arm64.pkg` for Apple Silicon or `darwin-x64.pkg` for an Intel Mac. The package installs `/Applications/Sinter.app`. Open it from Applications. There is no 32-bit macOS package. Remove the app using normal administrator-approved software management when it is no longer needed.

Debian/Ubuntu: open the `.deb` for your architecture in your software installer. An application-menu entry launches Sinter. Package-manager installation/removal requires the usual administrator permission. A `.tar.gz` runtime archive is also available for compatible Linux environments; it is not a universal binary for every distribution.

Debian prerelease package versions use `~` so ordinary updates can install the
later final release: app/download version `0.5.4rc3` has package-manager version
`0.5.4~rc3`. The native receipt records both identities.

Separate actual package replacements from published v0.5.3, v0.5.4rc1 and v0.5.4rc2 were
tested on copied fictional workspaces. Saved work, original sources, preferences
and explicit model selections survived. Before upgrading your own installation,
save current work and export backups. Quit Sinter, then install the new `.deb`
using normal software controls; no uninstall or workspace reset is needed for
the tested upgrade paths. This test does not replace customer-device acceptance.

These preview packages are **not publisher-signed or notarised**. macOS application bundles are ad-hoc signed for integrity, not verified publisher identity. A managed machine can refuse them. Do not disable operating-system protections; follow your organisation's policy or use an approved source installation.

## What is included?

The core workbench, settings, source-linked reports, transcript import/review, community tools, optional RKC adapters, Python and browser assets are included. No API account is required for local examples.

Speech engines, model weights and the RKC executable are **not** bundled. Optional transcription currently uses a source checkout with the speech extra. Importing an existing TXT/SRT/VTT/JSON transcript works in the core installer. RKC atlas import works without installing RKC; creating atlases or reading its live local context needs RKC separately.

ChatGPT sign-in requires the bundled account-verification libraries. Current
native build targets include them on Windows x64, Apple Silicon and Linux.
Windows x86, Windows ARM64 and Intel macOS builds omit them because current
cryptography binary support is unavailable; those builds explain the limitation
in Settings. Provider API keys and compatible local models are still available.
The installed-app receipt's `account_auth_bundled` field is authoritative for a
download. An offline signed-token test proves the bundled verifier can run; it
does not prove a live ChatGPT sign-in or access for your account.

## Word save recovery in rc3

Beside a draft's normal download, open **Word save options** and choose **Save
Word copy on this computer**. Sinter creates a distinct verified local file and
shows its path for your file manager or Word editor. Apply or cancel pending
edits first. This saves the wording applied to the document; it does not save
later edits back to the Sinter workspace or mark the content reviewed.

Copies remain in the workspace's `exports` folder after closing Sinter
(normally `~/.sinter/exports` on Linux). After an interrupted or unconfirmed save,
inspect that folder before an explicit retry: a copy may already exist. Existing
files are never replaced and requests are never automatically replayed. Direct
saving requires supported safe local filesystem operations; other builds can
use the ordinary download or copy controls. The actual rc3 Linux workflow
qualifies three local Word copies, including changed wording and an unconfirmed
save without replay. Ordinary customer-browser download delivery remains
unqualified. Earlier rc2 installers do not include local Word-copy recovery.

## Platform qualification

Development campaign backups that contain `source_history` need a preview with
historical-source support. Published RC3 and other older strict importers reject
unsupported fields; they do not silently drop the snapshots. Export and retain
your full backup before changing previews. Local drafts for an unconfirmed
applicant stay in the full backup but are held out of shared campaign briefs.

Current RC4 candidate source is version `0.5.4rc4`; an RC4 installer is not yet
qualified or published. Source CI results do not establish installed operation.
On 9 October, the frozen Linux candidate at
`4cab335e60bbeaceabd6910cf4a453454020eb2c` passed the installed garden workflow
and both recovery profiles. Its four-launch native baseline passed, but the full
browser handoff failed before complete source inspection. Later cancellation and
close journeys were not reached; cold installation and prior-preview replacement
were not run. Later source harness repairs need fresh qualification and do not
qualify that frozen installer. The published RC3 Linux preview remains the
available qualified download and is unchanged. See the
[dated qualification record](QUALITY_REVIEW_2026-09-12.md).

The table below declares the CI build/test environments. It is not a pass matrix
for every candidate. Earlier v0.5.3, RC1 and RC2 packages have separate evidence;
consult [0.5.4rc3 qualification](releases/PREVIEW_0.5.4rc3_PUBLICATION_RECEIPT.md)
before treating a platform as tested.

The exact rc3 Linux Python and Chromium jobs passed, but aggregate Quality
failed. Windows test-fixture encoding/platform assumptions and a genuine macOS
failure during concurrent local Word saves remain unresolved. The macOS cause
and its reachability elsewhere are unproven. Other platforms and customer-device
acceptance remain unqualified; no stable all-platform release is claimed.

| Target | Build / installed-app execution |
| --- | --- |
| Windows x64 | Windows Server 2022 x64 runner, Python 3.13 |
| Windows x86 | 32-bit Python 3.13 under Windows x64 compatibility mode |
| Windows ARM64 | Windows 11 ARM runner, native ARM64 Python 3.13 |
| macOS Intel | macOS 15 Intel runner, Python 3.13 |
| macOS Apple Silicon | macOS 15 ARM64 runner, Python 3.13 |
| Linux x64 / ARM64 | Ubuntu 22.04 target runners, Python 3.13; glibc baseline recorded |
| Linux x86 | Debian Trixie 32-bit userspace, Python 3.11, host compatibility execution |
| Linux ARMv7 | Debian Bookworm armhf userspace, Python 3.11, QEMU emulation |

Actual release receipts are authoritative for the build in your download. Windows installer minimum is Windows 10. macOS tests are not a claim of support for every earlier release. Linux 64-bit Ubuntu-built packages require glibc 2.35 or newer; ARMv7 Bookworm packages require glibc 2.36 or newer; x86 Trixie packages require glibc 2.41 or newer. Check the specific receipt and package dependencies. ARMv7 has not been validated on physical boards in this release.

Checks install the package, start the installed executable, serve its assets and exercise offline workflows. Windows and Linux checks also remove it. These checks do not establish real meeting accuracy, current hosted API availability or automatic operating-system trust.

## Open, close and keep your work

Choose **Try an example** for a fictional offline demonstration. Use **Settings** for reading size, theme, motion and connection choices.

Current development source starts Overview and Getting started with **Open garden
handover**. Inspect its four original sources, choose **Prepare source-only
report**, check **Evidence** and edit the draft. **Save project** keeps inputs;
**Save to My workspace** keeps the edited report. Wait for the Saved confirmation.
On a narrow screen, use **Find a tool** to open My workspace or Community casebooks.
Export project inputs and edited documents separately. This clearer guidance
does not change the published installer or browser source pins.

In the rc3 browser workbench, Overview and Getting started
also offer **Open garden handover** and **Open garden campaign**. These open the
complete bundled fictional project without a file picker. Saved projects stay
unchanged; opening starts an unsaved copy and switching the paired editors resumes
your current session edits. The frozen 0.5.4rc1 installers do not include this newer
entry; their walkthrough uses the supplied JSON backups instead.

Browser mode selects an available local port. Keep it running for watch checks.
Use **Quit Sinter** in its navigation to stop the local process; closing a browser
tab alone does not stop it. Closing the native source window stops its own jobs
and process. Source-launcher users can press Ctrl+C in the terminal.

Reports and preferences are local and unencrypted. Unsaved browser work is not a backup. Export or save before quitting. Uninstalling a core application does not delete `~/.sinter`; remove that directory only after preserving any reports you need. Model caches are managed separately by the optional speech tools.

### Development Linux launcher change

Linux packages built from current development source give **Sinter** an explicit
full community-workbench launcher. No terminal command is needed for that menu
entry. Packages with Tk also provide **Sinter native source workspace** for the
smaller offline interface. Both use the same runtime and saved-work directory;
the bare executable and source wrappers still default to native mode.

The full workbench opens a loopback address in a local browser. A browser's
acceptance of the launch does not prove that a restricted environment permits
that address. Keep its protections in place and choose the native alternative
where appropriate. Use **Save project** for inputs and **Save to My workspace**
for edited reports. Wait for the Saved confirmation, then choose **Quit Sinter**.
Development Quit stays visible at phone widths. If there are unsaved browser
inputs, choose **Keep working** or explicitly quit in its in-page dialog. The
native-owned workbench requests confirmation in the Sinter window and keeps
browser inputs while it decides. An unconfirmed reply keeps your browser inputs;
check whether Sinter is running before explicitly retrying. Closing a browser tab
alone does not stop the installed app. Quit before opening it again.

This is a development packaging change, not a change to the published RC3
assets or their pinned instructions. Matching installed first-run evidence and
a separately qualified publication must precede customer download claims.

The rc3 browser workbench includes **On hold** for actions and a complete
local backup-text fallback. Earlier previews refuse to open a campaign containing
held actions. Keep an independent backup before switching versions and use rc3
for those records. Clipboard copying requires you to paste and retain the text
yourself; it does not establish that a file exists or that a campaign was saved.

The rc3 browser workbench also supports explicit source choices for individual casebook questions.
These scoped projects use casebook v2 and are stored separately to prevent older
previews from silently discarding the choices. Older previews cannot show those
projects or restore v2 backups. Keep an unchanged workspace copy before upgrading;
return to a supporting version to use the newer work. Clearing all source choices
is an explicit change to an unscoped project, not an automatic downgrade.
Casebook backup text can also be selected and retained manually when downloads
or clipboard access fail. Add or clear a pending source first. Copying captures
inputs at that moment; it does not save the project or create a file.

## Source and speech installation

Python 3.10+ is required for a source installation. The native window also needs
Tk and a working display; the full web workbench needs a current browser. CLI
workflows need neither a browser nor a display.

```sh
git clone https://github.com/neuroforge-io/Sinter.git
cd Sinter
python3 start.py
```

With no arguments, `start.py` opens the native source workspace. Windows uses `py start.py`
or `Start-Sinter.bat`; macOS can use `Start-Sinter.command`, and Linux can use
`./start-sinter.sh`. The platform wrappers prefer `.venv` when present and pass
arguments through, including paths containing spaces.

On Windows, `Start-Sinter.bat` uses the project's `.venv` first. Otherwise it
prefers a working Python 3.10+ executable on PATH, so an activated environment or
your PATH choice takes precedence over the registered latest minor version.
It checks an installed runtime layout before probing it; Store and install-manager
aliases are not launched as Python. If needed, it reads `py -0p` and directly
uses a working installed runtime from an ordinary CPython listing. Discovery does
not request a runtime download. An error after Sinter starts preserves its exit
code and never triggers a second launch.

Nonstandard shims, custom registered executable arguments and unrecognised listing
formats are not selected automatically. For those configurations, invoke your
chosen interpreter explicitly with `start.py`. An existing but broken project
`.venv` remains authoritative; repair it or choose an explicit interpreter rather
than expecting the wrapper to switch silently. Runtime selection does not establish
Tk availability or qualify Windows installed packages.
Registered fallback follows the admitted listing order; it does not reproduce
every `PY_PYTHON3` or `py.ini` minor-version preference. Use an explicit interpreter
when that preference is essential.

Current source and rc3 packages default to a native Tcl/Tk source workspace.
It requires a working display and Python's Tk support; it gives a clear error
when these are unavailable. Use `python3 start.py app --mode browser` for the
full web workbench, or shared CLI operations in headless environments. Published
rc2 downloads keep their browser launch. See [the portable runtime guide](PORTABLE_RUNTIME.md)
for the native scope and CLI workflows.

Source choices for individual casebook questions use the web workbench
and lossless CLI/Python paths. The native source window refuses these newer
projects instead of clearing their choices. The rc3 browser presentation includes
this capability. A Linux package deliberately built without the
native window uses an explicit browser-mode application-menu command; that
source behavior still needs matching installed qualification.

Explicit help, version and commands retain their CLI meaning: `python3 start.py
--help`, `python3 start.py --version`, or `python3 start.py serve --no-browser
--port 9000`. A bare installed `sinter` or `python -m sinter` prints help and exits;
use `sinter app` for the native workspace or `sinter serve` for the web workbench.

For speech recognition, stop Sinter and run `python3 setup_speech.py` (`py setup_speech.py` on Windows). The helper asks before installing into `.venv`; it does not install a model without the later model-download choice. See [transcription](TRANSCRIPTION.md).

For a previously installed Python package, reinstall after pulling changes (`.venv/bin/python -m pip install .`, or the Windows equivalent). Launching `start.py` directly always uses the checkout's source.

## Publishing the site

The static page is in `site/`. It never accepts private context and only requests public release metadata. The repository's `Public Sinter site` workflow deploys that folder to GitHub Pages on relevant main-branch changes.

One-time administrator setup: **Settings > Pages > Build and deployment > Source: GitHub Actions**. Then run the `Public Sinter site` workflow. The workflow intentionally has no administrator token and does not bypass repository settings. Its successful deployment reports the actual site URL; the expected project address is `https://neuroforge-io.github.io/Sinter/` once enabled.

A missing Pages setting is not a failed application build. Release downloads remain available through GitHub Releases independently.

## Building releases

`Native installers` builds nine targets using `tools/package_native.py`. `Sinter quality` runs the core, browser, real speech and RKC integration tests. `Publish tested community release` calls both workflows at a new main-branch version and publishes a preview only after every required job succeeds.

The publisher checks all nine installer receipts, source commit identity and SHA-256 digests before attaching files. It does not overwrite an existing release. `SHA256SUMS.txt` and `build-manifest.json` accompany the packages. This is artifact integrity and test provenance, not publisher code signing.

The Linux-only rc3 preview uses a separate explicit candidate gate. Its
`candidate-release-manifest.json` binds the exact source, installer, runtime
archive and qualification pack. All three prior-preview upgrades, the frozen
executable's 21-check offline browser journey and installed recovery are
mandatory, with separate bare cold-install and mapped native-display evidence.
This does not pass or bypass the
full nine-target publisher; development and candidate versions are excluded from
its automatic publication path.
