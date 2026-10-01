"""Immutable published identities admitted by scoped Linux upgrade qualification."""

from types import MappingProxyType
from typing import NamedTuple

PRIOR_COMMIT = "07bf7df8f233b555218b7957060968c7cdb29d99"


class PriorRelease(NamedTuple):
    """Source and Linux x64 installer bytes reviewed for one published preview."""

    version: str
    source_commit: str
    source_archive_sha256: str
    installer_sha256: str


QUALIFIED_PRIORS = MappingProxyType(
    {
        "0.5.3": PriorRelease(
            "0.5.3",
            PRIOR_COMMIT,
            "ec4abbc0ed4e121c50a5d383296c4b84d4a2a2b2ea981688e1c80c29333f8f6d",
            "ae2d72ea31237b2297946a8ae43fe904848acd0f0b47b88c6c56791f5ed13d62",
        ),
        "0.5.4rc1": PriorRelease(
            "0.5.4rc1",
            "cd928ba7561a09c477b3555e64aa6a3c4cc122b4",
            "873d539cb7d7d1de9b983283f3c5f20b28f6585b84c16b320920a236bf1dcf96",
            "31f64e2af6693a21b31c6296ee41aad68516238d6a9d4f34990e91632eb2a08d",
        ),
        "0.5.4rc2": PriorRelease(
            "0.5.4rc2",
            "256d38fa4b61a4d548472ce5abfd0bf513789090",
            "d53690e159ca4a21e9ec71a0997115bc96bec2486269807f97d8ed92a7301bfc",
            "eaf318d142e68e942fa17f0881f52bf98bbf0cee30e4bb9fdb84b7002c56b7f0",
        ),
    }
)

# Public v0.5.4rc2 SHA256SUMS.txt: 655 exact bytes, independently fetched and
# compared with the reviewed publication stage. Older receipt policies stay frozen.
QUALIFIED_CHECKSUM_DOCUMENTS = MappingProxyType(
    {"0.5.4rc2": "492e82f8972d7ee23d191dd0888bcf43d140a5ff9f24d4b5c7786ebaaefc2ff5"}
)


def qualified_prior(version: str, commit: str | None = None) -> PriorRelease:
    """Refuse caller-supplied or internally matching unqualified identities."""
    if not isinstance(version, str) or (
        commit is not None and not isinstance(commit, str)
    ):
        raise ValueError("Choose an explicitly qualified prior version and source.")
    prior = QUALIFIED_PRIORS.get(version)
    if prior is None or (commit is not None and commit != prior.source_commit):
        raise ValueError("Choose an explicitly qualified prior version and source.")
    return prior
