"""Atomic local preferences; credentials remain in memory and never enter exports."""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

from .client import (
    BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_TOKENS,
    PUBLIC_MAX_OUTPUT_TOKENS,
    safe_url,
    same_api_destination,
    uses_neuroforge_api,
    validate_max_tokens,
)
from .model_profiles import NATIVE_MODEL, native_profile_applies
from .profiles import PROFILE_DEFAULTS, validate_profile

DEFAULTS = {
    **PROFILE_DEFAULTS,
    'schema_version': 1, 'theme': 'dark', 'text_size': 'normal',
    'density': 'comfortable', 'reduce_motion': False, 'api_url': BASE_URL,
    'model': DEFAULT_MODEL, 'provider': 'openai-compatible',
    'max_tokens': DEFAULT_OUTPUT_TOKENS, 'rkc_port': 8787, 'rkc_executable': '',
}
PROVIDERS = frozenset({'openai-compatible', 'anthropic', 'chatgpt'})
MAX_PREFERENCES_BYTES = 65536
_NO_REVISION = object()


class PreferencesConflict(ValueError):
    """A delayed settings request no longer matches the observed runtime state."""


def _validate_destination(api_url, provider) -> dict:
    """Validate only the address and API style needed for catalogue discovery."""
    if (not isinstance(api_url, str) or len(api_url) > 1024
            or any(ord(char) < 32 for char in api_url)):
        raise ValueError('Please use ordinary text for api url.')
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ValueError('Choose one of the offered model connection types.')
    url = api_url.strip().rstrip('/')
    if not safe_url(url):
        raise ValueError('Enter a valid HTTPS API address without credentials.')
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment or (parsed.scheme != 'https' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}):
        raise ValueError('Remote APIs require HTTPS. Queries and fragments are not allowed.')
    if provider == 'chatgpt' and not same_api_destination(
            url, 'https://api.openai.com/v1'):
        raise ValueError('ChatGPT account access uses the official OpenAI API address.')
    if uses_neuroforge_api(url) and provider != 'openai-compatible':
        raise ValueError('Use the NeuroForge connection type for the NeuroForge API.')
    return {'api_url': url, 'provider': provider}


def _validate_api_key(api_key) -> None:
    if api_key is not None and (
            not isinstance(api_key, str) or len(api_key) > 4096
            or any(ord(char) < 33 or ord(char) > 126 for char in api_key)):
        raise ValueError('The API key contains invalid characters.')


def _validate_preview_fields(values, api_key) -> None:
    if not isinstance(values, dict) or set(values) - {
            'api_url', 'provider', 'model', 'max_tokens'}:
        raise ValueError('Provide only the model connection fields.')
    _validate_api_key(api_key)


def validate(values: dict) -> dict:
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('Unrecognised settings. Reload the settings page.')
    result = {**DEFAULTS, **values}
    result.update(validate_profile(result))
    for key in ('model', 'rkc_executable'):
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
    result.update(_validate_destination(result['api_url'], result['provider']))
    if type(result['rkc_port']) is not int or not 1024 <= result['rkc_port'] <= 65535:
        raise ValueError('Choose an RKC port from 1024 to 65535.')
    url = result['api_url']
    if not result['model'] or not re.fullmatch(r'[A-Za-z0-9_./:@+-]{1,200}', result['model']):
        raise ValueError('Enter the model identifier supplied by your provider.')
    result['api_url'] = url
    native = native_profile_applies(result['model'], url, result['provider'])
    validate_max_tokens(result['max_tokens'], model=NATIVE_MODEL if native else None)
    if uses_neuroforge_api(url) and result['max_tokens'] > PUBLIC_MAX_OUTPUT_TOKENS:
        raise ValueError('The public NeuroForge API supports at most 2,048 output tokens per step. Choose 2,048 or less.')
    return result


class Preferences:
    def __init__(self, directory: Path):
        self.path = directory / 'preferences.json'
        self.lock = threading.RLock()
        self._key = ''
        self._revision = secrets.token_hex(16)
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
            values = {name: self._values[name] for name in
                      ('api_url', 'model', 'max_tokens', 'provider')}
            # Environment variables remain an explicit administrator/CLI override.
            values['api_url'] = os.environ.get('NEUROFORGE_BASE_URL', values['api_url'])
            values['model'] = os.environ.get('NEUROFORGE_MODEL', values['model'])
            if not same_api_destination(values['api_url'], self._values['api_url']):
                values['provider'] = 'openai-compatible'
            values['api_key'] = (self._key if same_api_destination(
                values['api_url'], self._values['api_url']) else '')
            # Never forward an inherited NeuroForge credential to a custom server.
            values['inherit_key'] = uses_neuroforge_api(values['api_url'])
            return values

    def public(self) -> dict:
        with self.lock:
            return {
                'settings': dict(self._values), 'has_session_key': bool(self._key),
                'revision': self._revision, 'warning': self.warning,
                'environment_override': bool(os.environ.get('NEUROFORGE_BASE_URL')
                                             or os.environ.get('NEUROFORGE_MODEL')),
            }

    def _preview_credentials(self, candidate: dict, *,
                             confirm_endpoint, api_key) -> dict:
        """Bind credentials while the caller holds the preferences lock."""
        same = (same_api_destination(candidate['api_url'], self._values['api_url'])
                and candidate['provider'] == self._values['provider'])
        if not same and confirm_endpoint is not True:
            raise ValueError('Confirm the API destination before checking it.')
        return {
            **candidate,
            'api_key': api_key if api_key is not None else self._key if same else '',
            'inherit_key': uses_neuroforge_api(candidate['api_url']),
        }

    def preview_connection(self, values: dict, *, confirm_endpoint=False,
                           api_key=None) -> dict:
        """Validate full unsaved connection settings without retaining a key."""
        _validate_preview_fields(values, api_key)
        with self.lock:
            validated = validate({**self._values, **values})
            candidate = {name: validated[name] for name in
                         ('api_url', 'provider', 'model', 'max_tokens')}
            return self._preview_credentials(
                candidate, confirm_endpoint=confirm_endpoint, api_key=api_key)

    def preview_destination(self, values: dict, *, confirm_endpoint=False,
                            api_key=None) -> dict:
        """Admit a catalogue destination independently of generation settings."""
        _validate_preview_fields(values, api_key)
        with self.lock:
            # Older callers may include model/cap; catalogue lookup neither uses
            # nor changes them. Full saves and generation remain model-aware.
            candidate = _validate_destination(
                values.get('api_url', self._values['api_url']),
                values.get('provider', self._values['provider']))
            return self._preview_credentials(
                candidate, confirm_endpoint=confirm_endpoint, api_key=api_key)

    def update(self, values: dict, *, confirm_endpoint=False, api_key=None,
               expected_revision=_NO_REVISION) -> dict:
        if not isinstance(values, dict) or set(values) - set(DEFAULTS):
            raise ValueError('Unrecognised settings. Reload the settings page.')
        _validate_api_key(api_key)
        if expected_revision is not _NO_REVISION and (
                not isinstance(expected_revision, str)
                or not re.fullmatch(r'[0-9a-f]{32}', expected_revision)):
            raise ValueError('Provide the settings revision returned by this app.')
        with self.lock:
            if (expected_revision is not _NO_REVISION
                    and expected_revision != self._revision):
                raise PreferencesConflict(
                    'Saved settings changed. Check what is saved before '
                    'explicitly saving again. Your form has not been applied.')
            # Partial saves (for example, a theme toggle) preserve the saved profile.
            # An explicit empty string clears just that profile field.
            validated = validate({**self._values, **values})
            changed = (validated['api_url'] != self._values['api_url']
                       or validated['provider'] != self._values['provider'])
            if changed and confirm_endpoint is not True:
                raise ValueError('Confirm the new API destination before saving it.')
            next_revision = secrets.token_hex(16)
            fd, name = tempfile.mkstemp(prefix='.preferences-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(validated, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
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
            self._revision = next_revision
            # Keep this acknowledgement bound to this write, including its key flag.
            return self.public()
