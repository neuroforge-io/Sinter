"""Publication cannot reuse a conflicting tag or overwrite a concurrent creator."""
from __future__ import annotations

import json
import subprocess

import pytest

from tools import release_tag

REPOSITORY = 'neuroforge-io/Sinter'
TAG = 'v0.5.3'
COMMIT = 'a' * 40


def ref(commit=COMMIT, *, kind='commit', name=TAG):
    return {'ref': f'refs/tags/{name}', 'object': {'type': kind, 'sha': commit}}


class GitHubRefs:
    """Stateful create-only API fixture with an optional competing creator."""
    def __init__(self, existing=None, raced=None):
        self.existing, self.raced = existing, raced
        self.methods = []

    def __call__(self, repository, method, endpoint, payload=None):
        assert repository == REPOSITORY
        self.methods.append(method)
        if method == 'GET':
            assert endpoint == f'ref/tags/{TAG}'
            return (200, self.existing) if self.existing else (404, {'message': 'Not Found'})
        assert method == 'POST' and endpoint == 'refs'
        assert payload == {'ref': f'refs/tags/{TAG}', 'sha': COMMIT}
        if self.raced is not None:
            self.existing = self.raced
        if self.existing is not None:
            return 422, {'message': 'Reference already exists'}
        self.existing = ref(payload['sha'])
        return 201, self.existing


@pytest.mark.parametrize('existing', [None, ref()])
def test_create_or_retry_preserves_exact_release_identity(monkeypatch, existing):
    api = GitHubRefs(existing)
    monkeypatch.setattr(release_tag, '_api', api)
    release_tag.ensure_release_tag(REPOSITORY, TAG, COMMIT)
    assert api.existing == ref()
    assert api.methods == (['GET'] if existing else ['GET', 'POST'])


@pytest.mark.parametrize('existing', [ref('b' * 40), ref(kind='tag'), ref(name='v9.0.0')])
def test_existing_wrong_commit_annotated_or_wrong_name_never_mutates(monkeypatch, existing):
    api = GitHubRefs(existing)
    monkeypatch.setattr(release_tag, '_api', api)
    with pytest.raises(ValueError, match='reviewed commit'):
        release_tag.ensure_release_tag(REPOSITORY, TAG, COMMIT)
    assert api.existing == existing and api.methods == ['GET']


@pytest.mark.parametrize('raced,success', [(ref(), True), (ref('b' * 40), False), (ref(kind='tag'), False)])
def test_concurrent_creation_only_accepts_same_commit(monkeypatch, raced, success):
    api = GitHubRefs(raced=raced)
    monkeypatch.setattr(release_tag, '_api', api)
    if success:
        release_tag.ensure_release_tag(REPOSITORY, TAG, COMMIT)
    else:
        with pytest.raises(ValueError, match='reviewed commit'):
            release_tag.ensure_release_tag(REPOSITORY, TAG, COMMIT)
    assert api.existing == raced
    assert api.methods == ['GET', 'POST', 'GET']


@pytest.mark.parametrize('status', [301, 401, 403, 429, 500])
def test_lookup_failure_is_not_mistaken_for_absent_tag(monkeypatch, status):
    calls = []
    def api(*args):
        calls.append(args)
        return status, {'message': 'Unavailable'}
    monkeypatch.setattr(release_tag, '_api', api)
    with pytest.raises(ValueError, match=f'HTTP {status}'):
        release_tag.ensure_release_tag(REPOSITORY, TAG, COMMIT)
    assert len(calls) == 1 and calls[0][1] == 'GET'


@pytest.mark.parametrize('responses', [
    [(404, {}), (403, {})],
    [(404, {}), (422, {}), (404, {})],
    [(404, {}), (201, ref('b' * 40))],
])
def test_failed_or_unverified_creation_blocks_publication(monkeypatch, responses):
    replies = iter(responses)
    monkeypatch.setattr(release_tag, '_api', lambda *args: next(replies))
    with pytest.raises(ValueError):
        release_tag.ensure_release_tag(REPOSITORY, TAG, COMMIT)


@pytest.mark.parametrize('status,returncode', [(200, 0), (404, 1), (422, 1)])
def test_cli_transport_reads_http_status_without_parsing_error_prose(monkeypatch, status, returncode):
    def run(command, **kwargs):
        assert command[:5] == ['gh', 'api', '--hostname', 'github.com', '--include']
        assert command[-2:] == ['--input', '-']
        assert json.loads(kwargs['input']) == {'ref': f'refs/tags/{TAG}', 'sha': COMMIT}
        assert kwargs['timeout'] == 30
        return subprocess.CompletedProcess(command, returncode,
            f'HTTP/2.0 {status} Result\r\nContent-Type: application/json\r\n\r\n{{"fixture":true}}',
            'Arbitrary diagnostic text that is not authority.')
    monkeypatch.setattr(release_tag.subprocess, 'run', run)
    assert release_tag._api(REPOSITORY, 'POST', 'refs', {'ref': f'refs/tags/{TAG}', 'sha': COMMIT}) == (status, {'fixture': True})


@pytest.mark.parametrize('output,code', [('', 1), ('HTTP/2.0 200 OK\n\nnot JSON', 0), ('HTTP/2.0 200 OK\n\n{}', 1)])
def test_transport_failure_never_returns_success(monkeypatch, output, code):
    monkeypatch.setattr(release_tag.subprocess, 'run', lambda *a, **kw:
        subprocess.CompletedProcess(a[0], code, output, 'secret diagnostic must not appear'))
    with pytest.raises(ValueError) as error:
        release_tag._api(REPOSITORY, 'GET', f'ref/tags/{TAG}')
    assert 'secret diagnostic' not in str(error.value)


@pytest.mark.parametrize('repository,tag,commit', [
    ('owner/repo/extra', TAG, COMMIT), (REPOSITORY, '../main', COMMIT),
    (REPOSITORY, TAG, 'main'), (REPOSITORY, TAG, 'A' * 40),
])
def test_invalid_identity_never_calls_github(monkeypatch, repository, tag, commit):
    def forbidden(*args):
        pytest.fail('Invalid input reached GitHub')
    monkeypatch.setattr(release_tag, '_api', forbidden)
    with pytest.raises(ValueError):
        release_tag.ensure_release_tag(repository, tag, commit)
