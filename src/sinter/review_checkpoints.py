"""Bounded local recovery of review receipts, without dispatching model requests."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

MAX_CHECKPOINT_BYTES = 10_000_000
MAX_DISCOVERY_ENTRIES = 1000
MAX_DISCOVERY_BYTES = 20_000_000


def output_paths(source, destination=None):
    """Keep generated reports out of the source collection and prevent clobbers."""
    source = Path(source).expanduser().resolve()
    output = (Path(destination).expanduser() if destination else
              source.parent / ((source.name or 'collection') + '.review.md'))
    receipt = Path(str(output) + '.checkpoint.json')
    for target in (output, receipt):
        if target.is_symlink():
            raise ValueError('Review output and checkpoint paths may not be symbolic links. Choose a new -o path.')
        if target.resolve() == source or (target.exists() and source.exists() and target.samefile(source)):
            raise ValueError('The review output or checkpoint would overwrite your source. Choose a different -o path.')
        if source.is_dir() and target.resolve().is_relative_to(source):
            suggested = source.parent / ((source.name or 'collection') + '.review.md')
            raise ValueError('Save review output outside the folder being reviewed so reports and checkpoints '
                             f'do not become source material on resume. Use -o {json.dumps(str(suggested))}. '
                             'Move any earlier review reports and checkpoints out of that source folder first.')
        if not target.parent.is_dir():
            raise ValueError(f'The output directory {target.parent} does not exist. Create it or choose another -o path.')
        if target.exists() and not target.is_file():
            raise ValueError('Choose regular files for the review output and checkpoint, using another -o path.')
    return output, receipt


def read_checkpoint(path):
    path = Path(path)
    try:
        if path.is_symlink():
            raise ValueError('A review checkpoint may not be a symbolic link.')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CHECKPOINT_BYTES:
                raise ValueError('Choose a regular review checkpoint smaller than 10 MB.')
            raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
        if len(raw) > MAX_CHECKPOINT_BYTES:
            raise ValueError('Choose a review checkpoint smaller than 10 MB.')
        saved = json.loads(raw.decode('utf-8'))
    except FileNotFoundError:
        raise ValueError(f'No review checkpoint exists at {path}.') from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError(f'The review checkpoint at {path} is not valid UTF-8 JSON.') from None
    except OSError:
        raise ValueError(f'The review checkpoint at {path} cannot be read. Check the path and file permissions.') from None
    if not isinstance(saved, dict):
        raise ValueError(f'The review checkpoint at {path} must contain a saved review object.')
    return saved


def resolve_checkpoint(requested, fingerprint, directories=(), *, explicit=False):
    """Use the requested receipt, or discover one unambiguous identical review.

    Discovery examines only the named directories, never their descendants. The
    engine still validates every saved batch before any model call.
    """
    requested = Path(requested).expanduser()
    if explicit or requested.exists() or requested.is_symlink():
        return requested, read_checkpoint(requested)
    matches, visited, examined, read_bytes = [], set(), 0, 0
    bounded = False
    for directory in directories:
        directory = Path(directory).expanduser()
        resolved = directory.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    examined += 1
                    if examined > MAX_DISCOVERY_ENTRIES:
                        bounded = True
                        break
                    if not entry.name.endswith('.checkpoint.json') or not entry.is_file(follow_symlinks=False):
                        continue
                    size = entry.stat(follow_symlinks=False).st_size
                    if size > MAX_CHECKPOINT_BYTES:
                        continue
                    read_bytes += size
                    if read_bytes > MAX_DISCOVERY_BYTES:
                        bounded = True
                        break
                    try:
                        candidate = read_checkpoint(entry.path)
                    except ValueError:
                        continue
                    if candidate.get('fingerprint') == fingerprint:
                        matches.append((Path(entry.path), candidate))
        except OSError:
            bounded = True
        if bounded:
            break
    if len(matches) == 1 and not bounded:
        return matches[0]
    if matches:
        choices = '\n'.join(f'  --checkpoint {json.dumps(str(path))}' for path, _ in matches[:5])
        reason = ('The local search reached its safety limit; choose a checkpoint explicitly.' if bounded
                  else 'More than one matching review checkpoint was found; choose one explicitly.')
        raise ValueError(f'{reason}\n{choices}\nKeep --resume and your preferred -o output path.')
    limit = ' The bounded local search was incomplete.' if bounded else ''
    raise ValueError(
        f'No matching review checkpoint was found for {requested}.{limit} '
        'Use --resume --checkpoint PATH with your original .checkpoint.json file, '
        'or repeat the original -o path. Keep the original source, question, language and API settings. '
        'To start a new review, omit --resume.')
