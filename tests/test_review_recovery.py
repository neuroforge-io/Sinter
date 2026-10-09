"""User-facing review recovery regressions; responses are deterministic fixtures."""
import json
import os
import runpy
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from unittest.mock import patch

import pytest

from wrapper_diagnostics import MAX_SAMPLE_BYTES, PHASES, _snapshot, observe_wrapper

from sinter import cli, client, review, review_checkpoints



@pytest.fixture(autouse=True)
def explicit_legacy_model(monkeypatch):
    """Legacy transport/recovery fixtures keep an explicit backend identity."""
    monkeypatch.setenv("NEUROFORGE_MODEL", "erais-fracture-gemma")


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
    'Line 2: One instruction gives Friday at noon and the earlier instruction gives Thursday.',
    'Line 2: The date differs from the earlier booking instruction.',
    'Line 2: The deadline does not match the earlier date.',
    'Line 2: The stated due date contradicts the earlier Thursday deadline.',
    'L2: The booking deadline conflicts with Thursday in the earlier instruction; choose one deadline.',
    'The statement “The booking deadline is Friday at noon.” conflicts with the previous deadline.',
    'No demonstrated issues. I checked the date consistency and responsibilities in the supplied excerpt.',
    'Line 3: The coordinator is not named; assign a person responsible for confirmations.',
])
def test_grounded_prose_findings_are_usable_without_literal_quotes(text):
    assert review._substantive(text, SOURCE)


def test_grounded_absence_can_be_paraphrased_without_a_verbatim_quote():
    source = 'No contact method for the coordinator is listed.\n'
    assert review._substantive(
        'Line 1: The contact method for the coordinator is absent.', source)


@pytest.mark.parametrize('finding', [
    'Line 1: There is no contact method for the coordinator.',
    'Line 1: The contact method for the coordinator is not available.',
])
def test_common_grounded_absence_phrasings_are_substantive(finding):
    source = 'The contact method for the coordinator is not listed.\n'
    assert review._substantive(finding, source)


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


@pytest.mark.parametrize(('answer', 'source'), [
    ('Line 1: Exporting member accommodation details risks information disclosure to public readers; '
     'restrict the export to authorised committee users.',
     'The public export includes member names and accommodation details.\n'),
    ('Line 1: An authorization bypass could allow an unauthenticated request to update a record; '
     'authorize the caller role in this request handler.',
     'The request handler updates access permissions before checking the user role.\n'),
    ('Line 1: This path traversal can overwrite files outside the workspace; constrain the user path '
     'to the workspace root.',
     'The export handler joins a request-provided filename onto the workspace root and writes it '
     'without checking the resolved destination.\n'),
])
def test_specific_line_findings_require_matching_source_evidence(answer, source):
    # A line number and a vulnerability label are insufficient by themselves.
    assert review._substantive(answer, source)


def test_safe_path_resolution_is_not_reported_as_path_traversal():
    answer = ('Line 1: This path traversal can overwrite files outside the workspace; '
              'resolve the user path before writing the destination.')
    source = 'Resolve the user-supplied file path under the workspace before writing the destination.\n'
    assert not review._substantive(answer, source)


@pytest.mark.parametrize('answer', [
    'Line 1: This is an information disclosure concern. Please review.',
    'Line 1: This looks bad and should be fixed to make the document better.',
    'Line 1: This creates an information disclosure risk that could expose private contact details; '
    'please provide the source document before I can review it.',
])
def test_line_location_does_not_admit_vague_or_unavailable_findings(answer):
    source = 'Member names and accommodation details are included in this export.\n'
    assert not review._substantive(answer, source)


@pytest.mark.parametrize(('answer', 'source'), [
    ('Line 1: This creates SQL injection because students update attendance records; '
     'validate input.', 'Students update attendance records each morning.\n'),
    ('Line 1: This authorization bypass lets attendees access the newsletter; '
     'check permissions.', 'Picnic attendees receive the newsletter each Friday.\n'),
    ('Line 1: Member accommodation details appear in this export; improve the document.',
     'Member names and accommodation details are included in this export.\n'),
])
def test_line_numbers_and_shared_words_do_not_support_an_unrelated_failure(answer, source):
    assert not review._substantive(answer, source)


def test_single_shared_word_does_not_ground_a_line_numbered_finding():
    answer = 'Line 1: The coordinator deadline is inconsistent and should be updated.'
    assert not review._substantive(answer, 'The coordinator confirms available garden spaces.\n')


@pytest.mark.parametrize('answer', [
    'Line 1: Applicant eligibility evidence is not provided.',
    'The source says “No applicant email is listed.” Applicant eligibility evidence is not provided.',
])
def test_a_generic_omission_cannot_borrow_one_unrelated_source_word(answer):
    assert not review._substantive(answer, 'No applicant email is listed.\n')


def test_a_matching_quote_does_not_ground_an_unrelated_security_claim():
    answer = ('The statement “The booking deadline is Friday at noon.” is a path traversal '
              'vulnerability. Please fix it.')
    assert not review._substantive(answer, SOURCE)


def test_a_matching_quote_does_not_launder_an_unrelated_deadline_claim():
    answer = ('The statement “The booking deadline is Friday at noon.” is inconsistent '
              'with the school pool depth; change the deadline.')
    assert not review._substantive(answer, SOURCE)


@pytest.mark.parametrize('answer', [
    '“No contact method for the coordinator is listed.”',
    'Line 1: “No contact method for the coordinator is listed.”',
])
def test_a_source_quote_without_a_finding_does_not_complete_a_review(answer):
    assert not review._substantive(
        answer, 'No contact method for the coordinator is listed.\n')


def test_repeating_quoted_nouns_does_not_support_an_unrelated_claim():
    answer = ('The statement “The booking deadline is Friday at noon.” shows that the '
              'booking deadline is inconsistent with the school pool depth.')
    assert not review._substantive(answer, SOURCE)


def test_a_quote_can_support_a_grounded_absence_paraphrase():
    source = 'No contact method for the coordinator is listed.\n'
    answer = 'The source says “No contact method for the coordinator is listed.” That contact method is absent.'
    assert review._substantive(answer, source)


def test_a_supplied_wording_can_paraphrase_a_quoted_absence():
    source = 'No contact method for the coordinator is listed.\n'
    answer = 'The source says “No contact method for the coordinator is listed.” No coordinator contact details are supplied.'
    assert review._substantive(answer, source)


def test_unrelated_weekday_events_cannot_be_joined_into_a_false_conflict():
    source = 'The school pool is open Thursday.\nThe library room is bookable Friday.\n'
    answer = ('Line 1: The Friday booking deadline conflicts with Thursday pool access; '
              'correct the deadline.')
    assert not review._substantive(answer, source)


def test_two_dates_on_one_line_can_support_a_specific_deadline_conflict():
    source = 'The deadline is Thursday, while the summary says Friday.\n'
    answer = 'Line 1: The deadline conflicts: Thursday versus Friday.'
    assert review._substantive(answer, source)


@pytest.mark.parametrize(('source', 'answer'), [
    ('The booking deadline is 3 October.\n',
     'Line 1: The booking deadline conflicts: 3 October versus 4 October.'),
    ('The application closes on 3 October.\n',
     'Line 1: The application deadline conflicts with the portal date of 4 October.'),
    ('The school meeting is 3 October; the grant deadline is 4 October.\n',
     'Line 1: The application deadline conflicts: 3 October versus 4 October.'),
])
def test_unsupported_or_unrelated_numeric_dates_cannot_certify_a_conflict(source, answer):
    assert not review._substantive(answer, source)


def test_two_same_subject_calendar_dates_can_support_a_conflict():
    source = 'The application deadline is 3 October; the portal says 4 October.\n'
    answer = 'Line 1: The application deadline conflicts: 3 October versus 4 October.'
    assert review._substantive(answer, source)


def test_calendar_conflict_can_omit_year_when_source_dates_include_it():
    source = 'The application deadline is 3 October 2026; the portal says 4 October 2026.\n'
    answer = 'Line 1: The application deadline conflicts: 3 October versus 4 October.'
    assert review._substantive(answer, source)


@pytest.mark.parametrize(('source', 'answer'), [
    ('The meeting starts Thursday; the form about meal delivery is due Friday.\n',
     'Line 1: The meeting schedule conflicts: Thursday versus Friday.'),
    ('The booking check is Thursday; the performance summary will be delivered Friday.\n',
     'Line 1: The booking deadline conflicts: Thursday versus Friday.'),
])
def test_unrelated_context_in_a_form_or_summary_cannot_inherit_a_date_topic(source, answer):
    assert not review._substantive(answer, source)


def test_two_unrelated_events_on_one_line_are_not_a_date_conflict():
    source = 'Pool access is available Thursday; the library booking deadline is Friday.\n'
    answer = ('Line 1: The Friday booking deadline conflicts with Thursday pool access; '
              'correct the deadline.')
    assert not review._substantive(answer, source)


@pytest.mark.parametrize(('answer', 'source'), [
    ('Line 1: Server-side request forgery could expose internal data; restrict the webhook URL target.',
     'The webhook fetches a user-supplied URL without checking the target address.\n'),
    ('Line 1: An IDOR could allow a user to read another account’s record; authorize the owner before returning data.',
     'The endpoint loads a record by ID without checking which user owns it.\n'),
])
def test_common_security_findings_can_be_substantive_when_the_cited_flow_supports_them(answer, source):
    assert review._substantive(answer, source)


@pytest.mark.parametrize(('answer', 'source'), [
    ('Line 1: Server-side request forgery could expose internal data; restrict the webhook URL target.',
     'The webhook fetches a user-supplied URL target only after validating it against an internal-address denylist.\n'),
    ('Line 1: SQL injection could expose member records; parameterize the user input.',
     'The member lookup uses a parameterized SQL query for user-supplied values.\n'),
    ('Line 1: An IDOR could allow a user to read another account’s record; authorize the owner before returning data.',
     'The endpoint loads a record by ID only after verifying the requesting user owns it.\n'),
    ('Line 1: Cross-site scripting could execute user content; escape the HTML before rendering.',
     'The renderer escapes user-supplied HTML content before displaying it.\n'),
])
def test_security_labels_cannot_override_source_describing_a_safeguard(answer, source):
    assert not review._substantive(answer, source)


@pytest.mark.parametrize(('answer', 'source', 'expected'), [
    ('Line 1: Server-side request forgery could expose internal data; restrict the webhook URL target.',
     'The webhook fetches a user-supplied URL without validating the target against an internal-address denylist.\n', True),
    ('Line 1: Server-side request forgery could expose internal data; restrict the webhook URL target.',
     'No validation is applied to the webhook user-supplied URL target; localhost and private networks are reachable.\n', True),
    ('Line 1: Server-side request forgery could expose internal data; restrict the webhook URL target.',
     'Validation of the webhook URL target is missing, so internal addresses remain reachable.\n', True),
    ('Line 1: Server-side request forgery could expose internal data; restrict the webhook URL target.',
     'The webhook fetches a user-supplied URL target; it is validated for syntax only, not against private network destinations.\n', True),
    ('Line 1: Server-side request forgery could expose internal data; restrict the webhook URL target.',
     "The webhook isn't validated against internal addresses, so user-supplied URLs can reach the private network.\n", True),
    ('Line 1: Command injection could run arbitrary shell commands; escape the user argument.',
     'The handler safely escapes the user argument before passing it to the shell command.', False),
    ('Line 1: An authorization bypass could allow an unauthenticated request to update a record; authorize the caller role in this request handler.',
     'The API route authenticates every request and checks the caller role before updating the record.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export excludes member contact details and includes only committee-approved fields.\n', False),
    ('Line 1: Sensitive data leak could expose member contact details in the public report; restrict it to committee users.',
     'Member contact details are excluded from the public report.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'Member contact details are withheld from the public export.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'Member contact details are only available to committee users.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'Member contact details are not withheld from the public export; the export includes those fields.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'Member contact details are only available to committee users in the internal register, but the public export includes all contact fields.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, but it also includes member contact details.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details; however, it includes member contact details.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details. The public export also includes member contact details.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, while also publishing member contact details.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, but includes member counts.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, but includes committee contact details.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, but does not include contact details.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, but includes member accommodation details.\n', False),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export excludes contact details; however, member contact details are still available on the public download.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, but publishes member phone numbers.\n', True),
    ('Line 1: Information disclosure could expose member contact details in a public export; restrict it to committee users.',
     'The public export contains all member fields except contact details, but publishes member email addresses.\n', True),
    ('Line 1: Information disclosure could expose member email addresses in a public export; restrict it to committee users.',
     'The public export contains all member fields except email addresses, but publishes member phone numbers.\n', False),
])
def test_negated_or_qualified_safeguards_do_not_hide_or_invent_findings(answer, source, expected):
    assert review._substantive(answer, source) is expected


def test_folder_cli_accepts_specific_line_numbered_findings_without_follow_up(tmp_path, monkeypatch, capsys):
    folder = tmp_path / 'community-records'
    folder.mkdir()
    (folder / 'register.txt').write_text(
        'Member names and accommodation details are included in this export.\n', encoding='utf-8')
    (folder / 'volunteers.txt').write_text(
        'Volunteer phone numbers are included in this contact sheet.\n', encoding='utf-8')
    output = tmp_path / 'review.md'
    monkeypatch.chdir(tmp_path)
    responses = [
        'Line 1: Exporting member accommodation details risks information disclosure to public readers; '
        'restrict the export to authorised committee users.',
        'Line 1: Missing owner for these volunteer phone numbers; confirm who may use them.',
    ]
    with patch('sinter.client.chat', side_effect=[client.ChatResult(text) for text in responses]) as model:
        cli.main(['review', str(folder), '--consent', '-o', str(output)])

    assert model.call_count == 2
    report = output.read_text(encoding='utf-8')
    assert report.count('Status: done') == 2
    assert 'Status: partial' not in report
    assert 'batches_complete": 2' in capsys.readouterr().out


@pytest.mark.parametrize(
    ('outcome', 'expected_exit', 'expected_message'),
    [
        ('partial', 3, 'Review needs follow-up'),
        ('failed', 1, 'Review incomplete'),
        ('uncertain', 1, 'Review incomplete'),
    ],
)
def test_cli_exit_codes_distinguish_follow_up_from_hard_failures(
    tmp_path, capsys, outcome, expected_exit, expected_message
):
    source = tmp_path / 'source.txt'
    source.write_text(SOURCE, encoding='utf-8')
    if outcome == 'partial':
        response = client.ChatResult('The supplied material appears broadly consistent with expectations.')
        patcher = patch('sinter.client.chat', return_value=response)
    elif outcome == 'failed':
        patcher = patch('sinter.client.chat', return_value=client.ChatResult('Truncated', finish_reason='length'))
    else:
        patcher = patch('sinter.client.chat', side_effect=client.APIError('Connection interrupted'))

    with patcher, pytest.raises(SystemExit) as exited:
        cli.main(['review', str(source), '-o', str(tmp_path / 'review.md')])

    assert exited.value.code == expected_exit
    assert expected_message in capsys.readouterr().err


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
    assert exited.value.code == 3
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


@pytest.mark.parametrize('arguments, expected', [
    (['serve'], ('127.0.0.1', 8420, True)),
    (['serve', '--no-browser', '--port', '9000'], ('127.0.0.1', 9000, False)),
])
def test_source_launcher_preserves_explicit_serve_options(
    monkeypatch, arguments, expected,
):
    launcher = Path(__file__).parents[1] / 'start.py'
    monkeypatch.setattr(sys, 'argv', [str(launcher), *arguments])
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    with patch('sinter.server.serve') as serve:
        runpy.run_path(str(launcher), run_name='__main__')
    serve.assert_called_once_with(*expected)


@pytest.mark.parametrize('argument, expected', [
    ('--help', 'usage: sinter'), ('--version', 'sinter '),
])
def test_source_launcher_preserves_help_and_version(monkeypatch, capsys, argument, expected):
    launcher = Path(__file__).parents[1] / 'start.py'
    monkeypatch.setattr(sys, 'argv', [str(launcher), argument])
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    with patch('sinter.server.serve') as serve, pytest.raises(SystemExit) as exited:
        runpy.run_path(str(launcher), run_name='__main__')
    assert exited.value.code == 0
    serve.assert_not_called()
    assert expected in capsys.readouterr().out


def test_source_launcher_preserves_other_commands(monkeypatch, capsys):
    launcher = Path(__file__).parents[1] / 'start.py'
    monkeypatch.setattr(sys, 'argv', [str(launcher), 'health'])
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    with patch('sinter.server.serve') as serve, patch.object(
        client, 'health_check', return_value=(True, 'Fictional connection'),
    ) as health, pytest.raises(SystemExit) as exited:
        runpy.run_path(str(launcher), run_name='__main__')
    assert exited.value.code == 0
    serve.assert_not_called()
    health.assert_called_once_with()
    assert 'OK: Fictional connection' in capsys.readouterr().out


def _wrapper_entry_source(marker: Path, stages: Path) -> str:
    """Keep the first Python instruction observable before fixture imports.

    Args:
        marker: Final structured runtime marker belonging to this fixture.
        stages: Fresh append-only file containing closed raw stage observations.

    Returns:
        A zero-work fixture script. It imports no Sinter product code.
    """
    def stage(value: str) -> str:
        return (
            f"with open({str(stages)!r}, 'ab', buffering=0) as retained:\n"
            f"    retained.write({(value + chr(10)).encode()!r})\n"
        )

    return (
        stage('python_entered')
        + 'import sys\n'
        + stage('sys_imported')
        + f"with open({str(stages)!r}, 'ab', buffering=0) as retained:\n"
        + "    retained.write(('runtime=' + repr((sys.executable, sys.version, "
        "sys.argv)) + '\\n').encode('utf-8'))\n"
        + 'import os\n'
        + stage('os_imported')
        + 'import json\n'
        + stage('json_imported')
        + 'from pathlib import Path\n'
        + stage('pathlib_imported')
        + 'observation = {"executable": sys.executable, "version": sys.version, '
        '"version_info": list(sys.version_info[:3]), "argv": sys.argv, '
        '"cwd": os.getcwd(), "pid": os.getpid(), "prefix": sys.prefix, '
        '"base_prefix": sys.base_prefix}\n'
        + f'Path({str(marker)!r}).write_text(json.dumps(observation), '
        'encoding="utf-8")\n'
        + stage('marker_written')
        + 'print(json.dumps({"arguments": sys.argv[1:], "cwd": os.getcwd()}))\n'
    )


def _wrapper_stage_observation(stages: Path) -> dict:
    """Read a bounded snapshot without claiming final descendant evidence.

    Args:
        stages: Owned raw stage file, which may be absent or incomplete.

    Returns:
        Actual bounded bytes and decoded lines when complete. Missing evidence
        leaves Python entry unknown rather than claiming absence or success.
    """
    value, raw = _snapshot(stages, limit=MAX_SAMPLE_BYTES)
    value['python_entered'] = None
    if raw is not None:
        try:
            value['lines'] = raw.decode('utf-8').splitlines()
            if raw.startswith(b'python_entered\n'):
                value['python_entered'] = True
        except UnicodeError as error:
            value['decode_error'] = f'{type(error).__name__}: {error}'
    return value


_BATCH_WRAPPER_PHASES = PHASES['batch']


def _wrapper_batch_stage_observation(stages: Path) -> dict:
    """Read only closed fixed phase names; absent or invalid evidence is unknown.

    This reuses the fixture's bounded snapshot reader. Even a complete snapshot
    is not proof that descendants finished or that a selected runtime is valid.
    """
    value, raw = _snapshot(stages, limit=MAX_SAMPLE_BYTES)
    value['batch_entered'] = None
    value['last_phase'] = None
    if raw is not None:
        try:
            lines = raw.decode('utf-8').splitlines()
        except UnicodeError as error:
            value['decode_error'] = f'{type(error).__name__}: {error}'
        else:
            value['lines'] = lines
            if (
                raw.endswith(b'\n') and lines
                and all(line in _BATCH_WRAPPER_PHASES for line in lines)
            ):
                value['last_phase'] = lines[-1]
                if lines[0] == 'batch_entered':
                    value['batch_entered'] = True
    return value


def _wrapper_selection_satisfied(selection: dict, runtime: object) -> bool | None:
    """Check only the explicitly configured fixture selection.

    Args:
        selection: Intended fixture lane and its explicit selection constraints.
        runtime: Actual final runtime marker, never inferred from parent exit.

    Returns:
        None for system discovery, or whether the requested selection occurred.
    """
    if selection['lane'] == 'system-discovery':
        return None
    if not isinstance(runtime, dict):
        return False
    version = runtime.get('version_info')
    if not (
        isinstance(version, list)
        and len(version) == 3
        and all(type(part) is int for part in version)
        and version[:2] == selection['expected_version']
        and isinstance(runtime.get('executable'), str)
    ):
        return False
    expected = selection.get('expected_executable')
    return expected is None or Path(runtime['executable']).resolve() == Path(
        expected
    ).resolve()


def _exercise_wrapper_fixture(
    tmp_path: Path, wrapper: str, arguments: list[str],
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, *,
    lane: str = 'system-discovery',
) -> None:
    """Exercise one unchanged native wrapper with honest runtime diagnostics.

    Args:
        tmp_path: Fresh private fixture directory belonging to this test.
        wrapper: Exact source wrapper copied without instrumentation or edits.
        arguments: Original arguments whose forwarding the test checks.
        request: Pytest request retaining diagnostics even when assertions fail.
        monkeypatch: Scoped environment changes undone after the test.
        lane: System discovery, an explicit PATH runtime or a real local venv.
    """
    windows = wrapper.endswith('.bat')
    directory = tmp_path / 'source folder with spaces'
    directory.mkdir()
    launcher = directory / wrapper
    shutil.copyfile(Path(__file__).parents[1] / wrapper, launcher)
    marker, stages = tmp_path / 'wrapper-marker.json', tmp_path / 'wrapper-stages.bin'
    batch_stages = tmp_path / 'wrapper-batch-stages.bin'
    selection = {
        'lane': lane,
        'fixture_interpreter': sys.executable,
        'fixture_version': list(sys.version_info[:3]),
        'expected_version': (
            list(sys.version_info[:2]) if lane != 'system-discovery' else None
        ),
        'expected_executable': None,
        'py_candidate': shutil.which('py') if windows else None,
        'python_candidate': shutil.which('python'),
        'local_venv_present': False,
        'launcher_debug_requested': windows,
        'launcher_family': 'unknown' if windows else 'not-applicable',
        'requested_launcher_environment': {},
        'launcher_policy_effective': None,
    }
    if windows:
        monkeypatch.setenv('SINTER_FIXTURE_BATCH_STAGES', str(batch_stages))
        # Launcher families have different controls. Request both debug channels
        # and request no automatic runtime installs before any fixture launch.
        # Administrative manager overrides may supersede environment settings;
        # the requested policy is not proof of effective policy or family.
        policy = {
            'PYLAUNCHER_DEBUG': '1',
            'PYLAUNCHER_ALLOW_INSTALL': None,
            'PYLAUNCHER_ALWAYS_INSTALL': None,
            'PYMANAGER_DEBUG': '1',
            'PYTHON_MANAGER_AUTOMATIC_INSTALL': 'false',
        }
        for key, value in policy.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        selection['requested_launcher_environment'] = {
            key: os.environ.get(key) for key in policy
        }
        selection['launcher_policy_boundary'] = (
            'Administrator configuration may override requested environment.'
        )
    if lane == 'configured-local-venv':
        venv.EnvBuilder(with_pip=False, symlinks=False).create(directory / '.venv')
        executable = directory / '.venv' / (
            'Scripts/python.exe' if windows else 'bin/python'
        )
        assert executable.is_file(), 'The actual fixture venv executable is missing.'
        selection.update(local_venv_present=True, expected_executable=str(executable))
    elif lane == 'configured-path':
        assert windows, 'The PATH selection lane exercises the Windows wrapper.'
        assert selection['py_candidate'], 'CI must retain an available py fallback.'
        monkeypatch.setenv(
            'PATH', str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH']
        )
        selection['expected_executable'] = sys.executable
        selection['python_candidate'] = shutil.which('python')
    else:
        assert lane == 'system-discovery', 'Unknown wrapper fixture lane.'
    selection['legacy_minor_selector'] = (
        os.environ.get('PY_PYTHON3') if windows else None
    )
    (directory / 'start.py').write_text(
        _wrapper_entry_source(marker, stages), encoding='utf-8', newline='\n',
    )
    if windows:
        # cmd /s removes one outer quote pair. Keep the quoted batch path and
        # spaced arguments inside it, rather than applying argv escaping to cmd.
        shell = subprocess.list2cmdline([os.environ['COMSPEC']])
        invocation = subprocess.list2cmdline([str(launcher), *arguments])
        command = f'{shell} /d /s /c "{invocation}"'
    else:
        command = ['sh', str(launcher), *arguments]
    observation, stdout = observe_wrapper(
        command, tmp_path, marker, timeout=5,
        phase_paths=({'batch': batch_stages, 'python': stages}
                     if windows else {'python': stages}),
    )
    observation['startup_stages'] = _wrapper_stage_observation(stages)
    if windows:
        observation['batch_stages'] = _wrapper_batch_stage_observation(batch_stages)
    runtime = observation['marker'].get('value', {})
    selection['satisfied'] = _wrapper_selection_satisfied(selection, runtime)
    observation['interpreter_selection'] = selection
    diagnostics = json.dumps(observation, sort_keys=True, separators=(',', ':'))
    request.node.user_properties.append(('sinter_wrapper_diagnostics', diagnostics))
    assert not observation['timed_out'], diagnostics
    assert observation['parent_exited'], diagnostics
    assert observation['cleanup_errors'] == [], diagnostics
    assert observation['returncode'] == 0, diagnostics
    assert stdout is not None, diagnostics
    assert observation['stderr'].get('metadata_stable_snapshot'), diagnostics
    assert 'value' in observation['marker'], diagnostics
    assert observation['startup_stages']['python_entered'] is True, diagnostics
    assert 'marker_written' in observation['startup_stages'].get(
        'lines', []
    ), diagnostics
    if lane != 'system-discovery':
        assert selection['satisfied'] is True, diagnostics
    recorded = json.loads(stdout)
    assert recorded['arguments'] == arguments
    assert Path(recorded['cwd']) == directory
    assert runtime['argv'][1:] == arguments, diagnostics
    assert Path(runtime['cwd']) == directory, diagnostics


@pytest.mark.parametrize(
    'wrapper', ['start-sinter.sh', 'Start-Sinter.command', 'Start-Sinter.bat'],
)
@pytest.mark.parametrize('arguments', [
    [], ['--help'], ['--version'], ['serve', '--no-browser', '--port', '9000'],
    ['review', 'notes with spaces.txt', '--offline'],
])
def test_platform_wrappers_preserve_arguments_from_another_directory(
    tmp_path, wrapper, arguments, request, monkeypatch,
):
    windows = wrapper.endswith('.bat')
    if windows != (os.name == 'nt'):
        pytest.skip('Execute each wrapper on its native CI platform.')
    _exercise_wrapper_fixture(tmp_path, wrapper, arguments, request, monkeypatch)


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows wrapper selection lanes.')
@pytest.mark.parametrize('arguments', [
    [], ['--help'], ['--version'], ['serve', '--no-browser', '--port', '9000'],
    ['review', 'notes with spaces.txt', '--offline'],
])
def test_windows_wrapper_configured_interpreter_lanes(
    tmp_path, arguments, request, monkeypatch,
):
    _exercise_wrapper_fixture(
        tmp_path, 'Start-Sinter.bat', arguments, request, monkeypatch,
        lane='configured-local-venv',
    )


@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows PATH runtime selection.')
@pytest.mark.parametrize('arguments', [
    [], ['--help'], ['--version'],
    ['review', 'notes Ω & (draft)! 100% ready.txt', '--offline'],
])
def test_windows_wrapper_prefers_the_working_matrix_runtime_on_path(
    tmp_path, arguments, request, monkeypatch,
):
    _exercise_wrapper_fixture(
        tmp_path, 'Start-Sinter.bat', arguments, request, monkeypatch,
        lane='configured-path',
    )


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
