"""Tests for stats API — ledger and pod anomaly endpoints."""

import time

import pytest
from fastapi.testclient import TestClient

from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def _insert_ledger_row(conn, assembly_id, item_type_id, event_type="TRANSFER", quantity=10):
    now = int(time.time())
    conn.execute(
        "INSERT INTO item_ledger "
        "(assembly_id, item_type_id, event_type, quantity, event_id, transaction_hash, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (assembly_id, item_type_id, event_type, quantity, f"evt-{now}", f"tx-{now}", now),
    )
    conn.commit()


def _insert_anomaly(
    conn,
    anomaly_id,
    detector="pod_checker",
    anomaly_type="POD_MISMATCH",
    system_id="30012602",
    object_id="obj-1",
    severity="HIGH",
):
    now = int(time.time())
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, anomaly_type, severity, category, "
        "detector, rule_id, object_id, system_id, detected_at, evidence_json, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            anomaly_id,
            anomaly_type,
            severity,
            "ECONOMIC",
            detector,
            "P1",
            object_id,
            system_id,
            now,
            "{}",
            "UNVERIFIED",
        ),
    )
    conn.commit()


def _insert_object(conn, object_id, system_id, object_type="SmartAssembly"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, current_owner, "
        "system_id, last_event_id, last_seen, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (object_id, object_type, "{}", "", system_id, "evt-1", now, now),
    )
    conn.commit()


def test_stats_ledger_empty(client):
    resp = client.get("/api/stats/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_items_tracked"] == 0
    assert body["total_events"] == 0
    assert body["top_assemblies"] == []
    assert body["by_event_type"] == {}


def test_stats_ledger_with_data(client):
    conn = app.state.db
    _insert_ledger_row(conn, "asm-1", "item-A", "TRANSFER", 10)
    _insert_ledger_row(conn, "asm-1", "item-B", "MINT", 5)
    _insert_ledger_row(conn, "asm-2", "item-A", "TRANSFER", 20)
    resp = client.get("/api/stats/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_events"] == 3
    assert body["top_assemblies"][0]["assembly_id"] == "asm-1"
    assert body["top_assemblies"][0]["event_count"] == 2
    assert body["by_event_type"]["TRANSFER"] == 2
    assert body["by_event_type"]["MINT"] == 1


def _insert_reference(conn, system_id, name, x, z):
    import json

    conn.execute(
        "INSERT INTO reference_data (data_type, data_id, name, data_json, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "solarsystems",
            system_id,
            name,
            json.dumps({"id": system_id, "name": name, "location": {"x": x, "y": 0, "z": z}}),
            int(time.time()),
        ),
    )
    conn.commit()


def test_stats_map_empty(client):
    resp = client.get("/api/stats/map")
    assert resp.status_code == 200
    body = resp.json()
    assert body["systems"] == []
    assert body["recent_events"] == []


def test_stats_map_with_data(client):
    conn = app.state.db
    _insert_anomaly(conn, "MAP-1", detector="continuity_checker", anomaly_type="ORPHAN")
    _insert_reference(conn, "30012602", "Terminus", -5103797186450162000, 1335601100954271700)

    resp = client.get("/api/stats/map")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["systems"]) == 1
    sys = body["systems"][0]
    assert sys["system_id"] == "30012602"
    assert sys["name"] == "Terminus"
    assert sys["x"] == -5103797186450162000
    assert sys["z"] == 1335601100954271700
    assert sys["count"] == 1


def test_stats_map_recent_events(client):
    """Recent events include anomaly type, severity, coords, and timestamp."""
    conn = app.state.db
    _insert_anomaly(conn, "EVT-1", detector="pod_checker", anomaly_type="POD_MISMATCH")
    _insert_anomaly(conn, "EVT-2", detector="continuity_checker", anomaly_type="CONTINUITY_BREAK")
    _insert_reference(conn, "30012602", "Terminus", -5103797186450162000, 1335601100954271700)

    resp = client.get("/api/stats/map")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["recent_events"]) == 2
    ev = body["recent_events"][0]
    assert ev["anomaly_id"] in ("EVT-1", "EVT-2")
    assert ev["system_id"] == "30012602"
    assert ev["system_name"] == "Terminus"
    assert ev["x"] == -5103797186450162000
    assert ev["z"] == 1335601100954271700
    assert "anomaly_type" in ev
    assert "severity" in ev
    assert "detected_at" in ev


def test_stats_map_recent_events_excludes_false_positives(client):
    """False positive anomalies should not appear in recent_events."""
    conn = app.state.db
    _insert_anomaly(conn, "EVT-FP", detector="pod_checker", anomaly_type="POD_MISMATCH")
    _insert_reference(conn, "30012602", "Terminus", -5103797186450162000, 1335601100954271700)
    conn.execute("UPDATE anomalies SET status = 'FALSE_POSITIVE' WHERE anomaly_id = 'EVT-FP'")
    conn.commit()

    resp = client.get("/api/stats/map")
    body = resp.json()
    assert body["recent_events"] == []


def test_stats_map_recent_events_excludes_old(client):
    """Anomalies older than 24h should not appear in recent_events."""
    conn = app.state.db
    _insert_anomaly(conn, "EVT-OLD", detector="pod_checker", anomaly_type="POD_MISMATCH")
    _insert_reference(conn, "30012602", "Terminus", -5103797186450162000, 1335601100954271700)
    old_ts = int(time.time()) - 90000  # 25 hours ago
    conn.execute("UPDATE anomalies SET detected_at = ? WHERE anomaly_id = 'EVT-OLD'", (old_ts,))
    conn.commit()

    resp = client.get("/api/stats/map")
    body = resp.json()
    assert body["recent_events"] == []


def test_stats_map_recent_events_skips_no_coords(client):
    """Events without reference data (coordinates) should be excluded."""
    conn = app.state.db
    _insert_anomaly(conn, "EVT-NC", detector="pod_checker", anomaly_type="POD_MISMATCH")
    # No reference_data for system_id 30012602

    resp = client.get("/api/stats/map")
    body = resp.json()
    assert body["recent_events"] == []


def test_stats_map_system_id_from_objects_fallback(client):
    """Anomalies with empty system_id should resolve via objects table."""
    conn = app.state.db
    _insert_object(conn, "obj-abc", "30012602")
    _insert_anomaly(
        conn,
        "MAP-FB",
        detector="economic_checker",
        anomaly_type="UNEXPLAINED_DESTRUCTION",
        system_id="",
        object_id="obj-abc",
    )
    _insert_reference(conn, "30012602", "Terminus", -5103797186450162000, 1335601100954271700)

    resp = client.get("/api/stats/map")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["systems"]) == 1
    assert body["systems"][0]["system_id"] == "30012602"
    assert body["systems"][0]["name"] == "Terminus"
    # Also appears in recent_events
    assert len(body["recent_events"]) == 1
    assert body["recent_events"][0]["system_id"] == "30012602"


def test_stats_map_anomaly_system_id_preferred_over_object(client):
    """When anomaly has its own system_id, it takes precedence over objects table."""
    conn = app.state.db
    _insert_object(conn, "obj-xyz", "99999999")  # different system
    _insert_anomaly(
        conn,
        "MAP-PR",
        detector="pod_checker",
        anomaly_type="POD_MISMATCH",
        system_id="30012602",
        object_id="obj-xyz",
    )
    _insert_reference(conn, "30012602", "Terminus", -5103797186450162000, 1335601100954271700)

    resp = client.get("/api/stats/map")
    body = resp.json()
    assert len(body["systems"]) == 1
    assert body["systems"][0]["system_id"] == "30012602"


def test_stats_map_excludes_false_positives(client):
    conn = app.state.db
    _insert_anomaly(conn, "MAP-FP", detector="continuity_checker", anomaly_type="ORPHAN")
    _insert_reference(conn, "30012602", "Terminus", -5103797186450162000, 1335601100954271700)
    conn.execute("UPDATE anomalies SET status = 'FALSE_POSITIVE' WHERE anomaly_id = 'MAP-FP'")
    conn.commit()

    resp = client.get("/api/stats/map")
    body = resp.json()
    assert body["systems"] == []


def test_stats_map_skips_no_coords(client):
    conn = app.state.db
    _insert_anomaly(conn, "MAP-NC", detector="continuity_checker", anomaly_type="ORPHAN")
    # No reference_data for this system
    resp = client.get("/api/stats/map")
    body = resp.json()
    assert body["systems"] == []


def test_background_systems_empty(client):
    """Background systems returns empty list when no reference data."""
    # Clear cache
    import backend.api.stats as stats_mod
    stats_mod._bg_systems_cache = None
    stats_mod._bg_systems_etag = None

    resp = client.get("/api/stats/map/systems")
    assert resp.status_code == 200
    body = resp.json()
    assert body["all_systems"] == []


def test_background_systems_with_data(client):
    """Background systems returns cached reference data."""
    import backend.api.stats as stats_mod
    stats_mod._bg_systems_cache = None
    stats_mod._bg_systems_etag = None

    conn = app.state.db
    _insert_reference(conn, "30000001", "Alpha", 100, 200)
    _insert_reference(conn, "30000002", "Beta", 300, 400)

    resp = client.get("/api/stats/map/systems")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["all_systems"]) == 2
    assert body["all_systems"][0]["name"] in ("Alpha", "Beta")
    assert "ETag" in resp.headers


def test_background_systems_etag_304(client):
    """Background systems returns 304 when ETag matches."""
    import backend.api.stats as stats_mod
    stats_mod._bg_systems_cache = None
    stats_mod._bg_systems_etag = None

    conn = app.state.db
    _insert_reference(conn, "30000003", "Gamma", 500, 600)

    # First request to populate cache
    resp1 = client.get("/api/stats/map/systems")
    etag = resp1.headers.get("ETag")
    assert etag

    # Second request with matching ETag
    resp2 = client.get("/api/stats/map/systems", headers={"if-none-match": etag})
    assert resp2.status_code == 304


def test_background_systems_skips_zero_coords(client):
    """Background systems excludes systems at origin (0,0)."""
    import backend.api.stats as stats_mod
    stats_mod._bg_systems_cache = None
    stats_mod._bg_systems_etag = None

    conn = app.state.db
    _insert_reference(conn, "30000004", "Origin", 0, 0)
    _insert_reference(conn, "30000005", "Valid", 100, 200)

    resp = client.get("/api/stats/map/systems")
    body = resp.json()
    assert len(body["all_systems"]) == 1
    assert body["all_systems"][0]["name"] == "Valid"


def test_enrich_system_ids(client):
    """Enrich endpoint backfills system_id from nexus killmails."""
    conn = app.state.db
    import json as json_mod
    # Insert an object without system_id
    now = int(time.time())
    conn.execute(
        "INSERT INTO objects (object_id, object_type, current_state, current_owner, "
        "system_id, last_seen, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("obj-enrich", "SmartAssembly", "{}", "", "", now, now),
    )
    # Insert a nexus killmail that references this object
    conn.execute(
        "INSERT INTO nexus_events (event_id, event_type, payload, solar_system_id, received_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "nex-1", "killmail",
            json_mod.dumps({"victim": {"id": "obj-enrich"}, "killer": {"id": "obj-other"}}),
            "30012602", now,
        ),
    )
    conn.commit()

    resp = client.post("/api/stats/map/enrich")
    assert resp.status_code == 200
    body = resp.json()
    assert body["killmails_processed"] == 1
    assert body["enriched_objects"] >= 1

    # Verify object got updated
    row = conn.execute("SELECT system_id FROM objects WHERE object_id = 'obj-enrich'").fetchone()
    assert row["system_id"] == "30012602"


def test_pod_anomalies_count(client):
    conn = app.state.db
    _insert_anomaly(conn, "POD-1", detector="pod_checker", anomaly_type="POD_MISMATCH")
    _insert_anomaly(conn, "OTHER-1", detector="continuity_checker", anomaly_type="STATE_GAP")
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pod_anomalies_24h"] == 1
