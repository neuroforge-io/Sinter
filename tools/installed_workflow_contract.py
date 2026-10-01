"""Data-only contract for one fictional Linux x64 installed UI qualification."""

from types import MappingProxyType

SCHEMA = "sinter-installed-workflow/v1"
ARTIFACT_PATHS = MappingProxyType(
    {
        "overview": "installed-workflow/01-overview.png",
        "prepared_handover": "installed-workflow/02-prepared-handover.png",
        "campaign_action": "installed-workflow/03-campaign-action.png",
        "reopened_handover": "installed-workflow/04-reopened-handover.png",
        "restored_workspace": "installed-workflow/05-restored-workspace.png",
        "handover_word": "installed-workflow/handover.docx",
        "casebook_backup": "installed-workflow/casebook-backup.json",
        "campaign_backup": "installed-workflow/campaign-backup.json",
    }
)
CHECKS = (
    "installed_package_identity",
    "frozen_desktop_identity",
    "overview_practice_discovery",
    "handover_exact_originals",
    "handover_prepare_edit_save",
    "campaign_action_and_draft_save",
    "interface_quit_and_process_exit",
    "actual_binary_restart",
    "saved_report_and_campaign_reopened",
    "word_download_verified",
    "project_and_campaign_backup_downloaded",
    "backup_restore_as_separate_copies",
    "original_inputs_and_correspondence_preserved",
    "interface_quit_after_restart",
    "package_removed_and_container_closed",
)
RESOURCE_FLAGS = (
    "browser_closed",
    "relay_closed",
    "installed_process_stopped",
    "container_removed",
    "package_removed",
)
RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "passed",
        "version",
        "source_commit",
        "system",
        "target_arch",
        "machine",
        "pointer_bits",
        "frozen",
        "desktop",
        "installed_executable",
        "installer_sha256",
        "source_archive_sha256",
        "native_receipt_sha256",
        "installed_binary_sha256",
        "web_assets_sha256",
        "practice_fixture_sha256",
        "image_id",
        "container",
        "network",
        "network_mode",
        "host_installation",
        "os_release",
        "libc",
        "external_requests",
        "page_errors",
        "model_calls",
        "resources",
        "checks",
        "artifacts",
        "input_hashes",
        "result_hashes",
    }
)
PRACTICE_FILES = (
    "src/sinter/web/offline-garden-casebook.json",
    "src/sinter/web/offline-garden-campaign.json",
)
RECIPIENT = "Fictional incoming team"
RESTORED_CASEBOOK_TITLE = "Restored fictional installed handover"
RESTORED_CAMPAIGN_TITLE = "Restored fictional installed campaign"
OPERATOR_NOTE = (
    "\n\n## Fictional operator note\n\n"
    "Fictional practice only: equipment quote remains pending. "
    "No order or enquiry has been sent."
)
ACTION_TASK = "Fictional operator: recheck current guidelines before proceeding."
COMMUNICATION = MappingProxyType(
    {
        "date": "2026-09-30",
        "direction": "outgoing",
        "status": "draft",
        "channel": "email",
        "counterparty": "Fictional garden contact (not sent)",
        "subject": "Fictional garden clarification - not sent",
        "content": (
            "Fictional practice draft only. Please clarify applicant conditions and "
            "the current application window. This draft has not been sent."
        ),
    }
)
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024

# Historical v1 remains unchanged. These roles are mandatory only when the
# pinned source introduces the explicit local Word-copy operation.
LATEST_SCHEMA = "sinter-installed-workflow/v2"
WORD_CHANGED_NOTE = (
    "\n\n## Fictional Word-only clarification\n\n"
    "No grant was awarded; no owner or proposed date has been confirmed. 🐝"
)
WORD_CHECKS = (
    "installed_catalog_exact_53_with_word_copy_write",
    "ordinary_json_word_copy_actual_bytes",
    "pending_word_edits_refused_without_request",
    "changed_wording_distinct_prior_copy_retained",
    "lost_word_confirmation_prior_path_no_replay",
    "word_copy_original_records_preferences_retained",
)
LATEST_ARTIFACT_PATHS = MappingProxyType(
    {
        **ARTIFACT_PATHS,
        "operations_catalog": "installed-workflow/operations-catalog.json",
        "word_copy_recovery": "installed-workflow/word-copy-recovery.json",
        "word_copy_applied": "installed-workflow/word-copy-applied.docx",
        "word_copy_changed": "installed-workflow/word-copy-changed.docx",
        "word_copy_unconfirmed": "installed-workflow/word-copy-unconfirmed.docx",
    }
)


def requires_word_copy(source: dict[str, bytes]) -> bool:
    """A missing/changed catalogue cannot downgrade a new module to v1."""
    return (
        "src/sinter/document_copies.py" in source
        or b"documents.docx.save" in source.get("src/sinter/runtime.py", b"")
    )


def workflow_schema(source: dict[str, bytes]) -> str:
    return LATEST_SCHEMA if requires_word_copy(source) else SCHEMA


def workflow_artifact_paths(source: dict[str, bytes]):
    return LATEST_ARTIFACT_PATHS if requires_word_copy(source) else ARTIFACT_PATHS


def workflow_checks(source: dict[str, bytes]) -> tuple[str, ...]:
    return (
        (*CHECKS[:-1], *WORD_CHECKS, CHECKS[-1])
        if requires_word_copy(source)
        else CHECKS
    )
