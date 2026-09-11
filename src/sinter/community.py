"""Deterministic everyday community tools. User-entered actions are never inferred."""
from __future__ import annotations

import csv
import difflib
import io
from datetime import date, datetime, timedelta, timezone
import hashlib

from .evidence import literal, text, utc_now


def compare(before, after):
    text(before, 'Earlier version', 60000); text(after, 'New version', 60000)
    # Keep both inputs unchanged. Line-oriented comparison bounds expensive matching.
    left, right = before.splitlines(), after.splitlines()
    if max(len(left), len(right)) > 1500:
        raise ValueError('Compare at most 1,500 lines per document.')
    changes = []
    for op, a, b, c, d in difflib.SequenceMatcher(None, left, right, autojunk=True).get_opcodes():
        if op != 'equal':
            changes.append({'kind': op, 'before_start': a+1, 'after_start': c+1,
                            'before': '\n'.join(left[a:b]), 'after': '\n'.join(right[c:d])})
    return {'changes': changes, 'changed_blocks': len(changes), 'notice': 'Line-by-line wording comparison; line-ending style and a final newline are ignored. This is not a judgement of meaning, correctness or approval.'}


def plan(title, rows):
    title = text(title, 'Plan title', 200, True)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError('Enter 1 to 200 actions.')
    output = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Each action must be an object.')
        action = text(row.get('action', ''), 'Action', 2000, True)
        owner = text(row.get('owner', ''), 'Owner', 200)
        due = text(row.get('due', ''), 'Due date', 10)
        status = text(row.get('status', 'not_started'), 'Status', 20)
        if status not in {'not_started', 'in_progress', 'done'}:
            raise ValueError('Choose a valid action status.')
        if due:
            try:
                parsed = date.fromisoformat(due)
                if parsed.isoformat() != due:
                    raise ValueError()
                parsed + timedelta(days=1)
            except (ValueError, OverflowError) as exc:
                raise ValueError('Use a valid YYYY-MM-DD deadline before 9999-12-31.') from exc
        output.append({'action': action, 'owner': owner, 'due': due, 'status': status})
    stream = io.StringIO(newline=''); writer = csv.writer(stream)
    writer.writerow(['Action', 'Owner', 'Due date', 'Status'])
    def cell(value):
        # Defend against spreadsheet formula interpretation, including leading whitespace.
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) or value.startswith(('\t', '\r', '\n')) else value
    for row in output:
        writer.writerow([cell(row[k]) for k in ('action', 'owner', 'due', 'status')])
    lines = ['# '+literal(title), 'USER-ENTERED PLAN - CONFIRM OWNERS AND DATES']
    for row in output:
        lines.append('- '+literal(row['action'])+' | Owner: '+literal(row['owner'] or 'Unassigned')+' | Due: '+(row['due'] or 'Not set')+' | '+row['status'])
    def escape(value):
        return value.replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    def daystamp(value):
        return f'{value.year:04d}{value.month:02d}{value.day:02d}'
    cal = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//NeuroForge//Sinter user plan//EN', 'CALSCALE:GREGORIAN']
    for index, row in enumerate(output):
        if row['due']:
            day = date.fromisoformat(row['due'])
            identity = hashlib.sha256((title+'\0'+str(index)+'\0'+row['action']).encode()).hexdigest()
            cal += ['BEGIN:VEVENT', 'UID:'+identity+'@sinter.local', 'DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                    'DTSTART;VALUE=DATE:'+daystamp(day), 'DTEND;VALUE=DATE:'+daystamp(day+timedelta(days=1)),
                    'SUMMARY:'+escape(row['action']), 'DESCRIPTION:'+escape('Owner: '+(row['owner'] or 'Unassigned')+'; user-entered deadline'), 'END:VEVENT']
    cal.append('END:VCALENDAR')
    folded = []
    for line in cal:
        chunk = ''
        for character in line:
            if len((chunk+character).encode('utf-8')) > 73:
                folded.append(chunk); chunk = ' '
            chunk += character
        folded.append(chunk)
    return {'title': title, 'workflow': 'community-plan', 'created_at': utc_now(), 'review_status': 'user_entered', 'actions': output,
            'markdown': '\n\n'.join(lines), 'csv': stream.getvalue(), 'calendar': '\r\n'.join(folded)+'\r\n'}
