"""Local admission and source identity for explicitly scoped model templates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from . import client

if TYPE_CHECKING:
    from .templates import Template


def validate_scope(template: Template, variables: dict, model: str) -> None:
    if not isinstance(variables, dict) or any(
            not isinstance(value, str) for value in variables.values()):
        raise ValueError('Template values must be text.')
    if client.is_native_profile(model) and not template.compact_source:
        raise ValueError('The native ERAIS preview supports a short source answer, '
                         'not this full template. Your inputs are retained. Choose '
                         'Short source answer with a smaller selected excerpt, or '
                         'explicitly configure a capable provider in Settings. '
                         'No model request was sent.')
    if template.compact_source and any(
            not variables.get(name, '').strip() for name in template.variables):
        raise ValueError('Enter a source title, the exact selected excerpt and '
                         'one question before previewing.')


def source_packet(variables: dict) -> dict:
    content = variables['excerpt']
    digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
    identity = hashlib.sha256((variables['source_title'] + '\0' + content)
                              .encode('utf-8')).hexdigest()[:32]
    return {'sources': [{'id': identity, 'title': variables['source_title'],
                         'content': content, 'sha256': digest,
                         'kind': 'selected_user_excerpt', 'url': ''}],
            'excerpts': [{'id': 'e1', 'source_id': identity, 'quote': content}]}


def preview(template: Template, variables: dict) -> dict:
    """Show the exact compact request; no discovery, credentials or network."""
    from .templates import render_prompt
    if not template.compact_source:
        raise ValueError('This preview is for Short source answer. Full templates '
                         'retain their original inputs and step instructions.')
    connection = client.connection_identity()
    if connection['model'] == client.AUTO_MODEL:
        raise ValueError('Check the available model in Settings and save its exact '
                         'identifier before previewing this source request.')
    validate_scope(template, variables, connection['model'])
    messages = ([client.Message('system', variables['system'])]
                if variables.get('system') else [])
    messages.append(client.Message('user', render_prompt(template.steps[0].prompt,
                                                        variables)))
    maximum = client.effective_max_tokens(template.steps[0].max_tokens)
    client.validate_chat_request(messages, maximum)
    request = {'messages': [asdict(message) for message in messages],
               'max_tokens': maximum, 'model': connection['model']}
    if client.is_native_profile():
        request.update(stream=False, n=1)
    digest = hashlib.sha256(json.dumps(
        {'request': request, 'connection': connection}, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return {'request': request, 'context_hash': digest,
            'buffered_native': client.is_native_profile(),
            'connection': connection, **source_packet(variables),
            'notice': 'Only the exact selected excerpt and question are included. '
                      'This is a short model draft, not a full source review. '
                      'Byte admission does not prove tokenizer fit, compute '
                      'availability or answer quality.'}
