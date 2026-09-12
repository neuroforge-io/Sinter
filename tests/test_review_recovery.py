"""User-facing review recovery regressions; responses are deterministic fixtures."""
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import cli, client, review, review_checkpoints


SOURCE = ('Volunteers must submit booking requests by Thursday.\n'
          'The booking deadline is Friday at noon.\n'
          'The coordinator confirms available garden spaces.\n')
FINDING = 'Line 2: The booking deadline conflicts with Thursday in the earlier instruction; choose one deadline.'


def payload():
    return {'title': 'Notes', 'documents': [{'title': 'notes.txt', 'content': SOURCE}]}


def saved_review():
    with patch('sinter.client.chat', return_value=client.ChatResult(FINDING)):
        return review.run(payload())


@pytest.mark.parametrize('text', [FINDING,
    'DEMONSTRATED: The booking deadline conflicts with Thursday in the earlier instruction; choose one deadline.',
    'SUSPECTED: The coordinator confirms available spaces, but no confirmation method is stated.',
    'Lines 1–2: The booking deadline appears inconsistent between Thursday and Friday.',
    'L2: The booking deadline conflicts with Thursday in the earlier instruction; choose one deadline.',
    'The statement “The booking deadline is Friday at noon.” conflicts with the previous deadline.',
    'No demonstrated issues. I checked the date consistency and responsibilities in the supplied excerpt.',
    'Line 3: The coordinator is not named; assign a person responsible for confirmations.',
])
def test_grounded_prose_findings_are_usable_without_literal_quotes(text):
    assert review._substantive(text, SOURCE)


@pytest.mark.parametrize('text', [
    'Line 99: The booking deadline conflicts with Thursday in the earlier instruction; choose one deadline.',
    'Lines 3–2: The booking deadline conflicts with Thursday in the earlier instruction; choose one deadline.',
    'Line 2: There might be possible issues with this supplied material that should be reviewed.',
    'Line 3: The booking deadline conflicts with Thursday in the earlier instruction; choose one deadline.',
    'DEMONSTRATED: There may be issues in this document; please review every section carefully.',
    'SUSPECTED: I cannot identify a concrete problem from the supplied information.',
    'The supplied material appears broadly consistent with expectations.',
    'Line 2: Please provide the booking deadline source document so I can perform the requested review.',
    'DEMONSTRATED: Please provide the booking deadline source document so I can perform the requested review.',
    'I cannot conclude "no issues found" because the excerpt is incomplete. Please provide the missing source.',
])
def test_location_and_confidence_labels_do_not_admit_ungrounded_fluff(text):
    assert not review._substantive(text, SOURCE)


def test_absolute_line_offsets_are_checked():
    assert review._substantive(FINDING.replace('Line 2', 'Line 102'), SOURCE, 101)
    assert not review._substantive(FINDING, SOURCE, 101)


def test_live_observed_unquoted_specific_gap_is_grounded():
    source = SOURCE + 'No contact method for the coordinator is listed.\n'
    answer = 'Mistakes, gaps, and inconsistencies:\n1. No contact method for the coordinator is listed.'
    assert review._substantive(answer, source)
    assert not review._substantive(answer, 'Different notes without any coordinator.')


def test_uncertain_follow_up_preserves_its_budget_and_received_commentary():
    vague = 'The supplied material appears broadly consistent with expectations.'
    with patch('sinter.client.chat', return_value=client.ChatResult(vague)):
        first = review.run(payload())
    with patch('sinter.client.chat', side_effect=client.APIError('Connection interrupted')):
        second = review.run(payload(), resume=first)
    assert second['batches'][0]['follow_ups'] == 1
    assert second['batches'][0]['prior_content'] == vague
    assert vague in second['markdown']
    with patch('sinter.client.chat') as model:
        blocked = review.run(payload(), resume=second)
        model.assert_not_called()
    assert blocked['batches'][0]['follow_ups'] == 1
    assert blocked['batches'][0]['question'] == second['batches'][0]['question']
    with patch('sinter.client.chat', return_value=client.ChatResult(vague)):
        third = review.run(payload(), resume=blocked, retry_uncertain=True)
    assert third['batches'][0]['follow_ups'] == 1
    assert third['batches'][0]['question'].startswith(review.FOLLOW_UP_HINT)
    with patch('sinter.client.chat', return_value=client.ChatResult(vague)):
        fourth = review.run(payload(), resume=third)
    assert fourth['batches'][0]['follow_ups'] == 2
    with patch('sinter.client.chat') as model:
        fifth = review.run(payload(), resume=fourth)
        model.assert_not_called()
    assert fifth['recovery']['follow_up_exhausted'] == 1


def test_older_capped_answer_recovers_locally_without_remote_replay():
    old = saved_review()
    old['batches'][0].update(status='partial', follow_ups=2, error='Old quote-only gate rejected this.')
    with patch('sinter.client.chat') as model:
        result = review.run(payload(), resume=old)
        model.assert_not_called()
    assert result['coverage']['batches_complete'] == 1
    assert result['coverage']['requests_this_run'] == 0
    assert result['recovery']['reassessed_locally'] == 1
    assert result['batches'][0]['follow_ups'] == 2


def test_exhausted_vague_answer_retains_commentary_and_explains_recovery():
    old = saved_review()
    old['batches'][0].update(status='partial', follow_ups=2, content='This generally seems reasonable.')
    progress = []
    with patch('sinter.client.chat') as model:
        result = review.run(payload(), resume=old, progress=progress.append)
        model.assert_not_called()
    assert result['coverage']['batches_partial'] == 1
    assert result['recovery']['follow_up_exhausted'] == 1
    assert 'This generally seems reasonable.' in result['markdown']
    assert 'Follow-up attempts remaining: 0' in result['markdown']
    assert 'narrower --question' in result['markdown']
    assert any('needs manual review' in message for message in progress)


@pytest.mark.parametrize('follow_ups', [-1, 3, True, '2', None])
def test_invalid_follow_up_counter_cannot_reset_the_cap(follow_ups):
    old = saved_review()
    old['batches'][0].update(status='partial', follow_ups=follow_ups)
    with patch('sinter.client.chat') as model, pytest.raises(ValueError, match='follow-up count'):
        review.run(payload(), resume=old)
    model.assert_not_called()


def test_provider_identity_is_not_overridden_by_retry_permission(monkeypatch):
    monkeypatch.setenv('NEUROFORGE_BASE_URL', 'https://first.example/v1')
    old = saved_review()
    monkeypatch.setenv('NEUROFORGE_BASE_URL', 'https://second.example/v1')
    with patch('sinter.client.chat') as model, pytest.raises(ValueError, match='NEUROFORGE_BASE_URL'):
        review.run(payload(), resume=old, retry_uncertain=True)
    model.assert_not_called()


def test_unique_matching_checkpoint_is_discovered_without_recursing(tmp_path):
    old = saved_review()
    original = tmp_path / 'original.md.checkpoint.json'
    review.atomic_save(original, old)
    nested = tmp_path / 'nested'
    nested.mkdir()
    review.atomic_save(nested / original.name, old)
    found, recovered = review_checkpoints.resolve_checkpoint(
        tmp_path / 'other.md.checkpoint.json', old['fingerprint'], [tmp_path])
    assert found == original and recovered['fingerprint'] == old['fingerprint']


def test_duplicate_matches_require_explicit_selection(tmp_path):
    old = saved_review()
    for name in ('first', 'second'):
        review.atomic_save(tmp_path / f'{name}.md.checkpoint.json', old)
    with pytest.raises(ValueError, match='More than one matching'):
        review_checkpoints.resolve_checkpoint(tmp_path / 'missing', old['fingerprint'], [tmp_path])
    selected = tmp_path / 'first.md.checkpoint.json'
    assert review_checkpoints.resolve_checkpoint(selected, old['fingerprint'], explicit=True)[0] == selected


def test_missing_checkpoint_explains_original_output_and_identity(tmp_path):
    with pytest.raises(ValueError) as caught:
        review_checkpoints.resolve_checkpoint(tmp_path / 'missing', 'unknown', [tmp_path])
    assert '--checkpoint PATH' in str(caught.value)
    assert 'original -o path' in str(caught.value)
    assert 'API settings' in str(caught.value)
    assert '[Errno' not in str(caught.value)


def test_folder_review_rejects_output_inside_sources_before_any_request(tmp_path, capsys):
    source = tmp_path / 'notes'
    source.mkdir()
    (source / 'source.txt').write_text(SOURCE)
    with patch('sinter.client.chat') as model, pytest.raises(SystemExit) as exited:
        cli.main(['review', str(source), '--consent', '-o', str(source / 'review.md')])
    assert exited.value.code == 1
    model.assert_not_called()
    assert 'outside the folder being reviewed' in capsys.readouterr().err
    assert not (source / 'review.md').exists()


def test_current_folder_default_output_is_external_and_resumable(tmp_path, monkeypatch):
    source = tmp_path / 'notes'
    source.mkdir()
    (source / 'source.txt').write_text(SOURCE)
    monkeypatch.chdir(source)
    with patch('sinter.client.chat', return_value=client.ChatResult(FINDING)):
        cli.main(['review', '.', '--consent'])
    assert (tmp_path / 'notes.review.md').exists()
    assert sorted(path.name for path in source.iterdir()) == ['source.txt']
    with patch('sinter.client.chat') as model:
        cli.main(['review', '.', '--consent', '--resume'])
        model.assert_not_called()


@pytest.mark.parametrize('kind', ['same', 'hardlink', 'symlink'])
def test_review_cannot_overwrite_a_single_file_source(tmp_path, capsys, kind):
    source = tmp_path / 'source.txt'
    source.write_text(SOURCE)
    output = source if kind == 'same' else tmp_path / 'output.md'
    if kind == 'hardlink':
        os.link(source, output)
    elif kind == 'symlink':
        output.symlink_to(source)
    with patch('sinter.client.chat') as model, pytest.raises(SystemExit) as exited:
        cli.main(['review', str(source), '-o', str(output)])
    assert exited.value.code == 1
    model.assert_not_called()
    assert source.read_text() == SOURCE
    assert 'Sinter:' in capsys.readouterr().err


def test_literal_home_folder_path_still_requires_consent(tmp_path, monkeypatch, capsys):
    source = tmp_path / 'notes'
    source.mkdir()
    (source / 'source.txt').write_text(SOURCE)
    monkeypatch.setenv('HOME', str(tmp_path))
    # pathlib uses HOME on POSIX and USERPROFILE on Windows. Exercise the
    # consent check against an existing home-relative folder on both platforms.
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    assert Path('~/notes').expanduser() == source
    with patch('sinter.client.chat') as model, pytest.raises(SystemExit) as exited:
        cli.main(['review', '~/notes'])
    assert exited.value.code == 1
    model.assert_not_called()
    assert 'Folder review sends text to the API' in capsys.readouterr().err


@pytest.mark.parametrize('body', ['invalid json', '[]'])
def test_invalid_checkpoint_reports_a_clean_error(tmp_path, body):
    target = tmp_path / 'bad.checkpoint.json'
    target.write_text(body)
    with pytest.raises(ValueError, match='checkpoint'):
        review_checkpoints.read_checkpoint(target)


def test_checkpoint_symlinks_and_oversized_files_are_rejected(tmp_path, monkeypatch):
    target = tmp_path / 'review.checkpoint.json'
    target.write_text('{}')
    link = tmp_path / 'link.checkpoint.json'
    link.symlink_to(target)
    with pytest.raises(ValueError, match='symbolic link'):
        review_checkpoints.read_checkpoint(link)
    monkeypatch.setattr(review_checkpoints, 'MAX_CHECKPOINT_BYTES', 1)
    with pytest.raises(ValueError, match='smaller than'):
        review_checkpoints.read_checkpoint(target)


def test_incomplete_discovery_never_auto_selects_a_checkpoint(tmp_path, monkeypatch):
    old = saved_review()
    review.atomic_save(tmp_path / 'first.checkpoint.json', old)
    review.atomic_save(tmp_path / 'second.checkpoint.json', old)
    monkeypatch.setattr(review_checkpoints, 'MAX_DISCOVERY_ENTRIES', 1)
    with pytest.raises(ValueError, match='safety limit'):
        review_checkpoints.resolve_checkpoint(tmp_path / 'missing', old['fingerprint'], [tmp_path])


def test_cli_resume_can_move_output_and_preserves_receipt(tmp_path, monkeypatch, capsys):
    source = tmp_path / 'notes.txt'
    source.write_text(SOURCE)
    first, second = tmp_path / 'first.md', tmp_path / 'second.md'
    monkeypatch.chdir(tmp_path)
    with patch('sinter.client.chat', return_value=client.ChatResult(FINDING)):
        cli.main(['review', str(source), '-o', str(first)])
    original = Path(str(first) + '.checkpoint.json').read_bytes()
    with patch('sinter.client.chat') as model:
        cli.main(['review', str(source), '--resume', '-o', str(second)])
        model.assert_not_called()
    assert Path(str(first) + '.checkpoint.json').read_bytes() == original
    assert Path(str(second) + '.checkpoint.json').exists()
    assert FINDING in second.read_text()
    assert 'Resuming saved progress from:' in capsys.readouterr().err


def test_cli_explicit_checkpoint_and_exhausted_answer_have_actionable_output(tmp_path, monkeypatch, capsys):
    source = tmp_path / 'notes.txt'
    source.write_text(SOURCE)
    monkeypatch.chdir(tmp_path)
    local_payload, _ = review.load_collection(source)
    old = review.run(local_payload, offline=True)
    old['batches'] = [{'id': review.plan(local_payload)[2][0]['id'], 'status': 'partial',
                      'content': 'The material seems broadly reasonable.', 'follow_ups': 2}]
    checkpoint = tmp_path / 'original.json'
    review.atomic_save(checkpoint, old)
    with patch('sinter.client.chat') as model, pytest.raises(SystemExit) as exited:
        cli.main(['review', str(source), '--resume', '--checkpoint', str(checkpoint), '-o', 'recovered.md'])
    assert exited.value.code == 2
    model.assert_not_called()
    error = capsys.readouterr().err
    assert 'manual review' in error and 'narrower --question' in error
    assert 'Continue saved work:' not in error


def test_console_entrypoint_and_module_print_help_under_a_pipe():
    environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1] / 'src')}
    for arguments in (['-m', 'sinter'], ['-m', 'sinter.cli'],
                      ['-c', 'from sinter.cli import launch; launch()']):
        result = subprocess.run([sys.executable, *arguments], capture_output=True, text=True,
                                env=environment, timeout=5)
        assert result.returncode == 0
        assert 'usage: sinter' in result.stdout
        assert 'serve' in result.stdout


def test_explicit_serve_still_dispatches_to_the_workbench():
    with patch('sinter.server.serve') as serve:
        cli.main(['serve', '--no-browser'])
    serve.assert_called_once_with('127.0.0.1', 8420, False)


def test_research_cli_dispatches_research_questions(tmp_path):
    output = tmp_path / 'research.md'
    with patch('sinter.workbench.run', return_value={'markdown': 'Cited research'}) as run:
        cli.main(['research', 'Community gardens', '-q', 'Which locations?', '-q', 'Who can apply?', '-o', str(output)])
    sent = run.call_args.args[0]
    assert sent['workflow'] == 'research'
    assert sent['questions'] == 'Which locations?\nWho can apply?'
    assert sent['use_search'] is True
    assert output.read_text() == 'Cited research'


@pytest.mark.parametrize('streamed', [False, True])
def test_cli_retains_completed_and_partial_template_work_with_sources(tmp_path, capsys, streamed):
    from sinter.templates import TemplateStepError
    output = tmp_path / 'partial.md'
    partial = {'type': 'step_partial', 'step': 'Expand', 'index': 1,
               'content': 'Unfinished but useful text', 'tokens': 512, 'max_tokens': 512,
               'finish_reason': 'length', 'error': 'Reached the answer limit.', 'complete': False}

    def events(*args, **kwargs):
        yield {'type': 'step', 'index': 0, 'total': 2, 'name': 'Outline'}
        yield {'type': 'sources', 'sources': [{'url': 'https://example.org/source'}]}
        yield {'type': 'step_done', 'step': 'Outline', 'content': 'Saved outline'}
        yield {'type': 'step', 'index': 1, 'total': 2, 'name': 'Expand'}
        if streamed:
            yield {'type': 'token', 't': partial['content']}
        yield partial
        raise TemplateStepError(partial)

    with patch('sinter.templates.template_events', events), pytest.raises(SystemExit) as exited:
        cli.main(['template', 'research', '-v', 'topic=Gardens', '-o', str(output)])
    assert exited.value.code == 1
    report = output.read_text()
    assert 'INCOMPLETE' in report
    assert 'Saved outline' in report and partial['content'] in report
    assert 'https://example.org/source' in report
    captured = capsys.readouterr()
    assert captured.out.count(partial['content']) == 1
    assert 'INCOMPLETE: Expand' in captured.err
