"""Source-safe destinations and atomic local text exports."""
from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Sequence
from pathlib import Path


def validate_output(
    destination: str | Path, *, sources: Sequence[str | Path] = (),
) -> Path:
    """Reject source aliases and unusable targets before starting expensive work.

    Folder-specific admission rules belong to the calling workflow. This policy
    protects the named source files, accepts only regular output files, and never
    creates directories or modifies a destination during validation.
    """
    try:
        target = Path(destination).expanduser()
        resolved = target.resolve()
        protected = [Path(source).expanduser().resolve() for source in sources]
    except (OSError, RuntimeError) as exc:
        raise ValueError("Cannot resolve the output or source path. "
                         "Choose a different -o path.") from exc
    if target.is_symlink():
        raise ValueError("Output paths may not be symbolic links. "
                         "Choose a different -o path.")
    if not target.parent.is_dir():
        raise ValueError(f"The output directory {target.parent} does not exist "
                         "or is not a directory. Create it or choose another -o path.")
    if not os.access(target.parent, os.W_OK | os.X_OK):
        raise ValueError(f"The output directory {target.parent} is not writable. "
                         "Choose another -o path or check its permissions.")
    try:
        info = target.lstat()
    except FileNotFoundError:
        info = None
    if info is not None and not stat.S_ISREG(info.st_mode):
        raise ValueError("Choose a regular file for output, using another -o path.")
    for source in protected:
        if resolved == source or (info is not None and source.exists()
                                  and target.samefile(source)):
            raise ValueError("The output would overwrite your source. "
                             "Choose a different -o path.")
    return target


def atomic_write_text(
    destination: str | Path, content: str, *, sources: Sequence[str | Path] = (),
) -> None:
    """Flush a same-directory temporary file, then replace the deliverable once.

    A failed write, flush or replacement leaves an existing deliverable intact.
    Revalidate immediately before replacement in case work changed the target.
    Cleanup is restricted to the unique temporary file created by this call.
    """
    target = validate_output(destination, sources=sources)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=target.parent,
            prefix=".sinter-output-", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        validate_output(target, sources=sources)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
