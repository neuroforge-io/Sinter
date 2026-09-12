"""Deterministic local structure inventory for targeted review questions.

Plain Python (AST + regular expressions) over supplied text; never executes
files, never contacts an API and never claims quality by itself. The inventory
drives per-batch review questions that are anchored in real symbols, imports
and risk-shaped lines rather than generic 'review everything' instructions.
"""
from __future__ import annotations

import ast
import re
from bisect import bisect_right

MAX_SYMBOLS = 200
MAX_SMELLS = 100
MAX_IMPORTS = 50
MAX_CUT_POINTS = 2000

DEFINITION = re.compile(
    r'(?m)^[ \t]*(?:async[ \t]+)?'
    r'(?:def[ \t]+([A-Za-z_]\w*)|class[ \t]+([A-Za-z_]\w*))[ \t]*[(:]')

RISK_PATTERNS = (
    ('dynamic code execution',
     re.compile(r'(?:eval|exec|compile)\s*\(')),
    ('subprocess or shell',
     re.compile(r'(?:subprocess\.[a-z]+|os\.system|os\.popen|\bshell\s*=\s*True)')),
    ('network access',
     re.compile(r'\b(?:urllib\.|requests\.|http\.client|socket\.|aiohttp|httpx\.)')),
    ('string-built SQL',
     re.compile(r'(?:execute|executemany)\s*\(\s*(?:f|rf|fr)?["\']')),
    ('file writes',
     re.compile(r'(?:open\s*\(\s*["\'][^"\']*?["\']\s*,\s*["\']w|[^a-zA-Z_]\.write\s*\()')),
    ('credential handling',
     re.compile(r'(?:getpass\b|api[_-]?key\b|access[_-]?token\b|client[_-]?secret\b|password\b)')),
    ('DOM injection',
     re.compile(r'(?:innerHTML|insertAdjacentHTML|document\.write|dangerouslySetInnerHTML)')),
    ('weak hash',
     re.compile(r'\b(?:md5|sha1)\s*\(')),
)

_IMPORT_LINE = re.compile(
    r'(?m)^[ \t]*(?:import[ \t]+([A-Za-z_][\w.]*)'
    r'|from[ \t]+([A-Za-z_][\w.]*)[ \t]+import)')

_AST_ERRORS = (SyntaxError, TypeError, ValueError, RecursionError, MemoryError)


def _line_starts(content):
    starts = [0]
    for index, char in enumerate(content):
        if char == '\n':
            starts.append(index + 1)
    return starts


def _line_of(starts, position):
    return bisect_right(starts, position)


def _signature(node):
    if isinstance(node, ast.ClassDef):
        bases = ', '.join(ast.unparse(base)[:60] for base in node.bases[:3])
        text = 'class ' + node.name + ('(' + bases + ')' if bases else '')
    else:
        args = [arg.arg for arg in node.args.posonlyargs]
        if node.args.posonlyargs and node.args.args:
            args.append('/')
        args.extend(arg.arg for arg in node.args.args)
        if node.args.vararg:
            args.append('*' + node.args.vararg.arg)
        args.extend(arg.arg for arg in node.args.kwonlyargs)
        if node.args.kwarg:
            args.append('**' + node.args.kwarg.arg)
        text = 'def ' + node.name + '(' + ', '.join(args) + ')'
    return text[:160]


def _parent_map(tree):
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def symbols(content):
    """Named definitions with line numbers; AST first, regex fallback."""
    starts = _line_starts(content)
    found = []
    try:
        tree = ast.parse(content)
        parents = _parent_map(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                in_class = isinstance(parents.get(id(node)), ast.ClassDef)
                kind = ('async ' if isinstance(node, ast.AsyncFunctionDef) else '') + (
                    'method' if in_class else 'function')
                found.append({'name': node.name, 'line': node.lineno,
                              'kind': kind, 'signature': _signature(node)})
            elif isinstance(node, ast.ClassDef):
                found.append({'name': node.name, 'line': node.lineno,
                              'kind': 'class', 'signature': _signature(node)})
    except _AST_ERRORS:
        found = []
    if not found:
        for match in DEFINITION.finditer(content):
            kind = 'class' if match.group(2) else 'regex'
            found.append({'name': match.group(1) or match.group(2),
                          'line': _line_of(starts, match.start()),
                          'kind': kind, 'signature': ''})
    unique, seen = [], set()
    for entry in found:
        key = (entry['name'], entry['line'], entry['kind'])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
        if len(unique) >= MAX_SYMBOLS:
            break
    return unique


def risk_smells(content):
    """Risk-shaped lines, matched by pattern kind and never counted as facts."""
    starts = _line_starts(content)
    matches = []
    for kind, pattern in RISK_PATTERNS:
        for match in pattern.finditer(content):
            line = content[match.start():].splitlines()[0].strip()[:80]
            matches.append({'kind': kind,
                            'line': _line_of(starts, match.start()),
                            'match': line})
            if len(matches) >= MAX_SMELLS:
                return matches
    return matches


def imports(content):
    """Top-level import lines; AST first, regex fallback."""
    starts = _line_starts(content)
    found = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.append({'module': ', '.join(alias.name for alias in node.names),
                              'line': node.lineno})
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.append({'module': node.module, 'line': node.lineno})
    except _AST_ERRORS:
        found = []
    if not found:
        for match in _IMPORT_LINE.finditer(content):
            module = match.group(1) or match.group(2)
            found.append({'module': module,
                          'line': _line_of(starts, match.start())})
    unique, seen = [], set()
    for entry in found:
        key = (entry['module'], entry['line'])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
        if len(unique) >= MAX_IMPORTS:
            break
    return unique


def _ast_cut_points(tree, starts):
    points = set()
    for node in ast.walk(tree):
        end_line = getattr(node, 'end_lineno', None)
        if end_line is None or end_line >= len(starts):
            continue
        points.add(starts[end_line])
    return points


def _text_boundaries(starts):
    points = set()
    width = len(starts) - 1
    if width < 2:
        return points
    step = max(1, round(width / 96))
    for index in range(step, width, step):
        points.add(starts[index])
    return points


def cut_points(content):
    """Character offsets where spans may end, always at line starts."""
    if not content:
        return []
    starts = _line_starts(content)
    try:
        points = _ast_cut_points(ast.parse(content), starts)
    except _AST_ERRORS:
        points = set()
    if not points:
        points = _text_boundaries(starts)
    points = sorted(point for point in points if 0 < point < len(content))
    if len(points) > MAX_CUT_POINTS:
        step = len(points) / MAX_CUT_POINTS
        points = [points[int(index * step)] for index in range(MAX_CUT_POINTS)]
    return points


def inventory(documents):
    """Per-source structure: symbols, risk smells and imports keyed by source id."""
    result = {}
    for document in documents:
        if not isinstance(document, dict) or not document.get('id'):
            continue
        content = document.get('content', '')
        result[document['id']] = {'symbols': symbols(content),
                                  'smells': risk_smells(content),
                                  'imports': imports(content)}
    return result
