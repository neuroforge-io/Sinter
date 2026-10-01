"""Data-only contract for one fictional Linux x64 installed UI qualification."""

import ast
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
NAVIGATION_SCHEMA = "sinter-installed-workflow/v3"
LEGACY_PRESENTATION = "sinter-handover-presentation/v1"
RECIPIENT_PRESENTATION = "sinter-handover-presentation/v2"
NAVIGATION_CHECK = "handover_recipient_guidance_and_internal_navigation"
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


def _symbol_nodes(tree: ast.AST, symbol: str) -> list[ast.AST]:
    """Find reserved identifier references/bindings, including nested declarations."""
    return [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Name)
            and node.id == symbol
            or isinstance(node, ast.arg)
            and node.arg == symbol
            or isinstance(node, ast.alias)
            and (node.asname or node.name.split(".")[0]) == symbol
            or getattr(node, "name", None) == symbol
            or isinstance(node, (ast.Global, ast.Nonlocal))
            and symbol in node.names
            or isinstance(node, ast.MatchMapping)
            and node.rest == symbol
        )
    ]


def source_presentation(source: dict[str, bytes]) -> str:
    """Read a closed literal identity; never execute or guess candidate code."""
    try:
        handover = ast.parse(source.get("src/sinter/handover.py", b""))
        exporter = ast.parse(source.get("src/sinter/docx_export.py", b""))
        identity_nodes = _symbol_nodes(handover, "PRESENTATION_VERSION")
        navigation_nodes = _symbol_nodes(exporter, "_passage_navigation")
        markers = [
            node
            for node in handover.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PRESENTATION_VERSION"
        ]
        navigation = [
            node
            for node in exporter.body
            if isinstance(node, ast.FunctionDef) and node.name == "_passage_navigation"
        ]
        navigation_bindings = [
            node
            for node in navigation_nodes
            if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load))
        ]
        if not identity_nodes and not navigation_nodes:
            return LEGACY_PRESENTATION
        if (
            len(markers) != 1
            or identity_nodes != [markers[0].targets[0]]
            or len(navigation) != 1
            or navigation_bindings != navigation
            or ast.literal_eval(markers[0].value) != RECIPIENT_PRESENTATION
        ):
            raise ValueError("Unknown or incomplete handover presentation identity.")
    except (SyntaxError, TypeError, ValueError) as error:
        raise ValueError(
            "Installed qualification needs a closed handover presentation identity."
        ) from error
    return RECIPIENT_PRESENTATION


def workflow_schema(source: dict[str, bytes]) -> str:
    if source_presentation(source) == RECIPIENT_PRESENTATION:
        if not requires_word_copy(source):
            raise ValueError(
                "Recipient handover qualification requires Word-copy support."
            )
        return NAVIGATION_SCHEMA
    return LATEST_SCHEMA if requires_word_copy(source) else SCHEMA


def workflow_artifact_paths(source: dict[str, bytes]):
    return (
        LATEST_ARTIFACT_PATHS if workflow_schema(source) != SCHEMA else ARTIFACT_PATHS
    )


def workflow_checks(source: dict[str, bytes]) -> tuple[str, ...]:
    if workflow_schema(source) == NAVIGATION_SCHEMA:
        return (*CHECKS[:-1], *WORD_CHECKS, NAVIGATION_CHECK, CHECKS[-1])
    return (
        (*CHECKS[:-1], *WORD_CHECKS, CHECKS[-1])
        if requires_word_copy(source)
        else CHECKS
    )
