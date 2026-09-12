"""Developer tools explain setup errors without weakening integration gates."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BROWSER_TOOLS = [
    'browser_smoke.py', 'casebook_browser.py', 'desktop_browser.py',
    'site_browser.py', 'studio_browser.py',
]


def run_tool(name, *args, cwd, commit=None):
    """Run with optional packages unavailable, even on a fully equipped host."""
    env = dict(os.environ)
    env.pop('GITHUB_SHA', None)
    env.pop('SINTER_CHROMIUM', None)
    if commit is not None:
        env['GITHUB_SHA'] = commit
    return subprocess.run(
        [sys.executable, '-I', '-S', str(ROOT / 'tools' / name), *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=10,
    )


@pytest.mark.parametrize('name', BROWSER_TOOLS + [
    'release_manifest.py', 'rkc_smoke.py', 'package_native.py',
])
def test_help_works_without_optional_dependencies_or_environment(name, tmp_path):
    result = run_tool(name, '--help', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout and '--help' in result.stdout
    assert not result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('name,required', [
    ('release_manifest.py', 'output, source'),
    ('rkc_smoke.py', 'binary'),
    ('package_native.py', '--arch'),
])
def test_required_arguments_have_usage_errors(name, required, tmp_path):
    result = run_tool(name, cwd=tmp_path)
    assert result.returncode == 2
    assert 'usage:' in result.stderr and required in result.stderr
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('name', BROWSER_TOOLS)
def test_missing_playwright_fails_before_browser_artifacts(name, tmp_path):
    result = run_tool(name, cwd=tmp_path)
    assert result.returncode == 2
    assert "python -m pip install '.[browser]'" in result.stderr
    assert 'Playwright is required' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not list(tmp_path.iterdir())


def test_native_packaging_explains_missing_dependencies(tmp_path):
    result = run_tool('package_native.py', '--arch', 'x64', cwd=tmp_path)
    assert result.returncode == 2
    assert 'PyInstaller is required' in result.stderr
    assert 'python -m pip install pyinstaller==6.22.2 certifi' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('commit', [None, '', 'local', 'a' * 39, 'z' * 40])
def test_release_manifest_requires_full_source_commit(commit, tmp_path):
    result = run_tool(
        'release_manifest.py', str(tmp_path), str(tmp_path),
        cwd=tmp_path, commit=commit,
    )
    assert result.returncode == 2
    assert 'GITHUB_SHA' in result.stderr and '40-character' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not list(tmp_path.iterdir())


def test_release_missing_receipts_fails_cleanly_without_publishing(tmp_path):
    result = run_tool(
        'release_manifest.py', str(tmp_path), str(tmp_path),
        cwd=tmp_path, commit='a' * 40,
    )
    assert result.returncode == 1
    assert 'release validation failed' in result.stderr
    assert 'required architecture receipt' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not list(tmp_path.iterdir())


def test_rkc_missing_executable_has_build_guidance(tmp_path):
    result = run_tool('rkc_smoke.py', 'missing-rkc', cwd=tmp_path)
    assert result.returncode == 2
    assert 'RKC executable does not exist' in result.stderr
    assert 'Build RKC' in result.stderr
    assert 'Traceback' not in result.stderr


def test_rkc_runtime_failure_is_clear_and_cannot_pass(monkeypatch, tmp_path, capsys):
    spec = importlib.util.spec_from_file_location(
        'rkc_smoke', ROOT / 'tools' / 'rkc_smoke.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    executable = tmp_path / 'rkc'
    executable.write_text('fixture')
    executable.chmod(0o755)

    def failed_check(binary):
        raise ValueError('RKC could not compile this collection.')

    monkeypatch.setattr(module, 'run_check', failed_check)
    with pytest.raises(SystemExit) as error:
        module.main([str(executable)])
    assert error.value.code == 1
    assert 'RKC integration failed: RKC could not compile' in capsys.readouterr().err


def support_module():
    spec = importlib.util.spec_from_file_location(
        'tool_support', ROOT / 'tools' / '_support.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_browser_startup_failure_has_actionable_nonzero_exit(monkeypatch):
    class BrowserError(Exception):
        pass

    def unavailable(**kwargs):
        raise BrowserError('Executable does not exist')

    monkeypatch.setitem(
        sys.modules, 'playwright.sync_api', SimpleNamespace(Error=BrowserError)
    )
    browser = SimpleNamespace(chromium=SimpleNamespace(launch=unavailable))
    with pytest.raises(SystemExit) as error:
        support_module().launch_chromium(browser)
    assert 'Chromium could not start' in str(error.value)
    assert 'playwright install --with-deps chromium' in str(error.value)
    assert '--chromium PATH' in str(error.value)
    assert error.value.code != 0


def test_explicit_chromium_overrides_environment(monkeypatch, tmp_path):
    helper = support_module()
    monkeypatch.setattr(helper.importlib, 'import_module', lambda _: None)
    monkeypatch.setenv('SINTER_CHROMIUM', str(tmp_path / 'missing-browser'))
    executable = tmp_path / 'chromium'
    executable.write_text('fixture')
    executable.chmod(0o755)
    args = helper.browser_arguments('Fixture tool', ['--chromium', str(executable)])
    assert args.chromium == str(executable)


def test_invalid_chromium_environment_is_reported(monkeypatch, tmp_path, capsys):
    helper = support_module()
    monkeypatch.setattr(helper.importlib, 'import_module', lambda _: None)
    monkeypatch.setenv('SINTER_CHROMIUM', str(tmp_path / 'missing-browser'))
    with pytest.raises(SystemExit) as error:
        helper.browser_arguments('Fixture tool', [])
    assert error.value.code == 2
    assert 'Chromium executable does not exist' in capsys.readouterr().err
