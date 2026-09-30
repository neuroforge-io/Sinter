"""Fictional Atlas source import, download and update browser regressions.

Uses recorded fictional context and a constructed Markdown bundle through the
real local Sinter server. Model, search and credential calls fail and are counted;
Python sockets and browser requests are restricted to this local app.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import socket
import sys
import tempfile
import threading
from contextlib import ExitStack
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

SOURCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = SOURCE_ROOT
# An imported-tool ROOT override changes artifact output, never fixture inputs.
FIXTURES = SOURCE_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT / "src"))

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.deliverable_browser import DeliverableChecks  # noqa: E402


class ForbiddenCalls:
    """Count blocked attempts without reading keys, bodies or private files."""

    def __init__(self):
        self.attempts = []

    def reject(self, category, method):
        def blocked(*args, **kwargs):
            self.attempts.append({"category": category, "method": method})
            raise AssertionError(f"Unexpected {category} call: {method}")

        return blocked

    def install(self, stack):
        for name in (
            "chat",
            "chat_stream",
            "chat_stream_result",
            "list_models",
            "_get",
            "_post",
            "_post_raw",
            "_open",
            "_request_json",
        ):
            stack.enter_context(patch.object(client, name, self.reject("model", name)))
        stack.enter_context(
            patch.object(client, "search", self.reject("search", "search"))
        )
        for name in ("_load_key", "destination_key", "_headers"):
            stack.enter_context(
                patch.object(client, name, self.reject("credential", name))
            )

    def count(self, category):
        return sum(row["category"] == category for row in self.attempts)


class LoopbackOnly:
    """Prevent Python network/DNS access beyond the disposable local app."""

    def __init__(self, *ports):
        self.ports = set(ports)
        self.allowed = []
        self.blocked = []

    def install(self, stack):
        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        original_sendto = socket.socket.sendto
        original_getaddrinfo = socket.getaddrinfo

        def admit(sock, address, method):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                host, port = address[:2]
                entry = {"host": str(host), "port": port, "method": method}
                if host not in {"127.0.0.1", "::1"} or port not in self.ports:
                    self.blocked.append(entry)
                    raise AssertionError(
                        "Only the disposable loopback app and fixture are allowed"
                    )
                self.allowed.append(entry)

        def connect(sock, address):
            admit(sock, address, "connect")
            return original_connect(sock, address)

        def connect_ex(sock, address):
            admit(sock, address, "connect_ex")
            return original_connect_ex(sock, address)

        def sendto(sock, *args):
            admit(sock, args[-1], "sendto")
            return original_sendto(sock, *args)

        def getaddrinfo(host, port, *args, **kwargs):
            if host not in {"127.0.0.1", "::1", None}:
                self.blocked.append(
                    {"host": str(host), "port": port, "method": "getaddrinfo"}
                )
                raise AssertionError("Non-loopback name resolution is blocked")
            return original_getaddrinfo(host, port, *args, **kwargs)

        stack.enter_context(patch.object(socket.socket, "connect", connect))
        stack.enter_context(patch.object(socket.socket, "connect_ex", connect_ex))
        stack.enter_context(patch.object(socket.socket, "sendto", sendto))
        stack.enter_context(patch.object(socket, "getaddrinfo", getaddrinfo))
        if hasattr(socket.socket, "sendmsg"):
            original_sendmsg = socket.socket.sendmsg

            def sendmsg(sock, buffers, ancdata=(), flags=0, address=None):
                if address is not None:
                    admit(sock, address, "sendmsg")
                    return original_sendmsg(sock, buffers, ancdata, flags, address)
                return original_sendmsg(sock, buffers, ancdata, flags)

            stack.enter_context(patch.object(socket.socket, "sendmsg", sendmsg))


class FictionalRKC:
    """Tiny recorded REST fixture; no executable, source paths or real RKC data."""

    question = "Lantern lending period"

    def __init__(self, packets):
        self.packet = copy.deepcopy(packets["before"])
        self.header_mismatch = False
        self.requests = []
        self.unexpected = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def parse_request(self):
                if not super().parse_request():
                    return False
                attempt = {"method": self.command, "path": self.path}
                owner.requests.append(attempt)
                if self.command != "GET":
                    owner.unexpected.append(attempt)
                    self.send_error(400, "Only fictional context GET is allowed")
                    return False
                return True

            def respond(self):
                attempt = {"method": self.command, "path": self.path}
                target = urlsplit(self.path)
                expected = {
                    "q": [owner.question],
                    "limit": ["12"],
                    "max_bytes": ["32768"],
                    "format": ["json"],
                }
                if (
                    self.command != "GET"
                    or target.path != "/api/v1/context"
                    or parse_qs(target.query, keep_blank_values=True) != expected
                    or any(
                        name in self.headers
                        for name in (
                            "Authorization",
                            "Proxy-Authorization",
                            "Cookie",
                        )
                    )
                ):
                    owner.unexpected.append(attempt)
                    self.send_error(400, "Unexpected fictional context request")
                    return
                packet = copy.deepcopy(owner.packet)
                raw = json.dumps(packet, ensure_ascii=False).encode("utf-8")
                snapshot = (
                    "fictional-mismatched-header"
                    if owner.header_mismatch
                    else packet["snapshot_id"]
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("X-RKC-Snapshot-ID", snapshot)
                self.end_headers()
                self.wfile.write(raw)

            do_GET = respond

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self):
        return self.server.server_port

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class AtlasSourceChecks(DeliverableChecks):
    def __init__(
        self, browser, server, artifacts, packets, bundle, fixture, source_bound_packets
    ):
        super().__init__(browser, f"http://127.0.0.1:{server.server_port}", artifacts)
        self.server, self.fixture = server, fixture
        self.packets = packets
        self.source_bound_packets = source_bound_packets
        self.bundle = bundle
        self.downloads = []
        self.delayed_inspections = []

    def open_atlas(self, page):
        self.goto(page, "atlas")
        return page.get_by_role("region", name="Knowledge results", exact=True)

    def consent(self, page):
        return page.get_by_label(
            "Send selected source excerpts and my question to my configured "
            "model API for an unverified draft.",
            exact=True,
        )

    def upload(self, page, document, name):
        page.get_by_label(
            "Import an RKC atlas or context packet", exact=True
        ).set_input_files(
            {
                "name": name,
                "mimeType": "application/json",
                "buffer": json.dumps(document, ensure_ascii=False).encode("utf-8"),
            }
        )

    def import_document(self, page, document, name):
        from playwright.sync_api import expect

        self.upload(page, document, name)
        snapshot = document.get("snapshot_id") or document["snapshot"]["id"]
        expect(page.get_by_text(f"Snapshot: {snapshot}.", exact=False)).to_be_visible()
        expect(
            page.get_by_role("button", name="Find supporting material", exact=True)
        ).to_be_enabled()

    def find(self, page, question="Lantern lending period"):
        page.get_by_label("What would you like to find out?", exact=True).fill(question)
        page.get_by_role("button", name="Find supporting material", exact=True).click()
        region = page.get_by_role("region", name="Knowledge results", exact=True)
        region.get_by_text(
            "Source packet only. No factual answer has been inferred.", exact=True
        ).wait_for()
        return region

    def retained_download(self, page, label, name):
        filename, raw = self.download(page, label)
        destination = self.artifacts / name
        destination.write_text(raw, encoding="utf-8")
        self.downloads.append(
            {
                "file": destination.name,
                "suggested_filename": filename,
                "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            }
        )
        return raw

    def rich_context_source(self, page):
        from playwright.sync_api import expect

        self.open_atlas(page)
        original = self.packets["before"]
        self.import_document(page, original, "fictional-rich-context.json")
        region = self.find(page)
        expect(region).to_contain_text("Lantern lending period is 14 days.")
        expect(region).to_contain_text(
            "Source object location (producer metadata; not excerpt offsets):"
        )
        expect(region).to_contain_text("handbook.md")
        raw = self.retained_download(page, "Download context JSON", "rich-context.json")
        result = json.loads(raw)
        by_id = {row["object_id"]: row for row in result["items"]}
        for supplied in original["items"]:
            retained = by_id[supplied["object_id"]]
            assert retained["id"] == supplied["citation_id"]
            assert retained["text"] == supplied["text"]
            assert retained["path"] == supplied["path"]
            if "source" in supplied:
                assert retained["source"] == supplied["source"]
            else:
                assert retained.get("source") in (None, {})
        artifact = next(
            row for row in original["items"] if row["object_type"] == "artifact"
        )
        assert set(by_id[artifact["object_id"]]["source"]) == {"artifact_id", "path"}
        assert result["snapshot_id"] == original["snapshot_id"]
        self.screenshot(page, "atlas-rich-context-source")
        for version in ("before", "after", "old_retained"):
            fresh = self.source_bound_packets[version]
            self.import_document(page, fresh, f"fictional-source-bound-{version}.json")
            self.find(page)
            days = 21 if version == "after" else 14
            expect(region).to_contain_text(f"Lantern lending period is {days} days.")
            expect(region).to_contain_text(re.compile(r'"start_line"\s*:\s*1\b'))
            expect(region).to_contain_text(re.compile(r'"end_line"\s*:\s*12\b'))
            result = json.loads(
                self.retained_download(
                    page, "Download context JSON", f"source-bound-{version}.json"
                )
            )
            assert result["snapshot_id"] == fresh["snapshot_id"]
            supplied = {row["object_id"]: row for row in fresh["items"]}
            assert len(result["items"]) == len(supplied)
            assert {row["object_id"] for row in result["items"]} == set(supplied)
            for retained in result["items"]:
                original = supplied[retained["object_id"]]
                assert retained["text"] == original["text"]
                assert retained["id"] == original["citation_id"]
                assert retained["source"] == original["source"]
                assert original["evidence_ids"] == sorted(set(original["evidence_ids"]))
                assert retained["evidence_ids"] == original["evidence_ids"]
                expect(region).to_contain_text(original["citation_id"])
            source_document = next(
                row for row in result["items"] if row["object_type"] == "document"
            )
            assert source_document["source"] == {
                "artifact_id": "rkc:artifact:2be09df08f95165bf021e56d",
                "path": "handbook.md",
                "start_line": 1,
                "end_line": 12,
            }
            assert source_document["evidence_ids"]
            self.screenshot(page, f"atlas-source-bound-{version}")

    def bundle_markdown_body(self, page):
        from playwright.sync_api import expect

        self.open_atlas(page)
        self.import_document(page, self.bundle, "fictional-markdown-bundle.json")
        region = self.find(page, "renewals")
        expect(region).to_contain_text("Lantern renewals are allowed once.")
        expect(region).to_contain_text("Lantern lending period is 14 days.")
        expect(region).to_contain_text(
            "Source object location (producer metadata; not excerpt offsets):"
        )
        expect(region).to_contain_text("lantern-lending-period")
        result = json.loads(
            self.retained_download(page, "Download context JSON", "bundle-context.json")
        )
        document = self.bundle["documents"][0]
        section = document["sections"][0]
        node = next(row for row in self.bundle["nodes"] if row["id"] == section["id"])
        expected_citation = hashlib.sha256(
            (self.bundle["snapshot"]["id"] + "\0node\0" + node["id"]).encode("utf-8")
        ).hexdigest()
        assert len(result["items"]) == 1
        retained = result["items"][0]
        assert retained["id"] == expected_citation
        assert retained["object_id"] == node["id"] and retained["object_type"] == "node"
        assert retained["text"] == section["markdown"]
        assert retained["source"] == node["source"]
        assert retained["pointer"] == "/documents/0/sections/0/markdown"
        assert retained["evidence_ids"] == section["evidence_ids"]
        for key, expected in (
            ("document_id", document["id"]),
            ("section_id", section["id"]),
            ("document_kind", document["kind"]),
            ("generator", document["generator"]),
            ("document_status", document["status"]),
        ):
            assert retained[key] == expected, key
        markdown = self.retained_download(
            page, "Download Markdown", "bundle-context.md"
        )
        assert "Lantern renewals are allowed once." in markdown
        assert expected_citation in markdown
        assert "/documents/0/sections/0/markdown" in markdown
        assert "lantern-lending-period" in markdown
        self.screenshot(page, "atlas-bundle-markdown")

    def explicit_update(self, page):
        from playwright.sync_api import expect

        region = self.open_atlas(page)
        before, after = self.packets["before"], self.packets["after"]
        assert self.packets["old_retained"] == before
        self.import_document(page, before, "fictional-before-context.json")
        self.find(page)
        old_raw = self.retained_download(
            page, "Download context JSON", "update-before.json"
        )
        old = json.loads(old_raw)
        self.consent(page).check()
        self.import_document(page, after, "fictional-after-context.json")
        expect(self.consent(page)).not_to_be_checked()
        expect(
            region.get_by_role("button", name="Download context JSON", exact=True)
        ).to_have_count(0)
        expect(region).not_to_contain_text("Lantern lending period is 14 days.")
        self.find(page)
        expect(region).to_contain_text("Lantern lending period is 21 days.")
        expect(region).not_to_contain_text("Lantern lending period is 14 days.")
        current = json.loads(
            self.retained_download(page, "Download context JSON", "update-after.json")
        )
        assert old["snapshot_id"] == before["snapshot_id"]
        assert current["snapshot_id"] == after["snapshot_id"]
        old_by_id = {row["object_id"]: row for row in old["items"]}
        new_by_id = {row["object_id"]: row for row in current["items"]}
        supplied_after = {row["object_id"]: row for row in after["items"]}
        assert set(old_by_id) == set(new_by_id) == set(supplied_after)
        for object_id, row in old_by_id.items():
            assert "14 days" in row["text"] and "21 days" not in row["text"]
            updated, supplied = new_by_id[object_id], supplied_after[object_id]
            assert updated["text"] == supplied["text"]
            assert updated["id"] == supplied["citation_id"]
            assert updated["path"] == supplied["path"]
            if "source" in supplied:
                assert updated["source"] == supplied["source"]
            else:
                assert updated.get("source") in (None, {})
            assert row["id"] != updated["id"]
        assert (self.artifacts / "update-before.json").read_text(
            encoding="utf-8"
        ) == old_raw
        self.screenshot(page, "atlas-explicit-update")

    def question_edit_consent(self, page):
        from playwright.sync_api import expect

        region = self.open_atlas(page)
        self.import_document(
            page, self.packets["before"], "fictional-question-context.json"
        )
        self.find(page)
        self.consent(page).check()
        page.get_by_label("What would you like to find out?", exact=True).fill(
            "Lantern opening hours"
        )
        expect(self.consent(page)).not_to_be_checked()
        page.get_by_role("button", name="Draft with your model", exact=True).click()
        expect(region).to_contain_text("approve the excerpt transfer")
        self.screenshot(page, "atlas-question-consent")

    def reject_corrupt_identity(self, page):
        from playwright.sync_api import expect

        region = self.open_atlas(page)
        original = self.packets["before"]
        self.import_document(page, original, "fictional-good-context.json")
        self.find(page)
        corrupt = copy.deepcopy(original)
        corrupt["items"][0]["citation_id"] = "0" * 64
        swapped = copy.deepcopy(original)
        swapped["snapshot_id"] = self.packets["after"]["snapshot_id"]
        for name, invalid in (
            ("fictional-corrupt-citation.json", corrupt),
            ("fictional-swapped-snapshot.json", swapped),
        ):
            self.upload(page, invalid, name)
            expect(region).to_contain_text(
                "A context citation does not match its snapshot and object identity."
            )
            expect(
                page.get_by_text(f"Snapshot: {original['snapshot_id']}.", exact=False)
            ).to_be_visible()
            expect(
                page.get_by_role("button", name="Find supporting material", exact=True)
            ).to_be_enabled()
        self.find(page)
        expect(region).to_contain_text("Lantern lending period is 14 days.")
        result = json.loads(
            self.retained_download(
                page, "Download context JSON", "corruption-retained-good.json"
            )
        )
        assert result["snapshot_id"] == original["snapshot_id"]
        assert {row["id"] for row in result["items"]} == {
            row["citation_id"] for row in original["items"]
        }
        self.screenshot(page, "atlas-corrupt-identity-refusal")

    def recorded_loopback_transport(self, page):
        from playwright.sync_api import expect

        region = self.open_atlas(page)
        self.server.app.preferences.update({"rkc_port": self.fixture.port})
        before, after = self.packets["before"], self.packets["after"]
        count = len(self.fixture.requests)
        self.fixture.packet = copy.deepcopy(before)
        self.fixture.header_mismatch = False
        page.get_by_label("What would you like to find out?", exact=True).fill(
            self.fixture.question
        )
        local = page.get_by_role(
            "button", name="Read context from local RKC", exact=True
        )
        local.click()
        expect(
            page.get_by_text(f"Snapshot: {before['snapshot_id']}.", exact=False)
        ).to_be_visible()
        expect(region).to_contain_text("Lantern lending period is 14 days.")
        old_raw = self.retained_download(
            page, "Download context JSON", "loopback-before.json"
        )
        old = json.loads(old_raw)
        assert old["snapshot_id"] == before["snapshot_id"]
        self.consent(page).check()

        self.fixture.packet = copy.deepcopy(after)
        local.click()
        expect(
            page.get_by_text(f"Snapshot: {after['snapshot_id']}.", exact=False)
        ).to_be_visible()
        expect(self.consent(page)).not_to_be_checked()
        expect(region).to_contain_text("Lantern lending period is 21 days.")
        expect(region).not_to_contain_text("Lantern lending period is 14 days.")
        current = json.loads(
            self.retained_download(page, "Download context JSON", "loopback-after.json")
        )
        assert current["snapshot_id"] == after["snapshot_id"]
        assert {row["id"] for row in current["items"]} == {
            row["citation_id"] for row in after["items"]
        }

        self.fixture.header_mismatch = True
        local.click()
        expect(region).to_contain_text("Cannot read the local RKC context.")
        expect(
            page.get_by_text(f"Snapshot: {after['snapshot_id']}.", exact=False)
        ).to_be_visible()
        expect(
            page.get_by_role("button", name="Find supporting material", exact=True)
        ).to_be_enabled()
        self.find(page)
        expect(region).to_contain_text("Lantern lending period is 21 days.")
        expect(region).not_to_contain_text("Lantern lending period is 14 days.")
        retained = json.loads(
            self.retained_download(
                page, "Download context JSON", "loopback-mismatch-retained-good.json"
            )
        )
        assert retained["snapshot_id"] == after["snapshot_id"]
        supplied = {row["object_id"]: row for row in after["items"]}
        assert len(retained["items"]) == len(supplied)
        assert {row["object_id"] for row in retained["items"]} == set(supplied)
        for row in retained["items"]:
            original = supplied[row["object_id"]]
            assert row["text"] == original["text"]
            assert row["id"] == original["citation_id"]
            if "source" in original:
                assert row["source"] == original["source"]
        assert (self.artifacts / "loopback-before.json").read_text(
            encoding="utf-8"
        ) == old_raw
        assert len(self.fixture.requests) == count + 3
        assert not self.fixture.unexpected
        self.fixture.header_mismatch = False
        self.screenshot(page, "atlas-loopback-header-update")

    def reject_omitted_artifact_provenance(self, page):
        from playwright.sync_api import expect

        region = self.open_atlas(page)
        original = self.source_bound_packets["after"]
        self.import_document(page, original, "fictional-current-provenance.json")
        self.find(page)
        good_raw = self.retained_download(
            page, "Download context JSON", "provenance-current.json"
        )
        attack = copy.deepcopy(self.bundle)
        node, document = attack["nodes"][0], attack["documents"][0]
        node["source"].pop("artifact_id")
        document["attributes"].pop("artifact_id")
        node["source"]["path"] = document["path"] = "fictional-other-book.md"
        assert node["artifact_id"] == attack["artifacts"][0]["id"]
        assert attack["artifacts"][0]["path"] == "handbook.md"
        self.consent(page).check()
        self.upload(page, attack, "fictional-omitted-artifact-provenance.json")
        expect(region).to_contain_text(
            "The RKC source path disagrees with its object path."
        )
        expect(self.consent(page)).not_to_be_checked()
        expect(
            page.get_by_text(f"Snapshot: {original['snapshot_id']}.", exact=False)
        ).to_be_visible()
        expect(
            page.get_by_role("button", name="Find supporting material", exact=True)
        ).to_be_enabled()
        self.find(page)
        expect(region).to_contain_text("Lantern lending period is 21 days.")
        expect(region).not_to_contain_text("fictional-other-book.md")
        retained = self.retained_download(
            page, "Download context JSON", "provenance-retained-good.json"
        )
        current, kept = json.loads(good_raw), json.loads(retained)
        # A new local search stamps a new context creation time; source content,
        # snapshot, references and all other metadata must remain identical.
        current_time = datetime.fromisoformat(current.pop("created_at"))
        kept_time = datetime.fromisoformat(kept.pop("created_at"))
        assert current_time.tzinfo is not None and kept_time.tzinfo is not None
        assert kept_time >= current_time
        assert kept == current
        self.screenshot(page, "atlas-omitted-artifact-provenance-refusal")

    def delayed_remembered_packet(self, page, *, failed, disposed=False):
        """Delay a real inspection response while a newer import is accepted."""
        from playwright.sync_api import expect

        outcome = ("disposed-" if disposed else "") + (
            "failure" if failed else "success"
        )
        before, after = (
            self.source_bound_packets["before"],
            self.source_bound_packets["after"],
        )
        region = self.open_atlas(page)
        self.import_document(page, before, f"fictional-remembered-{outcome}.json")
        self.find(page)
        old_raw = self.retained_download(
            page, "Download context JSON", f"delayed-{outcome}-old.json"
        )
        assert json.loads(old_raw)["snapshot_id"] == before["snapshot_id"]
        held = {}
        pattern = "**/api/atlas/inspect"

        def hold_inspection(route):
            packet = route.request.post_data_json["document"]
            if not held and packet.get("snapshot_id") == before["snapshot_id"]:
                # The actual Sinter server validates the fictional packet first.
                # Only delivery of that response is postponed, or fault-injected.
                held.update(route=route, response=route.fetch())
            else:
                route.continue_()

        page.route(pattern, hold_inspection)
        page.evaluate(
            """snapshot => {
                const original = window.fetch;
                window.__atlasDelayedInspectionDone = false;
                window.__atlasDelayedInspectionStarted = false;
                window.fetch = async (url, options) => {
                    const body = options?.body ? JSON.parse(options.body) : null;
                    const tracked = url === '/api/atlas/inspect' &&
                        body?.document?.snapshot_id === snapshot &&
                        !window.__atlasDelayedInspectionStarted;
                    if (tracked) window.__atlasDelayedInspectionStarted = true;
                    const response = await original(url, options);
                    if (tracked) {
                        const read = response.json.bind(response);
                        response.json = async () => {
                            try { return await read(); }
                            finally {
                                setTimeout(() => {
                                    window.__atlasDelayedInspectionDone = true;
                                }, 0);
                            }
                        };
                    }
                    return response;
                };
            }""",
            before["snapshot_id"],
        )
        try:
            self.goto(page, "home")
            self.open_atlas(page)
            page.wait_for_function(
                "() => window.__atlasDelayedInspectionStarted === true"
            )
            if disposed:
                # app.js calls this page's disposal hook on actual navigation;
                # the replacement page shares the app's remembered draft map.
                self.goto(page, "home")
                self.open_atlas(page)
                expect(
                    page.get_by_text(f"Snapshot: {before['snapshot_id']}.", exact=False)
                ).to_be_visible()
            # A normal UI replacement remains available while remembered data
            # is being checked; this is the independently reviewed race.
            self.import_document(page, after, f"fictional-current-{outcome}.json")
            assert held and held["response"].status == 200
            self.find(page)
            expect(region).to_contain_text("Lantern lending period is 21 days.")
            current_raw = self.retained_download(
                page, "Download context JSON", f"delayed-{outcome}-current.json"
            )
            current = json.loads(current_raw)
            assert current["snapshot_id"] == after["snapshot_id"]
            self.consent(page).check()
            visible = region.inner_text()
            if failed:
                held["route"].fulfill(
                    status=400,
                    json={"error": "Fictional delayed remembered-packet rejection"},
                )
            else:
                held["route"].fulfill(response=held["response"])
            held["released"] = True
            page.wait_for_function("() => window.__atlasDelayedInspectionDone === true")
            expect(
                page.get_by_text(f"Snapshot: {after['snapshot_id']}.", exact=False)
            ).to_be_visible()
            expect(region).to_contain_text("Lantern lending period is 21 days.")
            assert region.inner_text() == visible
            expect(region).not_to_contain_text(
                "Fictional delayed remembered-packet rejection"
            )
            # Superseded responses cannot silently change the approved selection.
            expect(self.consent(page)).to_be_checked()
            retained_raw = self.retained_download(
                page, "Download context JSON", f"delayed-{outcome}-retained.json"
            )
            assert json.loads(retained_raw) == current
            self.find(page)
            searched = json.loads(
                self.retained_download(
                    page, "Download context JSON", f"delayed-{outcome}-next-search.json"
                )
            )
            assert searched["snapshot_id"] == after["snapshot_id"]
            assert searched["items"] == current["items"]
            self.screenshot(page, f"atlas-delayed-remembered-{outcome}")
            page.unroute(pattern, hold_inspection)
            # Leaving and reopening uses the app's actual remembered state.
            self.goto(page, "home")
            self.open_atlas(page)
            expect(
                page.get_by_text(f"Snapshot: {after['snapshot_id']}.", exact=False)
            ).to_be_visible()
            self.find(page)
            expect(region).to_contain_text("Lantern lending period is 21 days.")
            expect(region).not_to_contain_text("Lantern lending period is 14 days.")
            assert (self.artifacts / f"delayed-{outcome}-old.json").read_text(
                encoding="utf-8"
            ) == old_raw
            self.delayed_inspections.append(
                {
                    "outcome": outcome,
                    "page_disposed_and_reopened": disposed,
                    "held_snapshot": before["snapshot_id"],
                    "accepted_snapshot": after["snapshot_id"],
                    "actual_server_inspection_status": held["response"].status,
                    "injected_response_status": 400 if failed else None,
                    "results_and_download_preserved": True,
                    "next_search_and_remembered_snapshot": searched["snapshot_id"],
                    "consent_unchanged_by_superseded_response": True,
                }
            )
        finally:
            if held and not held.get("released"):
                held["route"].abort()
            page.unroute(pattern, hold_inspection)

    def delayed_remembered_success(self, page):
        self.delayed_remembered_packet(page, failed=False)

    def delayed_remembered_failure(self, page):
        self.delayed_remembered_packet(page, failed=True)

    def disposed_remembered_success(self, page):
        self.delayed_remembered_packet(page, failed=False, disposed=True)

    def disposed_remembered_failure(self, page):
        self.delayed_remembered_packet(page, failed=True, disposed=True)


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import sync_playwright

    loaded, fixture_evidence = {}, []
    for name in (
        "rkc_sinter_context_bridge.v1.json",
        "rkc_sinter_context_bridge_source_bound.v1.json",
        "rkc_markdown_bundle.v1.json",
    ):
        raw = (FIXTURES / name).read_bytes()
        document = json.loads(raw)
        loaded[name] = document
        evidence = {"file": name, "sha256": hashlib.sha256(raw).hexdigest()}
        for key in ("origin", "origin_sha256"):
            if key in document:
                evidence[key] = document[key]
        fixture_evidence.append(evidence)
    packets = loaded["rkc_sinter_context_bridge.v1.json"]["packets"]
    source_bound_packets = loaded["rkc_sinter_context_bridge_source_bound.v1.json"][
        "packets"
    ]
    bundle = loaded["rkc_markdown_bundle.v1.json"]
    artifact_root = ROOT / "browser-artifacts"
    artifact_root.mkdir(exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix="atlas-source-", dir=artifact_root))
    forbidden = ForbiddenCalls()
    receipt = None
    with tempfile.TemporaryDirectory(prefix="sinter-atlas-source-fictional-") as data:
        with ExitStack() as guards:
            forbidden.install(guards)
            server = make_server(port=0, directory=data)
            fixture = FictionalRKC(packets)
            network = LoopbackOnly(server.server_port, fixture.port)
            network.install(guards)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            fixture.start()
            try:
                with sync_playwright() as playwright:
                    browser = launch_chromium(playwright, args.chromium)
                    try:
                        checks = AtlasSourceChecks(
                            browser,
                            server,
                            artifacts,
                            packets,
                            bundle,
                            fixture,
                            source_bound_packets,
                        )
                        for name, action in (
                            ("rich-context-source", checks.rich_context_source),
                            ("bundle-markdown-body", checks.bundle_markdown_body),
                            ("explicit-snapshot-update", checks.explicit_update),
                            ("question-edit-consent", checks.question_edit_consent),
                            (
                                "omitted-artifact-provenance-refusal",
                                checks.reject_omitted_artifact_provenance,
                            ),
                            (
                                "delayed-remembered-success",
                                checks.delayed_remembered_success,
                            ),
                            (
                                "delayed-remembered-failure",
                                checks.delayed_remembered_failure,
                            ),
                            (
                                "disposed-remembered-success",
                                checks.disposed_remembered_success,
                            ),
                            (
                                "disposed-remembered-failure",
                                checks.disposed_remembered_failure,
                            ),
                            (
                                "corrupt-identity-refusal",
                                checks.reject_corrupt_identity,
                            ),
                            (
                                "recorded-loopback-transport",
                                checks.recorded_loopback_transport,
                            ),
                        ):
                            checks.check(name, action)
                        expected = [
                            row
                            for row in checks.errors
                            if row["check"] == "corrupt-identity-refusal"
                            and row.get("url", "").endswith("/api/atlas/inspect")
                            and "400" in row["error"]
                            or row["check"] == "recorded-loopback-transport"
                            and row.get("url", "").endswith("/api/atlas/retrieve")
                            and "400" in row["error"]
                            or row["check"] == "omitted-artifact-provenance-refusal"
                            and row.get("url", "").endswith("/api/atlas/inspect")
                            and "400" in row["error"]
                            or row["check"]
                            in {
                                "delayed-remembered-failure",
                                "disposed-remembered-failure",
                            }
                            and row.get("url", "").endswith("/api/atlas/inspect")
                            and "400" in row["error"]
                        ]
                        unexpected = [
                            row for row in checks.errors if row not in expected
                        ]
                        receipt = {
                            "schema": "sinter-atlas-source-browser/v1",
                            "scope": (
                                "Fictional fixtures, real browser/server, "
                                "no inference or external service"
                            ),
                            "fixtures": fixture_evidence,
                            "checks": checks.results,
                            "screenshots": checks.screenshots,
                            "downloads": checks.downloads,
                            "delayed_inspections": checks.delayed_inspections,
                            "expected_http_errors": expected,
                            "unexpected_browser_errors": unexpected,
                            "external_browser_requests": checks.external,
                            "forbidden_call_attempts": forbidden.attempts,
                            "model_calls": forbidden.count("model"),
                            "search_calls": forbidden.count("search"),
                            "credential_calls": forbidden.count("credential"),
                            "allowed_loopback_operations": len(network.allowed),
                            "blocked_network_attempts": network.blocked,
                            "recorded_loopback_requests": fixture.requests,
                            "unexpected_loopback_requests": fixture.unexpected,
                            "passed": all(row["passed"] for row in checks.results)
                            and not unexpected
                            and not checks.external
                            and not forbidden.attempts
                            and not network.blocked
                            and not fixture.unexpected,
                        }
                        (artifacts / "receipt.json").write_text(
                            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
                        )
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                fixture.close()
    print("Evidence: " + str(artifacts), flush=True)
    if not receipt or not receipt["passed"]:
        raise SystemExit("FAIL: inspect receipt.json")
    print(
        "PASS: eleven fictional Atlas source journeys; "
        "no model/search/credential or external calls"
    )


if __name__ == "__main__":
    main()
