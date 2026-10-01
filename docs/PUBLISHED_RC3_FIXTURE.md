# Published RC3 fictional replacement fixture — source preparation only

`tools/published_rc3_fixture.py` is a separate, usable fixture-preparation route
for published **E**, `246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe`, on Linux x64.
It does not add E to the historical `qualified_priors`, choose a candidate,
install a package or qualify a replacement. Existing prior maps, target routes,
receipt schemas, public RC3 assets and release validators remain unchanged.

The proposed replacement **fixture profile** is exactly `0.5.4rc4`.
`0.5.4rc4.dev0`, other candidates, platforms and prior commits are refused before
writing a workspace. The profile name does not admit or freeze a future RC4
source commit or binary. Nothing in this route satisfies a release role or
turns the still-missing RC4 replacement gate into a pass.

## Inputs and invocation

Supply the actual retained published E source ZIP, its complete extracted source
and its Linux x64 DEB. The producer checks the immutable ZIP/DEB hashes before
importing Sinter, checks every extracted source byte and refuses foreign,
missing, changed or linked source entries. It reads package metadata with
`dpkg-deb -f`; it never executes package scripts, installs or launches the binary.

| Input | Immutable SHA-256 |
| --- | --- |
| E source ZIP | `6d2a4ec4c6342d1243507169d877d2d266230469b01dbc00cbe031c53328f22a` |
| E Linux x64 DEB | `bb7133d70d3abfc3a0f825d57968d75629e00dc21af8d33030870e68c8c99dae` |

Run from the current source root, using owned paths outside the extracted E
source and a fresh output directory:

```sh
python tools/published_rc3_fixture.py \
  --prior-source /owned/extracted-E-source \
  --prior-source-archive /owned/sinter-0.5.4rc3-source.zip \
  --prior-installer /owned/Sinter-0.5.4rc3-linux-x64.deb \
  --output /owned/new-E-fictional-fixture
```

The seed worker runs isolated Python against the verified E source, without
inherited model/key overrides, with explicit fictional data directories. It
blocks model/provider transport and connections other than its owned loopback
listener. It does not start the watch scheduler, access an account, open a
browser or use the user's workspace. The worker is an implementation detail:
running it alone is **not** immutable prior admission.

The Windows source-compatibility test keeps only the interpreter's required
`SystemRoot` and a `USERPROFILE` pointing to its fictional directory, alongside
the fixed search path. It does not inherit the caller's home, model settings,
keys or Python import overrides. POSIX worker environment remains unchanged.
This bootstrap repair needs actual hosted Windows replay; it does not qualify
a Windows installer or allow Windows into the Linux-only fixture profile.

## Preserved fictional work

The original contains a normal v1 project, another project's retained v1 report
and user-applied wording, and that project's explicit v2 revision with selected,
empty and default-all question source choices. Current negative/unknown venue
wording, a contrary historical source, unknown source date, exact Unicode text,
source IDs, quoted ranges and raw report JSON remain separate and literal.
Report IDs are retained alongside the original JSON; they are never injected
into it. Three plain project backups retain v1 history and v2 choices.

The campaign retains an earlier `met` user mark against a changed source URL/date,
an unknown owner, an unassigned owner, an unknown due date and an entered
`reviewed` answer. Its AUD110 including-GST quote, AUD100 excluding-GST quote and
unknown unallocated production price remain entered quote data. No GST
conversion, eligibility judgment, answer generation or review-status reset is
performed by this producer. Normalization is the actual prior's normal save
behavior; the saved documents and raw typed SQLite rows are the originals for
future comparison, not the unnormalized seed literals.

Preferences explicitly select a fictional custom endpoint, provider and model,
appearance, reduced motion and fictional contact details, with no session key or
inherited connection override. The disabled watch cannot initiate a search.
The retained snapshot reads both live SQLite files without opening a runtime;
it records typed rows, stored report text, table definitions and persistent
`user_version`, `application_id`, `encoding` and `page_size`. It does not demand
WAL bytes, inode identity or an ephemeral schema cookie.

## Per-request source capability proof

Checks run only on `disposable-source-protocol`, a third copy. The untouched
`original-E-workspace` and byte-identical `copied-for-eventual-replacement` stay
available for subsequent actual binary work. Each v2 read, backup-validation and
source-only build request explicitly selects `X-Sinter-Casebook-Schema:
sinter-casebook/v2`. Ordinary v1 calls have no capability header. No global
header or historical `LocalAPI` behavior is changed.

Missing-capability v2 reads, backup validation, old-reader resaves, report builds
and draft requests are refused. A capable but unconsented draft is also refused,
without queued work or model access. An explicitly capable source-only build
retains the selected/empty/default-all source distinctions, and none of these
probes changes persistent work or settings. This is HTTP source behavior;
it does not prove installed native v2 editing or every unsupported-reader path.

`fixture-preparation.json` has schema `sinter-published-rc3-fixture/v1`, identifies
fixture creation and binds all prior source bytes, inputs, producer/worker,
originals and both workspace copies. It intentionally has no `passed` field.
`candidate_admitted`, `candidate_tested`, `prior_binary_tested` and
`package_replacement_tested` are false. A seed failure or timeout retains its
partial diagnostics and emits no successful preparation receipt. Existing output
is never overwritten. Input/source identity is checked again after seeding.

## Remaining installed and release gates

The next assignment must bind one final RC4 source/version/installer and actual
binary, verify exact prior-binary identity and deliberately launch E's browser
presentation independently of its preservation profile. Run the copied rich
fixture with that installed E binary, including explicit per-request capability
and unsupported-reader refusals. Install RC4 over **still-installed E**, without
uninstalling E first; retain package order and compare all original work,
reports, backups, typed rows, metadata, settings and model selection after reopen.
Then verify removal and owned cleanup. These steps have not been executed by
fixture preparation, and source-generated data alone cannot prove replacement.

Closed RC4 recovery/current workflow-v3/installed native-owner handoff/menu
entry/canonical assembly contracts, actual notices and source identity, fresh
old-prior replacements and independent evidence admission remain separate release
blockers. No installer, customer desktop, Windows, macOS or publication claim is
made by this fixture-preparation route.
