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
    }
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
