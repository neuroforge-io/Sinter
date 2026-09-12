"""Deterministic inventory and boundary helpers: pure local text analysis."""
from sinter import analysis


def test_symbols_kinds_signatures_and_dedup():
    code = ('class Base:\n'
            '    pass\n\n'
            'def shared(x, y=None):\n'
            '    return x\n\n'
            'class Worker:\n'
            '    async def fetch(self, url):\n'
            '        return url\n\n'
            'def shared(a, b):\n'
            '    return a\n')
    rows = analysis.symbols(code)
    kinds = {row['name']: row['kind'] for row in rows}
    assert kinds['Base'] == 'class'
    assert kinds['Worker'] == 'class'
    assert kinds['shared'] == 'function'
    assert kinds['fetch'] == 'async method'
    by_line = {(row['name'], row['line'], row['kind']) for row in rows}
    assert ('shared', 4, 'function') in by_line
    assert ('shared', 11, 'function') in by_line
    signatures = {row['signature'] for row in rows if row['name'] == 'fetch'}
    assert signatures == {'def fetch(self, url)'}
    class_signatures = {row['signature'] for row in rows if row['name'] == 'Base'}
    assert class_signatures == {'class Base'}


def test_symbols_regex_fallback_for_unparseable_text():
    content = 'socket. socket\n'
    rows = analysis.symbols(content)
    assert rows == []


def test_risk_smells_and_imports():
    code = ('import os\n'
            'from json import loads\n\n'
            'def main():\n'
            '    return eval(os.system("ls") % password)\n')
    smells = analysis.risk_smells(code)
    kinds = {row['kind'] for row in smells}
    assert {'dynamic code execution', 'subprocess or shell',
            'credential handling'} <= kinds
    assert [row['line'] for row in smells
            if row['kind'] == 'dynamic code execution'] == [5]
    imports = analysis.imports(code)
    assert {row['module'] for row in imports} == {'os', 'json'}
    assert imports[0]['line'] == 1 and imports[1]['line'] == 2


def test_cut_points_are_sorted_and_bounded():
    block = 'def foo():\n    return 1\n'
    content = block * 200 + 'x' * 5000 + '\n'
    points = analysis.cut_points(content)
    assert points == sorted(set(points))
    assert 0 < points[0] and points[-1] < len(content)
    assert 4800 in points
    assert analysis.cut_points('') == []
    assert analysis.cut_points('one long line without newlines') == []


def test_cut_points_cap_and_fallback():
    big = 'y = 2\n' * 30000
    points = analysis.cut_points(big)
    assert len(points) <= analysis.MAX_CUT_POINTS
    assert points == sorted(set(points))
    prose = 'A commonplace sentence for the record.\n' * 300
    points = analysis.cut_points(prose)
    assert points and 0 < min(points) and max(points) < len(prose)


def test_inventory_keys_by_source_id():
    rows = analysis.inventory([{'id': 'S1', 'content': 'def a():\n    pass\n'}])
    assert set(rows) == {'S1'}
    assert rows['S1']['symbols'][0]['name'] == 'a'
    assert analysis.inventory([]) == {}


def test_bad_input_content_is_harmless():
    assert analysis.symbols('y ' * 4000) == []
    assert analysis.risk_smells('\x00' * 10) == []
    assert analysis.cut_points('y ' * 4000) == []
