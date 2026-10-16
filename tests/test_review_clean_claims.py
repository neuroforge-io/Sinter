"""Negated clean results and historical coverage must not become completion."""
import copy
from unittest.mock import patch

import pytest

from sinter import cli, client, review
from sinter.review_clean_claims import explicit_clean_result

SOURCE = 'The booking deadline is Friday at noon.\nThe coordinator is not named.\n'
NEGATED = ('Not all checks passed; this answer does not establish that the '
           'supplied material is correct.')
GROUNDED = 'Line 2: The coordinator is not named; assign a person responsible for confirmations.'


@pytest.fixture(autouse=True)
def explicit_legacy_model(monkeypatch):
    monkeypatch.setenv('NEUROFORGE_MODEL', client.MODEL)


def payload():
    return {'title': 'Fictional review', 'documents': [{'title': 'notes.txt', 'content': SOURCE}]}


@pytest.mark.parametrize('answer', [
    'No issues found after checking the supplied material.',
    'No problems detected after reviewing the supplied material.',
    'No mistakes noted in the supplied excerpt.',
    'No demonstrated issues. I checked the date consistency and responsibilities in the supplied excerpt.',
    'No confirmed errors in the supplied material.',
    'No substantiated bugs in the supplied material.',
    'Nothing was demonstrated after checking the supplied material.',
    'No issues were demonstrated after checking the supplied material.',
    'All checks passed after checking the supplied material.',
    'All checks ok after checking the supplied material.',
    'Nothing wrong with the supplied material.',
    'Nothing found after checking the supplied material.',
    'Nothing to report after checking the supplied material.',
    'Unverified fictional commentary: no issues found after checking the supplied material.',
    'Explicit retry: no issues found after checking the supplied material.',
    'Unverified first review: no issues found after checking the supplied material.',
    'Remaining review: no issues found after checking the supplied material.',
    '**No issues found.** I checked the supplied material.',
    '- No issues found after checking the supplied material.',
    'No issues found after checking the supplied module.py file.',
    'No issues found in the supplied unconfirmed draft.',
    'No issues found after checking the provided source material.',
    'No issues found after checking module.py.',
    'No issues found after checking the committee’s records.',
    'No issues found after checking the supplied follow-up-notes.md file.',
    'No issues found after checking the supplied material.\n\nI checked the date consistency and responsibilities.',
])
def test_affirmative_clean_results_preserve_existing_admission(answer):
    assert explicit_clean_result(answer)
    assert review._substantive(answer, SOURCE)


@pytest.mark.parametrize('answer', [
    NEGATED,
    "No issues found in the supplied material; that wasn't the actual result.",
    'No issues found in the supplied material — that wasn’t the actual result.',
    'No issues found in the supplied material - that wasn’t the actual result.',
    'No issues found in the supplied material: that wasn’t the actual result.',
    "No issues found after checking material that wasn't actually reviewed.",
    'No issues found after checking material that wasn’t actually reviewed.',
    'No issues found. That wasn’t the actual result.',
    'No issues found. I checked the supplied material; that wasn’t the actual result.',
    "No issues found after checking the supplied material.\n\nThat wasn't the actual result.",
    'No issues found after checking the supplied material.\n\nI checked whether the template says all checks passed.',
    'No issues found? I checked the supplied material.',
    'No issues found, except for the remaining unreviewed source material.',
    'No issues found—provided the missing source later supports that claim.',
    'No issues found after checking the supplied material, although the review is incomplete.',
    'No issues found is not an accurate description of this incomplete review.',
    'It is false that all checks passed for this material; the checks were incomplete.',
    'Not every check passed; the phrase all checks passed would be inaccurate.',
    'If all checks passed, the reviewer could say that no issues found is the result.',
    'All checks passed if the missing evidence is later supplied.',
    'No issues found would be a premature conclusion for this material.',
    'No issues found after checking the template phrase, not the supplied material.',
    'No issues found. That result would be inaccurate because the review is incomplete.',
    'No issues found. I checked whether the template says all checks passed.',
    'Expected result: no issues found after checking the supplied material.',
    'Example: no issues found after checking the supplied material.',
    'The words no issues found are a suggested label, not the outcome of this review.',
    'Review: the phrase no issues found does not establish completion of any check.',
    '“No issues found after checking the supplied material.”',
    '"No issues found after checking the supplied material."',
    '`No issues found after checking the supplied material.`',
    '> No issues found after checking the supplied material.',
    '```text\nNo issues found after checking the supplied material.\n```',
    '```text\n\nNo issues found after checking the supplied material.\n\n```',
    '~~~text\n\nNo issues found after checking the supplied material.\n\n~~~',
    '```text\n\nNo issues found after checking the supplied material.',
])
def test_non_asserted_clean_words_do_not_complete_review(answer):
    assert not explicit_clean_result(answer)
    assert not review._substantive(answer, SOURCE)


def test_rejecting_clean_shortcut_does_not_hide_a_separate_grounded_finding():
    assert review._substantive(NEGATED + '\n\n' + GROUNDED, SOURCE)
    assert review._substantive('“No issues found.”\n\n' + GROUNDED, SOURCE)


def old_done(*, follow_ups=0):
    old = review.run(payload(), offline=True)
    chunk = review.plan(payload())[2][0]
    old['batches'] = [{'id': chunk['id'], 'status': 'done', 'content': NEGATED,
                       'question': review.DEFAULT_QUESTION, 'follow_ups': follow_ups}]
    return old


@pytest.mark.parametrize('recovery_version', [1, 2])
def test_old_done_is_reclassified_without_a_request_or_rewriting_history(recovery_version):
    old = old_done()
    old['recovery_version'] = recovery_version
    original = copy.deepcopy(old)
    with patch('sinter.client.chat') as model:
        result = review.run(payload(), resume=old)
    model.assert_not_called()
    assert old == original
    assert result['coverage']['batches_complete'] == 0
    assert result['coverage']['batches_partial'] == 1
    assert result['coverage']['requests_this_run'] == 0
    assert result['recovery']['reclassified_locally'] == 1
    row = result['batches'][0]
    assert row['status'] == 'partial' and row['content'] == NEGATED
    assert row['follow_ups'] == 0
    assert row['prior_assessment'] == {
        'status': 'done', 'content': NEGATED, 'question': review.DEFAULT_QUESTION,
        'follow_ups': 0, 'reason': 'clean_result_reassessed'}
    assert 'Historical classification: DONE' in result['markdown']
    assert 'Reclassified locally; no request was sent' in result['markdown']


def test_updated_checkpoint_allows_one_explicit_bounded_followup_and_retains_original():
    with patch('sinter.client.chat') as model:
        first = review.run(payload(), resume=old_done())
        model.assert_not_called()
    original = copy.deepcopy(first)
    with patch('sinter.client.chat', return_value=client.ChatResult(GROUNDED)) as model:
        second = review.run(payload(), resume=first, max_parts=1)
    model.assert_called_once()
    assert first == original
    assert second['coverage']['batches_complete'] == 1
    assert second['coverage']['requests_this_run'] == 1
    assert second['batches'][0]['follow_ups'] == 1
    assert second['batches'][0]['prior_assessment'] == first['batches'][0]['prior_assessment']
    assert NEGATED in second['markdown'] and GROUNDED in second['markdown']
    with patch('sinter.client.chat') as model:
        third = review.run(payload(), resume=second)
    model.assert_not_called()
    assert third['batches'][0]['prior_assessment'] == first['batches'][0]['prior_assessment']


def test_historical_reclassification_does_not_reset_exhausted_followups():
    with patch('sinter.client.chat') as model:
        first = review.run(payload(), resume=old_done(follow_ups=2))
        second = review.run(payload(), resume=first)
    model.assert_not_called()
    assert first['recovery']['follow_up_exhausted'] == second['recovery']['follow_up_exhausted'] == 1
    assert second['batches'][0]['follow_ups'] == 2
    assert second['batches'][0]['prior_assessment']['follow_ups'] == 2


def test_interrupted_followup_preserves_history_and_stays_blocked_without_retry_permission():
    with patch('sinter.client.chat'):
        first = review.run(payload(), resume=old_done())
    with patch('sinter.client.chat', side_effect=client.APIError('Interrupted')):
        second = review.run(payload(), resume=first)
    assert second['batches'][0]['status'] == 'uncertain_remote_outcome'
    assert second['batches'][0]['follow_ups'] == 1
    with patch('sinter.client.chat') as model:
        third = review.run(payload(), resume=second)
    model.assert_not_called()
    assert third['batches'][0]['status'] == 'uncertain_remote_outcome'
    assert third['batches'][0]['prior_assessment'] == first['batches'][0]['prior_assessment']
    assert third['batches'][0]['prior_content'] == NEGATED
    with patch('sinter.client.chat', return_value=client.ChatResult(GROUNDED)) as model:
        fourth = review.run(payload(), resume=third, retry_uncertain=True, max_parts=1)
    model.assert_called_once()
    assert fourth['batches'][0]['follow_ups'] == 1
    assert fourth['batches'][0]['prior_assessment'] == first['batches'][0]['prior_assessment']


@pytest.mark.parametrize('change', [
    {'status': 'partial'}, {'follow_ups': True}, {'follow_ups': 3},
    {'content': ['invalid']}, {'reason': 'unknown'}, {'extra': 'invalid'},
])
def test_invalid_historical_assessments_fail_before_remote_work(change):
    with patch('sinter.client.chat'):
        first = review.run(payload(), resume=old_done())
    first['batches'][0]['prior_assessment'].update(change)
    with patch('sinter.client.chat') as model, pytest.raises(ValueError):
        review.run(payload(), resume=first)
    model.assert_not_called()


def test_cli_consent_does_not_replay_reclassified_done_on_first_resume(tmp_path, capsys):
    folder = tmp_path / 'fictional'; folder.mkdir()
    (folder / 'notes.txt').write_text(SOURCE, encoding='utf-8')
    local_payload, _ = review.load_collection(folder)
    old = review.run(local_payload, offline=True)
    chunk = review.plan(local_payload)[2][0]
    old['batches'] = [{'id': chunk['id'], 'status': 'done', 'content': NEGATED,
                       'question': review.DEFAULT_QUESTION, 'follow_ups': 0}]
    output = tmp_path / 'review.md'
    receipt = tmp_path / 'review.md.checkpoint.json'; review.atomic_save(receipt, old)
    with patch('sinter.client.chat') as model, pytest.raises(SystemExit) as exited:
        cli.main(['review', str(folder), '--resume', '--consent', '-o', str(output)])
    model.assert_not_called()
    assert exited.value.code == 3
    assert 'Historical classification: DONE' in output.read_text(encoding='utf-8')
    assert 'follow-up' in capsys.readouterr().err
    with patch('sinter.client.chat', return_value=client.ChatResult(GROUNDED)) as model:
        cli.main(['review', str(folder), '--resume', '--consent', '-o', str(output)])
    model.assert_called_once()


def test_reclassified_history_is_checkpointed_before_any_other_generation():
    book = {'title': 'Two fictional notes', 'documents': [
        {'title': 'first.txt', 'content': SOURCE},
        {'title': 'second.txt', 'content': 'Other fictional notes needing review.'}]}
    old = review.run(book, offline=True)
    chunk = review.plan(book)[2][0]
    old['batches'] = [{'id': chunk['id'], 'status': 'done', 'content': NEGATED,
                       'question': review.DEFAULT_QUESTION, 'follow_ups': 0}]
    snapshots = []

    def refuse_write(state):
        snapshots.append(copy.deepcopy(state))
        historical = next(row for row in state['batches'] if row['id'] == chunk['id'])
        assert historical['status'] == 'partial'
        assert historical['prior_assessment']['status'] == 'done'
        assert historical['content'] == NEGATED
        raise OSError('Fictional checkpoint write failed')

    with patch('sinter.client.chat') as model, pytest.raises(OSError, match='write failed'):
        review.run(book, resume=old, on_checkpoint=refuse_write)
    model.assert_not_called()
    assert len(snapshots) == 1
