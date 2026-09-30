# Scoped Linux x64 publication plan

This is a prepared, reviewable publication plan. No tag or release is created by
the preparation tool. Publishing requires the human owner's approval of the
exact candidate source, public notes and staged asset hashes. The site agent's
request to arrange a prerelease is coordination, not independent publication
authority. The current local preparation does not establish a public download.

## Candidate identity and scope

- Application version: `0.5.4rc1`; Debian package version: `0.5.4~rc1`.
- Source: `cd928ba7561a09c477b3555e64aa6a3c4cc122b4`.
- Proposed create-only tag: `v0.5.4rc1`, directly identifying that source.
- GitHub repository: `neuroforge-io/Sinter`.
- `prerelease=true`, `latest=false`; the published v0.5.3 preview is untouched.
- Qualified native target: Linux x64, Ubuntu 22.04/glibc 2.35.
- Unqualified: Windows x64/x86/ARM64, macOS x64/ARM64, Linux x86/ARM64/ARMv7.

The source commit, installed candidate and public download files remain frozen.
Newer development on main is separate and does not inherit these installed
receipts. The candidate verifier reads the version from the pinned Git archive,
not from the newer working tree's version.

## Local preparation

Run from the Sinter repository, using a new output directory:

```sh
python3 tools/candidate_release.py prepare \
  --candidate /home/lloyd/sinter/dist/preview-0.5.4rc1 \
  --independent-review /home/lloyd/sinter/browser-artifacts/final-independent-qualification \
  --output /home/lloyd/sinter/dist/publication-review-0.5.4rc1-v3 \
  --version 0.5.4rc1 \
  --commit cd928ba7561a09c477b3555e64aa6a3c4cc122b4
```

`tools/candidate_qualification.py` checks immutable input evidence.
`tools/candidate_release.py` creates a separate local stage and can recheck or
render commands. Neither module contains a network or publication operation.
Existing directories, canonical assets and independent receipts are not replaced.

The gates check:

1. Every canonical file against its original checksum and exact inventory;
   the source ZIP against the pinned Git object; all portable Python application
   files and its entry point against that source.
2. The installed receipt against actual Debian bytes and matching frozen/installed
   runtime identities. Linux shared libraries, copyright notices and referenced
   licence texts are inspected in the actual installer. The native tar archive
   must contain the identical runtime, including directory paths and permissions;
   web assets match pinned source bytes and exported notices match actual package
   bytes. Unsafe or duplicate archive directories are rejected.
3. Actual Debian package identity, architecture and glibc dependency. Copied
   workspace and genuine prior-package replacement receipts must identify the
   same candidate and record preservation of source evidence, saved work,
   preferences and explicit model selection. Prior version `0.5.3`, source
   `07bf7df8f233b555218b7957060968c7cdb29d99`, installer digest and source archive
   digest are explicitly pinned to the reviewed published release and checked
   against the preserved prior checksum/source documents. Internal agreement
   among rewritten upgrade receipts does not qualify a different prior release.
4. Independent review of these exact artifacts, including the separate clean
   network-disabled Ubuntu 22.04 install, self-test and removal without
   preinstalled Python or account libraries.
5. Public asset names, notes and the scoped prerelease manifest. No additional
   platform can be smuggled into the public upload set or its nested qualification
   ZIP: the canonical bundle has closed product/evidence roles and notice paths
   admitted only through validated inventory. This manifest cannot authorise a
   stable tag.

Checksums and receipts establish integrity and the recorded qualification scope.
They are not a publisher signature, independent customer acceptance, live OAuth
proof or general model-quality qualification.

## Reviewable public material

The stage contains only these proposed release attachments:

- `Sinter-0.5.4rc1-linux-x64.deb`
- `Sinter-0.5.4rc1-linux-x64.tar.gz`
- `sinter-0.5.4rc1-source.zip`
- `sinter-0.5.4rc1.pyz`
- `sinter-0.5.4rc1-qualification.zip`
- `RELEASE-NOTES.md`
- `candidate-release-manifest.json`
- `SHA256SUMS.txt`

The qualification ZIP retains the complete original canonical bundle and its
checksums under `canonical/`, with separate independent installed-review evidence
under `independent-review/`. The standalone application files must match their
counterparts inside that bundle. Public notes retain unsupported targets,
unsigned limitations, optional AI boundaries and outstanding customer acceptance.

Recheck the stage and print the exact proposed commands:

```sh
python3 tools/candidate_release.py verify \
  /home/lloyd/sinter/dist/publication-review-0.5.4rc1-v3/candidate-release-manifest.json
python3 tools/candidate_release.py commands \
  /home/lloyd/sinter/dist/publication-review-0.5.4rc1-v3/candidate-release-manifest.json
```

The printed commands are for human review. After explicit approval, the rc-tag
helper rechecks the full staged bundle before any GitHub call and admits only the
manifest's exact source and tag. Tag creation remains atomic and create-only;
conflicting or annotated tags are never replaced. Release creation uses the
explicit asset list, `--verify-tag`, `--prerelease`, `--latest=false` and the reviewed
notes file. It does not update, upload over or delete an existing release.

## Existing full release gate

`tools/release_manifest.py` and `Publish tested community release` still require
all nine installed architecture receipts at the same source. The shared individual
receipt verifier does not grant matrix qualification. Linux-only preparation
continues to fail the full gate. This explicit scoped candidate path makes its
different advertised scope visible rather than declaring an incomplete matrix
complete.

## After authorised publication

Read the actual GitHub release metadata and confirm the exact tag commit,
`prerelease=true`, eight expected assets and immutable sizes. Check the latest
stable-release endpoint separately to confirm its release identity is unchanged.
The current endpoint returns 404 because the existing releases are prereleases;
retain and compare that response rather than describing v0.5.3 as stable.
Download the public checksums and artifacts into a fresh temporary directory;
verify hashes, source identity and qualification bundle again. Only then provide
actual public release/download URLs to the site and business agents. Their older
source-only rehearsals remain historical and do not inherit this candidate's
installed qualification. Human customer-device acceptance remains a separate
checkpoint.

The v3 stage corrects the description of v0.5.3 to “published preview”; GitHub
records it as a prerelease. Its application files and qualification ZIP are
byte-identical to the independently reviewed v2 stage. Earlier stages are retained.
