"""Atomic local preferences; credentials remain in memory and never enter exports."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

from .client import BASE_URL, MODEL, PUBLIC_MAX_OUTPUT_TOKENS, safe_url, validate_max_tokens
from .profiles import PROFILE_DEFAULTS, validate_profile

DEFAULTS = {
    **PROFILE_DEFAULTS,
    'schema_version': 1, 'theme': 'dark', 'text_size': 'normal',
    'density': 'comfortable', 'reduce_motion': False, 'api_url': BASE_URL,
    'model': MODEL, 'max_tokens': 2048, 'rkc_port': 8787, 'rkc_executable': '',
}
MAX_PREFERENCES_BYTES = 65536


def validate(values: dict) -> dict:
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('Unrecognised settings. Reload the settings page.')
    result = {**DEFAULTS, **values}
    result.update(validate_profile(result))
    for key in ('api_url', 'model', 'rkc_executable'):
        value = result[key]
        if not isinstance(value, str) or len(value) > 1024 or any(ord(c) < 32 for c in value):
            raise ValueError(f'Please use ordinary text for {key.replace("_", " ")}.')
        result[key] = value.strip()
    for key, options in {'theme': {'dark', 'light'}, 'text_size': {'normal', 'large'},
                         'density': {'comfortable', 'compact'}}.items():
        if not isinstance(result[key], str) or result[key] not in options:
            raise ValueError('Choose one of the offered appearance settings.')
    if type(result['reduce_motion']) is not bool or type(result['schema_version']) is not int or result['schema_version'] != 1:
        raise ValueError('Unsupported settings version or motion preference.')
    validate_max_tokens(result['max_tokens'])
    if type(result['rkc_port']) is not int or not 1024 <= result['rkc_port'] <= 65535:
        raise ValueError('Choose an RKC port from 1024 to 65535.')
    url = result['api_url'].rstrip('/')
    if not safe_url(url):
        raise ValueError('Enter a valid HTTPS API address without credentials.')
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment or (parsed.scheme != 'https' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}):
        raise ValueError('Remote APIs require HTTPS. Queries and fragments are not allowed.')
    if not result['model'] or not re.fullmatch(r'[A-Za-z0-9_./:@+-]{1,200}', result['model']):
        raise ValueError('Enter the model identifier supplied by your provider.')
    result['api_url'] = url
    if parsed.hostname == 'neuroforge.io' and parsed.path.rstrip('/') == '/v1' and result['max_tokens'] > PUBLIC_MAX_OUTPUT_TOKENS:
        raise ValueError('The public NeuroForge API supports at most 2,048 output tokens per step. Choose 2,048 or less.')
    return result


class Preferences:
    def __init__(self, directory: Path):
        self.path = directory / 'preferences.json'
        self.lock = threading.RLock()
        self._key = ''
        self._values = dict(DEFAULTS)
        self.warning = ''
        try:
            if self.path.stat().st_size > MAX_PREFERENCES_BYTES:
                raise ValueError('Settings file is too large.')
            self._values = validate(json.loads(self.path.read_text(encoding='utf-8')))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, UnicodeError):
            self.warning = 'Saved preferences could not be read. Defaults are active; the original file was not changed.'

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self._values)

    def connection(self) -> dict:
        with self.lock:
            # Contact details are local draft defaults, never connection metadata.
            values = {name: self._values[name] for name in ('api_url', 'model', 'max_tokens')}
            # Environment variables remain an explicit administrator/CLI override.
            values['api_url'] = os.environ.get('NEUROFORGE_BASE_URL', values['api_url'])
            values['model'] = os.environ.get('NEUROFORGE_MODEL', values['model'])
            values['api_key'] = self._key
            # Never forward an inherited NeuroForge credential to a custom server.
            values['inherit_key'] = values['api_url'].rstrip('/') == BASE_URL
            return values

    def public(self) -> dict:
        return {'settings': self.snapshot(), 'has_session_key': bool(self._key), 'warning': self.warning,
                'environment_override': bool(os.environ.get('NEUROFORGE_BASE_URL') or os.environ.get('NEUROFORGE_MODEL'))}

    def update(self, values: dict, *, confirm_endpoint=False, api_key=None) -> dict:
        if not isinstance(values, dict) or set(values) - set(DEFAULTS):
            raise ValueError('Unrecognised settings. Reload the settings page.')
        if api_key is not None and (not isinstance(api_key, str) or len(api_key) > 4096 or
                                    any(ord(c) < 33 or ord(c) > 126 for c in api_key)):
            raise ValueError('The API key contains invalid characters.')
        with self.lock:
            # Partial saves (for example, a theme toggle) preserve the saved profile.
            # An explicit empty string clears just that profile field.
            validated = validate({**self._values, **values})
            changed = validated['api_url'] != self._values['api_url']
            if changed and confirm_endpoint is not True:
                raise ValueError('Confirm the new API destination before saving it.')
            fd, name = tempfile.mkstemp(prefix='.preferences-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(validated, stream, ensure_ascii=False, indent=2)
                    stream.flush(); os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            self._values = validated
            if changed:
                self._key = ''
            if api_key is not None:
                self._key = api_key
            self.warning = ''
        return self.public()
