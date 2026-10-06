# Runtime and build notices

Sinter source is Apache-2.0; retain LICENSE and NOTICE. Native installers add
an unmodified Python runtime and PyInstaller bootloader. Their licences are
separate from Sinter and included under `licenses/` in each installed app.
Python retains the Python Software Foundation licence and its bundled library
notices. PyInstaller is GPL-2.0-or-later with an exception allowing its bootloader
to be distributed with applications under their own terms; Sinter source is
not relicensed by the packaging step.

On supported account-verification targets, desktop packages also include PyJWT
(MIT), cryptography (Apache-2.0 or BSD-3-Clause), cffi (MIT), and pycparser
(BSD-3-Clause). Their original licence files, all cryptography licence variants,
exact distribution versions and licence-file digests are included under
`licenses/`, with an inventory in `licenses/bundled-dependencies.json`. Each
installed-app receipt states whether account verification is bundled and records
an offline signed-token verification test. That test does not claim a live
ChatGPT account connection or provider approval.

Python 3.10 account builds also include typing_extensions (PSF-2.0), required by
the current PyJWT release. Its version and original licence are recorded in the
same inventory.

Windows 32-bit, Windows ARM64 and Intel macOS preview packages omit those account
verification libraries because the current cryptography release does not support
those binary targets. Their local tools and API-key connections remain available.
The portable core zipapp includes no third-party Python dependencies; source
users may install the optional `accounts` extra on a compatible environment.

Runtime libraries such as OpenSSL, SQLite, libffi, bzip2, xz and zlib retain their
respective upstream licences. The Python runtime licence and original notices
provided by the packaged dependencies are included in `licenses/`. Build tools
are not a grant of rights to the user's sources, RKC atlases, recordings or model
assets.

Linux packages also record every copied shared library's byte-matched origin.
The inventory includes the owning Debian/Ubuntu package's version, original
copyright notice and referenced common licence texts, with file digests.
The Python shared library is bound to its originating interpreter and Python
licence. Unused Python readline support is excluded from desktop bundles.
Missing or altered notices and incomplete library coverage stop packaging and
the release gate; this Linux-specific check does not qualify other platforms.

Optional faster-whisper, CTranslate2, PyAV, tokenizers, Hugging Face components,
speech model assets and the optional RKC application retain their own licences.
Core installers do not bundle those packages, speech models or RKC. No proprietary
ERAIS/Fracture implementation is included. Using Fracture is an API connection,
not redistribution of its server or model weights.

Windows installer: Inno Setup, Copyright Jordan Russell and Martijn Laan.
Installer tooling and publisher signing are independent of Sinter's source licence.
These initial packages are unsigned by a publisher; macOS bundles are ad-hoc
signed for runtime integrity, not notarised. Do not disable OS security checks.

## Browser edition

The browser edition self-hosts Pyodide 0.29.3 and the matching CPython/SQLite/OpenSSL
WebAssembly packages from the official Pyodide distribution. Versioned asset hashes
are in browser/vendor-sha256.json. Pyodide's Mozilla Public License 2.0 is included
in browser/PYODIDE-LICENSE and distributed with the browser assets. Package archives
retain their original metadata and third-party licence files.

Upstream source and notices: https://github.com/pyodide/pyodide/tree/0.29.3
Python licence: https://docs.python.org/3.13/license.html
SQLite is public domain: https://sqlite.org/copyright.html
OpenSSL 1.1.1 licence: https://github.com/openssl/openssl/blob/OpenSSL_1_1_1w/LICENSE
