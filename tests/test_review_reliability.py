"""Recovery safety and admission regressions; all model responses are fictional."""
import copy
import hashlib
import json
from unittest.mock import patch

import pytest

from sinter import client, evidence, review
from sinter.operations import Cancelled


def book(characters=100):
    return {'title': 'Community policies', 'documents': [
        {'title': 'Meeting notes', 'content': 'A' * characters}]}


def test_checkpoint_is_saved_before_remote_dispatch():
    saved = []

    def respond(*args, **kwargs):
        assert saved[-1]['batches'][0]['status'] == 'running'
        return client.ChatResult('Unverified fictional commentary: no issues found after checking the supplied material.')

    with patch('sinter.client.chat', side_effect=respond):
        result = review.run(book(), on_checkpoint=lambda row: saved.append(row))
    assert saved[0]['batches'][0]['status'] == 'running'
    assert saved[1]['batches'][0]['status'] == 'done'
    assert result['coverage']['requests_this_run'] == 1
    assert len({row['created_at'] for row in saved}) == 1


def test_failed_write_ahead_checkpoint_prevents_dispatch():
    with patch('sinter.client.chat') as model:
        with pytest.raises(OSError, match='disk full'):
            review.run(book(), on_checkpoint=lambda _: (_ for _ in ()).throw(OSError('disk full')))
        model.assert_not_called()


@pytest.mark.parametrize('failure', [Cancelled(), KeyboardInterrupt(), RuntimeError('process interrupted')])
def test_inflight_interruption_remains_blocked_on_resume(failure):
    saved = []
    with patch('sinter.client.chat', side_effect=failure):
        with pytest.raises(type(failure)):
            review.run(book(), on_checkpoint=lambda row: saved.append(copy.deepcopy(row)))
    with patch('sinter.client.chat') as model:
        resumed = review.run(book(), resume=saved[-1])
        model.assert_not_called()
    assert resumed['coverage']['batches_uncertain'] == 1
    assert resumed['coverage']['batches_not_attempted'] == 0


def test_legacy_failure_is_conservatively_uncertain():
    old = review.run(book(), offline=True)
    chunk = review.plan(book())[2][0]
    old.pop('recovery_version')
    old['batches'] = [{'id': chunk['id'], 'status': 'failed', 'error': 'legacy timeout'}]
    with patch('sinter.client.chat') as model:
        result = review.run(book(), resume=old)
        model.assert_not_called()
    assert result['coverage']['batches_uncertain'] == 1


def test_unattempted_explicit_retries_stay_uncertain_after_budget():
    payload = book(13000)
    old = review.run(payload, offline=True)
    old['batches'] = [{'id': chunk['id'], 'status': 'uncertain_remote_outcome'}
                      for chunk in review.plan(payload)[2]]
    with patch('sinter.client.chat', return_value=client.ChatResult('Explicit retry: no issues found after checking the supplied material.')) as model:
        result = review.run(payload, resume=old, retry_uncertain=True, max_parts=1)
    assert model.call_count == 1
    assert result['coverage']['batches_complete'] == 1
    assert result['coverage']['batches_uncertain'] == 2
    with patch('sinter.client.chat') as model:
        resumed = review.run(payload, resume=result)
        model.assert_not_called()
    assert resumed['coverage']['batches_uncertain'] == 2


def test_received_incomplete_response_is_failed_not_uncertain():
    with patch('sinter.client.chat', return_value=client.ChatResult('Truncated', finish_reason='length')):
        result = review.run(book(13000))
    coverage = result['coverage']
    assert coverage['batches_failed'] == 1 and coverage['batches_uncertain'] == 0
    assert coverage['batches_not_attempted'] == 2
    assert sum(coverage[key] for key in ('batches_complete', 'batches_failed',
                                       'batches_uncertain', 'batches_not_attempted')) == coverage['batches_total']


def test_creation_time_survives_resume_and_language_is_bound():
    with patch('sinter.review.utc_now', return_value='2026-09-12T01:00:00+00:00'):
        first = review.run(book(), offline=True, language='German')
    with patch('sinter.review.utc_now', return_value='2026-09-12T02:00:00+00:00'):
        second = review.run(book(), offline=True, language='German', resume=first)
    assert second['created_at'] == first['created_at']
    assert second['updated_at'] != first['updated_at']
    with pytest.raises(ValueError, match='different inputs'):
        review.run(book(), language='English', resume=first)
    with patch('sinter.client.chat', return_value=client.ChatResult('Fictional response')) as model:
        review.run(book(), language='German')
    assert json.loads(model.call_args.args[0][1].content)['language_hint'] == 'German'


def test_duplicate_checkpoint_batches_are_rejected():
    old = review.run(book(13000), offline=True)
    chunk = review.plan(book(13000))[2][0]
    old['batches'] = [{'id': chunk['id'], 'status': 'running'}] * 2
    with pytest.raises(ValueError, match='checkpoint batch'):
        review.run(book(13000), resume=old)


@pytest.mark.parametrize('options', [{'retry_uncertain': True}, {'retry_uncertain': 'yes'},
                                      {'retry_uncertain': True, 'offline': True}])
def test_retry_permission_requires_explicit_online_resume(options):
    with pytest.raises(ValueError, match='Retrying uncertain'):
        review.run(book(), **options)


def test_intake_admits_ci_extensionless_and_unknown_utf8_with_byte_hash(tmp_path):
    workflow = tmp_path / '.github' / 'workflows'
    workflow.mkdir(parents=True)
    (workflow / 'ci.yml').write_text('name: Fictional CI\n', encoding='utf-8')
    raw = b'\xef\xbb\xbfFROM fictional\r\n'
    (tmp_path / 'Dockerfile').write_bytes(raw)
    (tmp_path / 'notes.community').write_text('Volunteer shifts need confirmation.', encoding='utf-8')
    payload, manifest = review.load_collection(tmp_path)
    titles = {row['title'] for row in payload['documents']}
    assert titles == {'.github/workflows/ci.yml', 'Dockerfile', 'notes.community'}
    record = next(row for row in manifest['admitted'] if row['path'] == 'Dockerfile')
    assert record['source_bytes_sha256'] == hashlib.sha256(raw).hexdigest()
    assert record['bytes'] == len(raw)
    assert manifest['discovery_complete']


def test_intake_excludes_suspected_credentials_and_binary_data(tmp_path):
    (tmp_path / 'safe.txt').write_text('Ordinary community note.', encoding='utf-8')
    (tmp_path / '.env').write_text('SENSITIVE=fixture', encoding='utf-8')
    (tmp_path / 'token.txt').write_text('api_key=' + 'FAKE' * 6, encoding='utf-8')
    (tmp_path / 'key.txt').write_text('-----BEGIN PRIVATE KEY-----\nfixture', encoding='utf-8')
    (tmp_path / 'binary.unknown').write_bytes(b'\x00binary\x01')
    (tmp_path / 'document.pdf').write_bytes(b'%PDF-fixture')
    payload, manifest = review.load_collection(tmp_path)
    assert [row['title'] for row in payload['documents']] == ['safe.txt']
    assert len(manifest['skipped']) == 5
    assert any('suspected-sensitive content' in key for key in manifest['exclusion_counts'])


def test_discovery_cap_is_visible_and_operational_priority_is_preserved(tmp_path, monkeypatch):
    for index in range(6):
        (tmp_path / f'{index}.txt').write_text('Fictional note', encoding='utf-8')
    (tmp_path / 'Dockerfile').write_text('FROM fictional', encoding='utf-8')
    monkeypatch.setattr(review, 'MAX_FILES', 1)
    payload, manifest = review.load_collection(tmp_path)
    assert payload['documents'][0]['title'] == 'Dockerfile'
    assert manifest['exclusion_counts']['document count limit'] == 6
    monkeypatch.setattr(review, 'MAX_DISCOVERY_ENTRIES', 3)
    _, manifest = review.load_collection(tmp_path)
    assert manifest['entries_examined'] == 3
    assert not manifest['discovery_complete']


def test_zero_overlap_does_not_send_unrelated_evidence_to_ranker():
    sources = [evidence.source('Fictional note', 'Volunteers meet beside the garden.')]
    with patch('sinter.client.chat') as model:
        selected, warnings = evidence.select(sources, 'Insurance excess', use_model=True)
        model.assert_not_called()
    assert selected == []
    assert any('No relevant evidence' in warning for warning in warnings)
    assert any('not proof' in warning for warning in warnings)


def test_vague_hedge_becomes_partial_and_bound_on_resume():
    vague = 'The supplied material appears broadly consistent with expectations.'
    with patch('sinter.client.chat', return_value=client.ChatResult(vague)) as model:
        first = review.run(book())
    assert model.call_count == 1
    assert first['coverage']['batches_partial'] == 1
    assert first['coverage']['batches_complete'] == 0
    assert first['batches'][0]['status'] == 'partial'
    assert first['batches'][0]['follow_ups'] == 0
    with patch('sinter.client.chat', return_value=client.ChatResult(vague)) as model:
        second = review.run(book(), resume=first)
    assert model.call_count == 1
    assert second['batches'][0]['follow_ups'] == 1
    assert second['batches'][0]['question'].startswith(review.FOLLOW_UP_HINT[:20])
    with patch('sinter.client.chat', return_value=client.ChatResult(vague)) as model:
        third = review.run(book(), resume=second)
    assert model.call_count == 1 and third['batches'][0]['follow_ups'] == 2
    with patch('sinter.client.chat') as model:
        fourth = review.run(book(), resume=third)
        model.assert_not_called()
    assert fourth['coverage']['batches_partial'] == 1
    assert fourth['coverage']['batches_not_reviewed'] == 1


def test_substantive_gate_and_token_budget():
    assert review._substantive('No issues found after checking the supplied material.', 'x * 12')
    assert not review._substantive('Looks fine.', 'x * 12')
    assert review._substantive('"Volunteers meet beside the garden."', 'Volunteers meet beside the garden.')
    assert not review._substantive('"Volunteers meet beside the garden."', 'Unrelated wording entirely.')
    assert review._token_budget([]) == 704
    assert review._token_budget(['one']) == 704
    assert review._token_budget(['a', 'b', 'c']) == 1088
    assert review._token_budget(['x'] * 20) == 2048


def test_boundary_aware_chunks_are_contiguous_and_complete():
    block = 'def foo():\n    return 1\n'
    content = block * 200 + 'x' * 5000 + '\n'
    chunks = review.plan({'title': 'Structured', 'documents': [{'title': 's.py', 'content': content}]})[2]
    assert len(chunks) == 2
    assert chunks[0]['end'] == 4800 and chunks[0]['start'] == 0
    assert chunks[1]['start'] == 4800 and chunks[1]['end'] == len(content)
    assert ''.join(chunk['text'] for chunk in chunks) == content
    assert chunks[0]['end_line'] == chunks[1]['line']


def test_targeted_questions_are_grounded_in_real_symbols():
    code = ('import os\n\n'
            'def parse_path(value):\n'
            '    return os.system(value)\n\n'
            'class Loader:\n'
            '    def load(self):\n'
            '        return eval("2")\n')
    book = {'title': 'Code', 'documents': [{'title': 'main.py', 'content': code}]}
    _, _, chunks, _ = review.plan(book)
    chunk = chunks[0]
    assert set(chunk['symbols']) == {'parse_path', 'Loader', 'load'}
    assert any('subprocess or shell' in row for row in chunk['smells'])
    assert any('dynamic code execution' in row for row in chunk['smells'])
    questions = review._final_plan({}, chunks, review.DEFAULT_QUESTION)[chunk['id']]
    assert questions
    for question in questions:
        assert any(name in question for name in ('parse_path', 'Loader', 'load'))


def test_refine_with_model_is_gated_and_graceful():
    plain = {'title': 'Plain', 'documents': [{'title': 'note', 'content': 'A' * 120}]}
    with patch('sinter.client.chat', side_effect=AssertionError('gated')) as model:
        assert review._refine_with_model(review.plan(plain)[2]) == {}
        model.assert_not_called()
    code = {'title': 'Code', 'documents': [{'title': 'main.py', 'content': 'def works():\n    return 1\n'}]}
    chunks = review.plan(code)[2]
    good = '{"questions": [{"question": "Wrap loads in error handling and verify it.", "target": "works"}]}'
    with patch('sinter.client.chat', return_value=client.ChatResult(good)):
        refined = review._refine_with_model(chunks)
    assert refined[chunks[0]['id']] == ['Wrap loads in error handling and verify it.']
    for bad in ('not json', '{"questions": []}', '{"questions": "x"}',
                '{"questions": [{"target": "works"}]}'):
        with patch('sinter.client.chat', return_value=client.ChatResult(bad)):
            assert review._refine_with_model(chunks) == {}
    with patch('sinter.client.chat', side_effect=client.APIError('down', 503)):
        assert review._refine_with_model(chunks) == {}


def test_questions_plan_survives_resume_without_model_calls():
    code = 'def load(path):\n    return open(path).read()\n'
    book = {'title': 'Code', 'documents': [{'title': 'main.py', 'content': code}]}
    with patch('sinter.client.chat', side_effect=AssertionError('no planning call')) as model:
        first = review.run(book, offline=True)
        model.assert_not_called()
    assert first['questions']
    with patch('sinter.client.chat', side_effect=AssertionError('no planning call')) as model:
        second = review.run(book, offline=True, resume=first)
        model.assert_not_called()
    assert second['questions'] == first['questions']
    assert 'Question:' in second['markdown']
