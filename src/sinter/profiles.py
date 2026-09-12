"""User-entered local profile values and explicit defaults for editable drafts."""
from __future__ import annotations

import re
import unicodedata

from .client import safe_url

PROFILE_LIMITS = {
    'full_name': 200,
    'role': 200,
    'organisation': 1024,  # Preserve the existing settings contract.
    'email': 254,
    'phone': 80,
    'website': 2048,
    'location': 200,
    'organisation_type': 200,
}
PROFILE_DEFAULTS = dict.fromkeys(PROFILE_LIMITS, '')
_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}")
_DOMAIN_LABEL = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')


def validate_profile(settings: dict) -> dict[str, str]:
    """Pick and validate optional profile fields without retaining other settings."""
    if not isinstance(settings, dict):
        raise ValueError('Provide profile details as an object.')
    result = {}
    for name, limit in PROFILE_LIMITS.items():
        value = settings.get(name, '')
        label = name.replace('_', ' ')
        if not isinstance(value, str):
            raise ValueError(f'Please enter {label} as text, or leave it blank.')
        if len(value) > limit:
            raise ValueError(f'Keep {label} within {limit:,} characters.')
        if any(unicodedata.category(character) in {'Cc', 'Zl', 'Zp'} for character in value):
            raise ValueError(f'Use a single line of ordinary text for {label}.')
        result[name] = value.strip()
    email = result['email']
    if email:
        local, separator, domain = email.rpartition('@')
        try:
            ascii_domain = domain.encode('idna').decode('ascii')
            labels = ascii_domain.split('.')
        except UnicodeError:
            ascii_domain = ''
            labels = []
        if (not separator or not _EMAIL_LOCAL.fullmatch(local)
                or local.startswith('.') or local.endswith('.') or '..' in local
                or len(local) + 1 + len(ascii_domain) > 254
                or len(labels) < 2 or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels)):
            raise ValueError('Use one email address, such as name@example.org, or leave it blank.')
    website = result['website']
    if website and not safe_url(website):
        raise ValueError('Use a website address beginning with https:// or http://, without credentials, or leave it blank.')
    return result


def sender_defaults(settings: dict) -> dict[str, str]:
    """Return visible, editable draft defaults; never infer identity or send data."""
    profile = validate_profile(settings)
    return {
        'signatory': profile['full_name'],
        'organisation': profile['organisation'],
        'contact_details': '\n'.join(profile[name] for name in ('email', 'phone', 'website') if profile[name]),
        'sender_role': profile['role'],
        'location': profile['location'],
        'organisation_type': profile['organisation_type'],
    }
