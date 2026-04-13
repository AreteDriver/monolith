"""Tests for the spectral regions API endpoint.

The regions endpoint partitions the galaxy's background systems into k
communities via `arete-graph-utils.spectral_communities`. These tests
verify the partitioning logic, caching, and graph-building helpers
without depending on a populated WatchTower topology cache.
"""

import json

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from backend.api.regions import (
    build_gate_graph,
    build_knn_graph,
    clear_regions_cache,
    compute_regions,
)
from backend.api.stats import clear_map_cache
from backend.db.database import init_db
from backend.main import app


@pytest.fixture
def client():
    conn = init_db(":memory:")
    app.state.db = conn
    clear_regions_cache()
    clear_map_cache()
    # Also clear the bg_systems cache in stats (module-level)
    from backend.api import stats as stats_module

    stats_module._bg_systems_cache = None
    stats_module._bg_systems_etag = None
    stats_module._bg_bounds = None
    yield TestClient(app, raise_server_exceptions=False)
    conn.close()


def _insert_system(conn, sid: str, name: str, x: int, z: int) -> None:
    data_json = json.dumps(
        {
            "name": name,
            "location": {"x": x, "y": 0, "z": z},
        }
    )
    conn.execute(
        "INSERT OR REPLACE INTO reference_data (data_type, data_id, name, data_json) "
        "VALUES (?, ?, ?, ?)",
        ("solarsystems", sid, name, data_json),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# build_knn_graph
# ---------------------------------------------------------------------------


class TestBuildKnnGraph:
    def test_empty_systems_returns_empty_graph(self):
        g = build_knn_graph([])
        assert g.number_of_nodes() == 0
        assert g.number_of_edges() == 0

    def test_single_system_has_no_edges(self):
        g = build_knn_graph([{"system_id": "s1", "x": 0, "z": 0}])
        assert g.number_of_nodes() == 1
        assert g.number_of_edges() == 0

    def test_knn_graph_has_all_systems_as_nodes(self):
        systems = [{"system_id": f"s{i}", "x": i * 10, "z": 0} for i in range(6)]
        g = build_knn_graph(systems, k=2)
        assert g.number_of_nodes() == 6
        for s in systems:
            assert g.has_node(s["system_id"])

    def test_knn_connects_nearest_neighbors(self):
        # 3 systems on a line; k=1 connects each to its nearest neighbor
        systems = [
            {"system_id": "A", "x": 0, "z": 0},
            {"system_id": "B", "x": 10, "z": 0},
            {"system_id": "C", "x": 100, "z": 0},
        ]
        g = build_knn_graph(systems, k=1)
        assert g.has_edge("A", "B")
        # C's nearest is B, so edge B-C must exist
        assert g.has_edge("B", "C")

    def test_knn_k_clamped_to_max_possible(self):
        # Only 3 systems — requesting k=10 should not crash
        systems = [{"system_id": f"s{i}", "x": i, "z": 0} for i in range(3)]
        g = build_knn_graph(systems, k=10)
        # All 3 systems should be mutually connected (complete graph)
        assert g.number_of_edges() == 3


# ---------------------------------------------------------------------------
# build_gate_graph
# ---------------------------------------------------------------------------


class TestBuildGateGraph:
    def test_gate_graph_uses_provided_edges(self):
        systems = [
            {"system_id": "A", "x": 0, "z": 0},
            {"system_id": "B", "x": 100, "z": 100},
            {"system_id": "C", "x": 200, "z": 200},
        ]
        edges = [("A", "B"), ("B", "C")]
        g = build_gate_graph(systems, edges)
        assert g.has_edge("A", "B")
        assert g.has_edge("B", "C")
        assert not g.has_edge("A", "C")

    def test_gate_graph_ignores_edges_to_unknown_systems(self):
        systems = [{"system_id": "A", "x": 0, "z": 0}]
        edges = [("A", "X")]  # X doesn't exist
        g = build_gate_graph(systems, edges)
        assert g.number_of_edges() == 0

    def test_gate_graph_ignores_self_loops(self):
        systems = [{"system_id": "A", "x": 0, "z": 0}]
        edges = [("A", "A")]
        g = build_gate_graph(systems, edges)
        assert g.number_of_edges() == 0


# ---------------------------------------------------------------------------
# compute_regions
# ---------------------------------------------------------------------------


class TestComputeRegions:
    def test_empty_graph_returns_empty_result(self):
        result = compute_regions(nx.Graph(), [], k=4)
        assert result["n_regions"] == 0
        assert result["regions"] == []

    def test_two_clusters_recovered_as_two_regions(self):
        # Two K3 cliques connected by a bridge
        systems = [{"system_id": f"s{i}", "x": i * 10, "z": 0} for i in range(6)]
        g = nx.Graph()
        for s in systems:
            g.add_node(s["system_id"])
        # Cluster 1: s0-s1-s2
        g.add_edges_from([("s0", "s1"), ("s1", "s2"), ("s0", "s2")])
        # Cluster 2: s3-s4-s5
        g.add_edges_from([("s3", "s4"), ("s4", "s5"), ("s3", "s5")])
        # Bridge
        g.add_edge("s2", "s3")

        result = compute_regions(g, systems, k=2, min_region_size=2)
        assert result["n_regions"] == 2
        # Each region has exactly 3 members
        assert sorted(r["size"] for r in result["regions"]) == [3, 3]

    def test_all_systems_assigned_to_a_region(self):
        systems = [{"system_id": f"s{i}", "x": i, "z": i} for i in range(8)]
        g = build_knn_graph(systems, k=2)
        result = compute_regions(g, systems, k=3, min_region_size=1)
        assert result["n_systems_assigned"] == 8
        assert set(result["assignment"].keys()) == {f"s{i}" for i in range(8)}

    def test_centroids_computed_from_member_coordinates(self):
        systems = [
            {"system_id": "a", "x": 0, "z": 0},
            {"system_id": "b", "x": 10, "z": 0},
            {"system_id": "c", "x": 1000, "z": 1000},
            {"system_id": "d", "x": 1010, "z": 1000},
        ]
        g = nx.Graph()
        for s in systems:
            g.add_node(s["system_id"])
        g.add_edge("a", "b")
        g.add_edge("c", "d")
        # Bridge to make graph connected
        g.add_edge("b", "c")

        result = compute_regions(g, systems, k=2, min_region_size=2)
        centroids = sorted((r["centroid_x"], r["centroid_z"]) for r in result["regions"])
        # One centroid near (5, 0), one near (1005, 1000)
        assert centroids[0][0] < 500
        assert centroids[1][0] > 500


# ---------------------------------------------------------------------------
# /api/map/regions endpoint
# ---------------------------------------------------------------------------


class TestRegionsEndpoint:
    def test_empty_db_returns_empty_regions(self, client):
        response = client.get("/api/map/regions?k=4")
        assert response.status_code == 200
        data = response.json()
        assert data["n_regions"] == 0
        assert data["regions"] == []

    def test_partition_with_k_regions(self, client):
        conn = app.state.db
        # Insert 12 systems in three spatial clusters
        clusters = [
            [(1000, 1000), (1010, 1000), (1000, 1010), (1010, 1010)],
            [(5000, 5000), (5010, 5000), (5000, 5010), (5010, 5010)],
            [(9000, 9000), (9010, 9000), (9000, 9010), (9010, 9010)],
        ]
        idx = 0
        for cluster in clusters:
            for x, z in cluster:
                _insert_system(conn, f"sys-{idx}", f"Sys {idx}", x, z)
                idx += 1

        response = client.get("/api/map/regions?k=3&knn_k=2&min_region_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["k"] == 3
        assert data["n_regions"] >= 2  # At least 2 regions recovered
        assert data["n_systems_assigned"] == 12

    def test_response_caching(self, client):
        conn = app.state.db
        for i in range(6):
            _insert_system(conn, f"s{i}", f"Sys {i}", i * 1000, i * 1000)

        # First call populates the cache
        r1 = client.get("/api/map/regions?k=2&knn_k=1&min_region_size=1")
        assert r1.status_code == 200
        # Second call is served from cache — identical bytes
        r2 = client.get("/api/map/regions?k=2&knn_k=1&min_region_size=1")
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    def test_k_parameter_validated(self, client):
        # k=1 is below minimum, k=100 is above maximum
        r1 = client.get("/api/map/regions?k=1")
        assert r1.status_code == 422
        r2 = client.get("/api/map/regions?k=100")
        assert r2.status_code == 422

    def test_graph_kind_validated(self, client):
        response = client.get("/api/map/regions?k=4&graph_kind=invalid")
        assert response.status_code == 422
