# Runtime and build notices

Sinter source is Apache-2.0; retain LICENSE and NOTICE. Native installers add
an unmodified Python runtime and PyInstaller bootloader. Their licences are
separate from Sinter and included under `licenses/` in each installed app.
Python retains the Python Software Foundation licence and its bundled library
notices. PyInstaller is GPL-2.0-or-later with an exception allowing its bootloader
to be distributed with applications under their own terms; Sinter source is
not relicensed by the packaging step.

Runtime libraries such as OpenSSL, SQLite, libffi, bzip2, xz and zlib retain their
respective upstream licences. The Python distribution's licence file contains
notices for incorporated third-party components. Build tools are not a grant
of rights to the user's sources, RKC atlases, recordings or model assets.

Optional faster-whisper, CTranslate2, PyAV, tokenizers, Hugging Face components,
speech model assets and the optional RKC application retain their own licences.
Core installers do not bundle those packages, speech models or RKC. No proprietary
ERAIS/Fracture implementation is included. Using Fracture is an API connection,
not redistribution of its server or model weights.

Windows installer: Inno Setup, Copyright Jordan Russell and Martijn Laan.
Installer tooling and publisher signing are independent of Sinter's source licence.
These initial packages are unsigned by a publisher; macOS bundles are ad-hoc
signed for runtime integrity, not notarised. Do not disable OS security checks.
