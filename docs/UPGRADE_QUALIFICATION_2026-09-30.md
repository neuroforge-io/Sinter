# Upgrade qualification tooling — 30 September 2026

The next Linux candidate must prove upgrades from both published previews:
`0.5.3` and `0.5.4rc1`. This tooling checkpoint does not qualify a new installer.
The published `0.5.4rc1` assets and their historical receipts are unchanged.

`tools/qualified_priors.py` pins each prior's source commit, published source ZIP
and Linux x64 Debian installer. The copied-workspace and installed-upgrade
harnesses require the actual published ZIP through `--prior-source-archive`,
its extracted source through `--prior-source`, and an explicit `--prior-version`.
Caller-supplied checksums cannot replace the reviewed pins. Source imports run
in isolated Python with network connection attempts blocked; every extracted
file must match the bounded published archive before fixture code is imported.
Unexpected directories, extra files, links, nonregular files and size mismatches
are rejected before content reads. The source is checked again after seeding.

Both priors successfully seeded fictional originals and byte-identical copies.
The originals and extracted sources were unchanged. Explicit legacy model
selection was retained. The rc1 fixture additionally keeps an unknown owner,
an unassigned owner, a proposed date and an earlier source snapshot distinct.
The receipt is `browser-artifacts/upgrade-prior-admission/fixture-admission-review.json`.
It records zero hosted calls and no installed packages.

Focused upgrade and tooling regressions passed 96 cases. Full configured Ruff
and diff checks passed for these files. An initial test invocation named a
nonexistent CLI test file and ran no tests; the corrected invocation used
`tests/test_tooling_cli.py`.

For a sealed `0.5.4rc2`, each harness must use a fresh output folder, the exact
candidate source commit and `--expected-version 0.5.4rc2`. The installed harness
also requires the prior and candidate Debian installers, checks x64 package
identity and upgrade ordering, then replaces the installed prior without first
removing it. It records the actual candidate binary and installer hashes,
retained preferences/workspace checks and cleanup. Copied and installed fixtures
are seeded independently; their SQLite hashes need not match each other, but
each original must remain unchanged.

Fresh candidate build, independent clean installation, both actual package
upgrades and a complete installed browser workflow remain required. Existing
source-server journeys and prior-preview receipts cannot substitute for them.
