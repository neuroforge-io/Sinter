# Published Linux x64 preview — 30 September 2026

[Sinter 0.5.4rc1](https://github.com/neuroforge-io/Sinter/releases/tag/v0.5.4rc1)
was published at `2026-09-30T05:00:22Z`, GitHub release ID `399731221`.
Its lightweight tag directly identifies
`cd928ba7561a09c477b3555e64aa6a3c4cc122b4`. It is a prerelease, with
`latest=false`. The human owner authorised publication of qualified ready packs.

## Available files

| File | SHA-256 |
| --- | --- |
| `Sinter-0.5.4rc1-linux-x64.deb` | `31f64e2af6693a21b31c6296ee41aad68516238d6a9d4f34990e91632eb2a08d` |
| `Sinter-0.5.4rc1-linux-x64.tar.gz` | `fda69d445e2a8fc32615f59e69c77fe1510700f01b2a7f98afd427c89ec1cd0c` |
| `sinter-0.5.4rc1-source.zip` | `873d539cb7d7d1de9b983283f3c5f20b28f6585b84c16b320920a236bf1dcf96` |
| `sinter-0.5.4rc1.pyz` | `fc265c2e5b1f2bdf5f1a08e69f94d6e21065c72ba6664d230388b72c8b04e92f` |
| `sinter-0.5.4rc1-qualification.zip` | `14d176cab0027cc50fd9623f5061cf87c422e3b99fdf119a797572084c50c1f5` |
| `RELEASE-NOTES.md` | `163b5afd0b2f777022f44e453660a678fe68d3bcbc2cc35f34f2fcfa4dc95708` |
| `candidate-release-manifest.json` | `5fe210903f1de32a35485fe24170ef1aa18fe6b9a187fb5826eee47f65f56106` |

`SHA256SUMS.txt` is the eighth attachment and covers the other seven files.
Every public attachment was downloaded into a fresh directory, compared
byte-for-byte with the verified v3 stage and rechecked through the full scoped
candidate verifier. The downloaded portable app reported `sinter 0.5.4rc1` under
isolated Python without installed dependencies. This proves download integrity;
installed qualification comes from the separate retained runtime evidence.

The v3 notes accurately call v0.5.3 a published preview. Application files and
the qualification ZIP are identical to the independently reviewed v2 stage.
Prior v0.5.3 release metadata and assets remained unchanged. GitHub's latest
stable endpoint returned 404 before and after; no stable release was promoted.

## Qualified and outstanding

Installed qualification covers **Linux x64 / Ubuntu 22.04 / glibc 2.35**:
clean offline installation, native self-test and removal without preinstalled
Python, plus actual v0.5.3 package replacement using a copied fictional workspace.
Saved evidence, preferences and explicit model selection survived the upgrade.
The qualification ZIP preserves original package/checksum/notice receipts and
independent clean-install evidence.

Other eight native targets remain unqualified for this candidate. Packages are
unsigned/not notarised; do not disable OS protections. Customer-device acceptance
is outstanding. Local work is unencrypted and intended for a single trusted user.

The source ZIP's `examples/offline-garden/README.md` covers local source inspection,
handover preparation, action edits, save/stop/reopen/export/restore and historical
evidence. Import the supplied JSON backups for this release. Newer development's
direct garden entry, account-isolated local routes and later recovery/formatting
changes are not present in this frozen installer.

Native NeuroForge assistance is limited to the qualified compact public profile.
Long native recipes and exact public token preflight remain unsupported; live
ChatGPT generation is not qualified. API success alone does not establish quality.

Local retained post-publication evidence:
`browser-artifacts/publication-0.5.4rc1/public-download-verification.json`,
`release-metadata.json` and `tag-metadata.json`. Earlier stages and reviews remain
historical; publication did not rewrite their receipts or the prior tag.
