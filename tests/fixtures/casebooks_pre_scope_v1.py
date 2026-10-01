"""Exact pre-scope v1 validator/storage excerpts; test fixture, never app code.

Golden outputs and original source identity are in the adjacent JSON manifest.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid

from . import client
from .briefs import DOCUMENT_FIELDS
from .handover import EVIDENCE_MODES as HANDOVER_EVIDENCE_MODES

MAX_FILES = 300


MAX_CHARS = 2_000_000


MAX_FILE_CHARS = 200_000


MAX_QUESTIONS = 20


FORMATS = {'brief': 'Briefing note', 'enquiry': 'Enquiry letter',
           'agenda': 'Agenda item', 'handover': 'Volunteer handover'}


SCHEMA = 'sinter-casebook/v1'


def _text(value, label, limit, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{label} must be text of at most {limit:,} characters.')
    if '\x00' in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f'{label} contains binary or invalid Unicode text.')
    if required and not value.strip():
        raise ValueError(f'Please enter {label.lower()}.')
    return value


def validate(payload):
    if not isinstance(payload, dict) or payload.get('schema', SCHEMA) != SCHEMA:
        raise ValueError('Choose a Sinter casebook, not an unrelated JSON export.')
    title = _text(payload.get('title', ''), 'Casebook title', 200, True)
    questions = _text(payload.get('questions', ''), 'Questions', 12000)
    if len([line for line in questions.splitlines() if line.strip()]) > MAX_QUESTIONS:
        raise ValueError(f'Use at most {MAX_QUESTIONS} questions, one per line.')
    rows = payload.get('documents', [])
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise ValueError(f'Add between 1 and {MAX_FILES} text documents.')
    documents, ids, total = [], set(), 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Each document needs a title and text.')
        name = _text(row.get('title', ''), 'Document title', 300, True)
        content = _text(row.get('content', ''), 'Document text', MAX_FILE_CHARS, True)
        url = _text(row.get('url', ''), 'Source URL', 4000)
        if url and not client.safe_url(url):
            raise ValueError('Source links must be HTTP(S), without credentials.')
        date = _text(row.get('date', ''), 'Document date', 10)
        if date:
            from datetime import date as calendar_date
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                raise ValueError('Use YYYY-MM-DD for a document date, or leave it unknown.')
            calendar_date.fromisoformat(date)
        digest = hashlib.sha256(content.encode()).hexdigest()
        identity = hashlib.sha256((name + '\0' + url + '\0' + date + '\0' + digest).encode()).hexdigest()
        if identity in ids:
            continue
        ids.add(identity)
        total += len(content)
        if total > MAX_CHARS:
            raise ValueError('This casebook exceeds 2,000,000 text characters. Split it into separate projects.')
        documents.append({'id': 'S' + identity[:24], 'title': name, 'content': content, 'url': url,
                          'date': date, 'sha256': digest})
    document_type = payload.get('document_type', 'brief')
    if not isinstance(document_type, str) or document_type not in FORMATS:
        raise ValueError('Choose a briefing, enquiry, agenda or handover.')
    normalized = {'schema': SCHEMA, 'title': title, 'questions': questions,
                  'document_type': document_type, 'documents': documents}
    handover_evidence = payload.get('handover_evidence', 'compact')
    if (not isinstance(handover_evidence, str)
            or handover_evidence not in HANDOVER_EVIDENCE_MODES):
        raise ValueError(
            'Choose compact handover notes or a selected evidence appendix.')
    # Keep old compact projects' normalized content and fingerprint unchanged.
    # The explicit appendix choice is saved and bound to report/draft admission.
    if handover_evidence != 'compact':
        normalized['handover_evidence'] = handover_evidence
    for key, (label, limit) in DOCUMENT_FIELDS.items():
        if key in payload:
            normalized[key] = _text(payload[key], label, limit)
    normalized['fingerprint'] = hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return normalized


class Casebooks:
    """Optimistic revisions prevent two browser tabs overwriting one another."""
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS casebooks '
                       '(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, title TEXT NOT NULL, '
                       'updated_at REAL NOT NULL, document TEXT NOT NULL)')

    def save(self, payload, identifier=None, revision=None):
        document = validate(payload)
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 10_000_000:
            raise ValueError('The encoded casebook exceeds 10 MB. Split this project.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if identifier is None:
                if db.execute('SELECT count(*) FROM casebooks').fetchone()[0] >= 50:
                    raise ValueError('You have 50 casebooks. Export and remove an old one before creating another.')
                identifier, revision = uuid.uuid4().hex, 1
                db.execute('INSERT INTO casebooks VALUES (?,?,?,?,?)',
                           (identifier, revision, document['title'], time.time(), encoded))
            else:
                _text(identifier, 'Casebook ID', 100, True)
                if type(revision) is not int or revision < 1:
                    raise ValueError('A saved casebook needs its current revision.')
                cursor = db.execute('UPDATE casebooks SET revision=revision+1,title=?,updated_at=?,document=? '
                                    'WHERE id=? AND revision=?',
                                    (document['title'], time.time(), encoded, identifier, revision))
                if cursor.rowcount != 1:
                    raise ValueError('This casebook changed in another window or was removed. Export your edits, then reopen it.')
                revision += 1
        return {'id': identifier, 'revision': revision, 'document': document}

    def list(self):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,revision,title,updated_at FROM casebooks ORDER BY updated_at DESC')]

    def get(self, identifier):
        _text(identifier, 'Casebook ID', 100, True)
        with self.store.connect() as db:
            row = db.execute('SELECT revision,document FROM casebooks WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('Casebook not found.')
        return {'id': identifier, 'revision': row['revision'], 'document': json.loads(row['document'])}

    def delete(self, identifier, revision):
        if type(revision) is not int or revision < 1:
            raise ValueError('Reopen the casebook before removing it.')
        with self.store.connect() as db:
            cursor = db.execute('DELETE FROM casebooks WHERE id=? AND revision=?', (identifier, revision))
            if cursor.rowcount != 1:
                raise ValueError('The casebook changed or was removed. Reopen it before deleting.')
