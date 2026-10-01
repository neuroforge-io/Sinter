"""Latest-campaign recovery must follow successful saves, even under a tied clock."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from unittest.mock import patch
from uuid import UUID

import pytest

from sinter import campaigns

CLOCK = "2026-10-01T12:00:00+00:00"


def document(title: str) -> dict[str, str]:
    """Return harmless campaign input with no external source or account data."""
    return {"title": title, "objective": "Fictional save-order regression only."}


def test_latest_created_campaign_wins_same_second_against_uuid_order(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    with patch.object(campaigns, "utc_now", return_value=CLOCK), patch.object(
        campaigns.uuid, "uuid4", side_effect=[UUID(hex="1" * 32), UUID(hex="f" * 32)]
    ):
        older = store.save(document("Fictional older USD campaign"))
        later = store.save(document("Fictional later other-currency campaign"))

    reopened = campaigns.CampaignStore(tmp_path)
    assert [row["id"] for row in reopened.list()] == [later["id"], older["id"]]
    assert reopened.get(reopened.list()[0]["id"]) == later
    assert reopened.get(older["id"]) == older


def test_latest_edit_keeps_identity_and_moves_older_campaign_first(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    with patch.object(campaigns, "utc_now", return_value=CLOCK), patch.object(
        campaigns.uuid, "uuid4", side_effect=[UUID(hex="f" * 32), UUID(hex="1" * 32)]
    ):
        older = store.save(document("Fictional original campaign"))
        other = store.save(document("Fictional separate campaign"))
        edited = store.save(
            {**older["document"], "title": "Fictional latest edit"},
            older["id"], older["revision"],
        )

    assert edited["id"] == older["id"] and edited["revision"] == 2
    assert [row["id"] for row in store.list()] == [edited["id"], other["id"]]
    assert store.get(other["id"]) == other
    assert store.get(store.list()[0]["id"]) == edited


@pytest.mark.parametrize("clock", [CLOCK, "2026-09-30T11:00:00+00:00"])
@pytest.mark.parametrize("legacy_stamp", [CLOCK, CLOCK.replace("+00:00", "Z")])
def test_legacy_second_timestamp_and_clock_rollback_keep_latest_save(
    tmp_path, clock, legacy_stamp
):
    store = campaigns.CampaignStore(tmp_path)
    with patch.object(campaigns.uuid, "uuid4", return_value=UUID(hex="1" * 32)):
        legacy = store.save(document("Fictional legacy campaign"))
    with store._connect() as db:
        db.execute(
            "UPDATE campaigns SET updated_at=? WHERE id=?", (legacy_stamp, legacy["id"])
        )
        columns = [row["name"] for row in db.execute("PRAGMA table_info(campaigns)")]
    with patch.object(campaigns, "utc_now", return_value=clock), patch.object(
        campaigns.uuid, "uuid4", return_value=UUID(hex="f" * 32)
    ):
        latest = store.save(document("Fictional saved after legacy"))

    reopened = campaigns.CampaignStore(tmp_path)
    listing = reopened.list()
    assert listing[0]["id"] == latest["id"]
    assert (
        datetime.fromisoformat(listing[0]["updated_at"]) > datetime.fromisoformat(CLOCK)
    )
    assert listing[1]["updated_at"] == legacy_stamp
    assert reopened.get(legacy["id"]) == legacy
    with reopened._connect() as db:
        reopened_columns = [
            row["name"] for row in db.execute("PRAGMA table_info(campaigns)")
        ]
        assert reopened_columns == columns


def test_mixed_legacy_utc_spellings_order_by_instant_without_rewriting(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    with patch.object(campaigns.uuid, "uuid4", side_effect=[
        UUID(hex="1" * 32), UUID(hex="f" * 32), UUID(hex="e" * 32)
    ]):
        earlier = store.save(document("Fictional legacy Z"))
        later = store.save(document("Fictional legacy fractional UTC"))
        stamps = [CLOCK.replace("+00:00", "Z"), "2026-10-01T12:00:00.000010+00:00"]
        with store._connect() as db:
            for saved, stamp in zip([earlier, later], stamps):
                db.execute("UPDATE campaigns SET updated_at=? WHERE id=?",
                           (stamp, saved["id"]))
        assert [row["id"] for row in store.list()] == [later["id"], earlier["id"]]
        with patch.object(campaigns, "utc_now", return_value=CLOCK):
            latest = store.save(document("Fictional saved after both UTC forms"))

    assert [row["id"] for row in store.list()] == [
        latest["id"], later["id"], earlier["id"]
    ]
    assert store.list()[0]["updated_at"] == "2026-10-01T12:00:00.000011+00:00"
    assert [row["updated_at"] for row in store.list()[1:]] == stamps[::-1]
    assert store.get(earlier["id"]) == earlier
    assert store.get(later["id"]) == later


def test_failed_stale_save_does_not_change_latest_order_or_saved_metadata(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    with patch.object(campaigns, "utc_now", return_value=CLOCK):
        saved = store.save(document("Fictional first revision"))
        edited = store.save(document("Fictional second revision"), saved["id"], 1)
        other = store.save(document("Fictional latest separate campaign"))
        before = store.list()
        with pytest.raises(ValueError, match="another window"):
            store.save(document("Fictional stale edit"), saved["id"], 1)
        with pytest.raises(ValueError):
            store.save({"title": "Invalid fictional campaign", "ready": True})

    assert store.list() == before
    assert store.get(saved["id"]) == edited
    assert store.get(other["id"]) == other


def test_two_connections_serialize_save_order_under_fixed_clock(tmp_path):
    barrier = Barrier(2)

    def save(index):
        store = campaigns.CampaignStore(tmp_path)
        barrier.wait(timeout=5)
        return store.save(document(f"Fictional concurrent campaign {index}"))

    with patch.object(campaigns, "utc_now", return_value=CLOCK):
        with ThreadPoolExecutor(max_workers=2) as pool:
            saved = list(pool.map(save, range(2)))
        store = campaigns.CampaignStore(tmp_path)
        listing = store.list()
        stamps = [datetime.fromisoformat(row["updated_at"]) for row in listing]
        assert stamps[0] > stamps[1]
        assert {row["id"] for row in listing} == {row["id"] for row in saved}
        earlier = next(row for row in saved if row["id"] == listing[-1]["id"])
        edited = store.save(document("Fictional final edit"), earlier["id"], 1)

    assert store.list()[0]["id"] == edited["id"]
    assert store.get(edited["id"]) == edited
    assert store.list()[1]["id"] == listing[0]["id"]
