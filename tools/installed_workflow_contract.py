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
