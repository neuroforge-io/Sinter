"""Native review refusal must not invent a remote attempt or damage recovery."""

import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import cli, client, review

SOURCE = "The fictional committee approved a quote. Spending is not approved.\n"


def settings(model=client.NATIVE_MODEL, api_url=client.BASE_URL):
    return {
        "provider": "openai-compatible",
        "api_url": api_url,
        "model": model,
        "max_tokens": 128,
    }


def payload():
    return {
        "title": "Fictional committee notes",
        "documents": [{"title": "notes.txt", "content": SOURCE}],
    }


def historical_checkpoint(source, status):
    saved = review.run(source, offline=True)
    chunk = review.plan(source)[2][0]
    saved["batches"] = [
        {
            "id": chunk["id"],
            "status": status,
            "follow_ups": 1,
            "prior_content": "Earlier fictional commentary",
            "error": "Earlier outcome",
        }
    ]
    if status == "failed":
        saved.pop("recovery_version")  # Legacy failures remain historically ambiguous.
    return saved


@pytest.mark.parametrize("model", [client.NATIVE_MODEL, client.AUTO_MODEL])
@pytest.mark.parametrize(
    "status", [None, "running", "failed", "uncertain_remote_outcome"]
)
def test_review_refusal_precedes_discovery_planning_checkpoint_and_attempts(
    model, status
):
    source = payload()
    original_source = copy.deepcopy(source)
    with client.connection_settings(settings(model)):
        saved = historical_checkpoint(source, status) if status else None
        original_checkpoint = copy.deepcopy(saved)
        with (
            patch.object(client, "list_models") as discover,
            patch.object(
                client, "_open", side_effect=AssertionError("network forbidden")
            ) as network,
            patch.object(client, "chat") as generate,
            patch.object(review, "_refine_with_model") as refine,
            patch.object(review, "plan") as plan,
        ):
            writes = []
            refusal = (
                "explicit model identifier"
                if model == client.AUTO_MODEL
                else "native ERAIS.*full collection review"
            )
            with pytest.raises(ValueError, match=refusal) as error:
                review.run(
                    source,
                    resume=saved,
                    retry_uncertain=bool(saved),
                    on_checkpoint=writes.append,
                )
        assert "No generation request was sent and no checkpoint was changed" in str(
            error.value
        )
        discover.assert_not_called()
        network.assert_not_called()
        generate.assert_not_called()
        refine.assert_not_called()
        plan.assert_not_called()
        assert writes == []
        assert saved == original_checkpoint
        assert source == original_source


@pytest.mark.parametrize("model", [client.NATIVE_MODEL, client.AUTO_MODEL])
def test_native_offline_plan_remains_exact_and_never_discovers_or_generates(model):
    source = payload()
    original = copy.deepcopy(source)
    with (
        client.connection_settings(settings(model)),
        patch.object(client, "list_models") as discover,
        patch.object(
            client, "_open", side_effect=AssertionError("network forbidden")
        ) as network,
        patch.object(client, "chat") as generate,
    ):
        writes = []
        result = review.run(source, offline=True, on_checkpoint=writes.append)
        chunks = review.plan(source)[2]
    discover.assert_not_called()
    network.assert_not_called()
    generate.assert_not_called()
    assert writes == []
    assert result["coverage"]["requests_this_run"] == 0
    assert result["coverage"]["batches_not_attempted"] == 1
    assert "Status: not reviewed" in result["markdown"]
    assert "No model review completed." in result["markdown"]
    assert "".join(chunk["text"] for chunk in chunks) == SOURCE
    assert source == original


@pytest.mark.parametrize("model", [client.NATIVE_MODEL, client.AUTO_MODEL])
@pytest.mark.parametrize("resuming", [False, True])
def test_cli_native_refusal_preserves_source_report_and_checkpoint(
    tmp_path, model, resuming, capsys
):
    source = tmp_path / "notes.txt"
    source.write_text(SOURCE, encoding="utf-8")
    output = tmp_path / "review.md"
    output.write_text("Earlier report must survive.\n", encoding="utf-8")
    receipt = Path(str(output) + ".checkpoint.json")
    original_source = source.read_bytes()
    original_report = output.read_bytes()
    with client.connection_settings(settings(model)):
        if resuming:
            book, _ = review.load_collection(source)
            review.atomic_save(receipt, historical_checkpoint(book, "running"))
        original_receipt = receipt.read_bytes() if receipt.exists() else None
        with (
            patch.object(client, "list_models") as discover,
            patch.object(
                client, "_open", side_effect=AssertionError("network forbidden")
            ) as network,
            patch.object(client, "chat") as generate,
        ):
            arguments = ["review", str(source), "-o", str(output)]
            if resuming:
                arguments.extend(["--resume", "--retry-uncertain"])
            with pytest.raises(SystemExit) as error:
                cli.main(arguments)
    assert error.value.code == 1
    assert "no checkpoint was changed" in capsys.readouterr().err
    discover.assert_not_called()
    network.assert_not_called()
    generate.assert_not_called()
    assert source.read_bytes() == original_source
    assert output.read_bytes() == original_report
    assert (receipt.read_bytes() if receipt.exists() else None) == original_receipt


def test_custom_provider_reusing_native_name_does_not_inherit_native_refusal():
    with (
        client.connection_settings(settings(api_url="https://models.example/v1")),
        patch.object(client, "list_models") as discover,
        patch.object(
            client, "_open", side_effect=AssertionError("network forbidden")
        ) as network,
        patch.object(
            client,
            "chat",
            return_value=client.ChatResult(
                "No issues found after checking the supplied committee "
                "and spending decisions."
            ),
        ) as generate,
    ):
        result = review.run(payload())
    discover.assert_not_called()
    network.assert_not_called()
    assert generate.call_count == 1
    assert result["coverage"]["batches_complete"] == 1
    assert result["coverage"]["requests_this_run"] == 1


def test_auto_review_requires_explicit_recovery_identity_without_discovery():
    with (
        client.connection_settings(settings(client.AUTO_MODEL)),
        patch.object(client, "list_models") as discover,
        patch.object(
            client, "_open", side_effect=AssertionError("network forbidden")
        ) as network,
        patch.object(client, "chat") as generate,
    ):
        writes = []
        with pytest.raises(ValueError, match="explicit model identifier"):
            review.run(payload(), on_checkpoint=writes.append)
    discover.assert_not_called()
    network.assert_not_called()
    generate.assert_not_called()
    assert writes == []


def test_cli_runtime_flag_validation_and_missing_argument_have_distinct_exit_codes(
    tmp_path,
):
    source = tmp_path / "notes.txt"
    source.write_text(SOURCE, encoding="utf-8")
    with pytest.raises(SystemExit) as runtime:
        cli.main(["review", str(source), "--retry-uncertain", "--offline"])
    with pytest.raises(SystemExit) as syntax:
        cli.main(["review"])
    assert runtime.value.code == 1
    assert syntax.value.code == 2
