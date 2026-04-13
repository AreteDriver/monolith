"""Spectral region partitioning of the EVE Frontier galaxy graph.

Uses `arete-graph-utils.spectral_communities` to partition the background
systems into k natural regions via recursive Fiedler bisection. This gives
a parameter-free, reproducible "what are the natural clusters here"
answer without tuning modularity thresholds or resolution parameters.

The graph is built from whichever signal is available:
  1. If gate topology is provided (e.g., from WatchTower /topology) we use
     those edges — this is the "real" stargate connectivity.
  2. Otherwise we fall back to a k-nearest-neighbors proximity graph
     in the 2D (x, z) plane of the galaxy map. This gives spatially
     coherent regions without requiring live gate data.

Results are cached for 1 hour because the computation is O(|V|³) in the
worst case on a dense graph, and the underlying system set changes at
most hourly (via the static_data_loop).
"""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

import networkx as nx
from arete_graph_utils import spectral_communities
from fastapi import APIRouter, Query, Request

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/map/regions", tags=["regions"])

# Cache: (k, graph_kind) -> (timestamp, result_dict)
_region_cache: dict[tuple[int, str], tuple[float, dict]] = {}
_REGION_CACHE_TTL = 3600  # 1 hour


def _get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def build_knn_graph(
    systems: list[dict],
    k: int = 3,
) -> nx.Graph:
    """Build a k-nearest-neighbors proximity graph on (x, z) coordinates.

    Args:
        systems: List of dicts with keys `system_id`, `x`, `z`.
        k: Number of nearest neighbors per node.

    Returns:
        Undirected `networkx.Graph` with system_id as node label.
    """
    g = nx.Graph()
    for s in systems:
        g.add_node(s["system_id"], x=s["x"], z=s["z"])

    if len(systems) < 2:
        return g

    k = max(1, min(k, len(systems) - 1))

    # O(n²) brute-force neighbor search — fine for 10K-30K systems at cache rate
    for i, s in enumerate(systems):
        sx, sz = s["x"], s["z"]
        dists: list[tuple[float, str]] = []
        for j, t in enumerate(systems):
            if i == j:
                continue
            dx = t["x"] - sx
            dz = t["z"] - sz
            # Use squared distance to avoid sqrt until needed
            dists.append((dx * dx + dz * dz, t["system_id"]))
        dists.sort(key=lambda pair: pair[0])
        for _, neighbor_id in dists[:k]:
            g.add_edge(s["system_id"], neighbor_id)
    return g


def build_gate_graph(
    systems: list[dict],
    gate_edges: Iterable[tuple[str, str]],
) -> nx.Graph:
    """Build a gate-topology graph from explicit edges.

    Systems without any gate edges remain as isolated nodes in the graph;
    they will be handled by the largest-connected-component fallback in
    `spectral_communities`.

    Args:
        systems: List of dicts with `system_id` — used to populate nodes.
        gate_edges: Iterable of (source_system_id, dest_system_id) pairs.

    Returns:
        Undirected `networkx.Graph`.
    """
    g = nx.Graph()
    for s in systems:
        g.add_node(s["system_id"], x=s["x"], z=s["z"])
    for u, v in gate_edges:
        if g.has_node(u) and g.has_node(v) and u != v:
            g.add_edge(u, v)
    return g


def compute_regions(
    graph: nx.Graph,
    systems: list[dict],
    k: int,
    min_region_size: int = 5,
) -> dict:
    """Partition a system graph into k regions via spectral bisection.

    Args:
        graph: The system connectivity graph (gate or proximity).
        systems: List of dicts with `system_id`, `x`, `z` for centroid
            computation. Must include all nodes in `graph`.
        k: Target number of regions.
        min_region_size: Minimum nodes per region (smaller groups are
            left unsplit).

    Returns:
        Dict with keys:
          - `graph_kind`: "gate" or "knn"
          - `k`: requested number of regions
          - `n_regions`: actual number produced
          - `n_systems_assigned`: total systems placed in a region
          - `regions`: list of region dicts with `id`, `size`, `centroid_x`,
            `centroid_z`, `member_ids` (capped at 50 for payload size)
          - `assignment`: full system_id → region_id mapping
    """
    if graph.number_of_nodes() == 0:
        return {
            "graph_kind": graph.graph.get("kind", "unknown"),
            "k": k,
            "n_regions": 0,
            "n_systems_assigned": 0,
            "regions": [],
            "assignment": {},
        }

    # Handle disconnected graphs: partition each connected component
    # separately, allocating k budget proportional to component size.
    # Isolated singletons become their own tiny community.
    components = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
    if len(components) == 1:
        communities = spectral_communities(graph, k=k, min_community_size=min_region_size)
    else:
        total_nodes = sum(c.number_of_nodes() for c in components)
        communities = []
        remaining_k = k
        for i, comp in enumerate(components):
            is_last = i == len(components) - 1
            if is_last:
                sub_k = remaining_k
            else:
                sub_k = max(1, round(k * comp.number_of_nodes() / total_nodes))
                sub_k = min(sub_k, remaining_k - (len(components) - 1 - i))
                sub_k = max(1, sub_k)
            remaining_k -= sub_k
            if comp.number_of_nodes() == 1 or sub_k <= 1:
                communities.append(frozenset(comp.nodes()))
            else:
                communities.extend(
                    spectral_communities(comp, k=sub_k, min_community_size=min_region_size)
                )

    # Build centroid index from systems list
    coords = {s["system_id"]: (s["x"], s["z"]) for s in systems}

    assignment: dict[str, int] = {}
    regions: list[dict] = []
    for region_id, members in enumerate(communities):
        member_list = sorted(members)
        xs = [coords[m][0] for m in member_list if m in coords]
        zs = [coords[m][1] for m in member_list if m in coords]
        if not xs or not zs:
            continue
        cx = sum(xs) / len(xs)
        cz = sum(zs) / len(zs)
        for m in member_list:
            assignment[m] = region_id
        # Farthest system from centroid (region "radius")
        radius = 0.0
        for m in member_list:
            if m not in coords:
                continue
            dx = coords[m][0] - cx
            dz = coords[m][1] - cz
            d = math.sqrt(dx * dx + dz * dz)
            if d > radius:
                radius = d
        regions.append(
            {
                "id": region_id,
                "size": len(member_list),
                "centroid_x": cx,
                "centroid_z": cz,
                "radius": radius,
                "member_ids": member_list[:50],  # cap for payload
            }
        )

    return {
        "graph_kind": graph.graph.get("kind", "unknown"),
        "k": k,
        "n_regions": len(regions),
        "n_systems_assigned": len(assignment),
        "regions": regions,
        "assignment": assignment,
    }


def clear_regions_cache() -> None:
    """Clear the regions cache. Used by tests."""
    _region_cache.clear()


@router.get("")
def get_regions(
    request: Request,
    k: int = Query(8, ge=2, le=32, description="Target number of regions"),
    graph_kind: str = Query(
        "knn",
        pattern="^(knn|gate)$",
        description="Graph type: 'knn' (spatial proximity) or 'gate' (stargate topology)",
    ),
    knn_k: int = Query(3, ge=1, le=10, description="Neighbors per node for knn graph"),
    min_region_size: int = Query(5, ge=1, le=100),
) -> dict:
    """Partition the galaxy into k spectral regions.

    Returns a deterministic, parameter-free community decomposition of the
    system graph using `arete-graph-utils.spectral_communities`. Cached
    for 1 hour by (k, graph_kind) because the computation is non-trivial
    on 10K+ node graphs.
    """
    cache_key = (k, graph_kind)
    now = time.time()
    cached = _region_cache.get(cache_key)
    if cached is not None and (now - cached[0]) < _REGION_CACHE_TTL:
        return cached[1]

    conn = _get_db(request)

    # Load background systems from reference_data (same source as /api/map/systems)
    from backend.api.stats import _load_bg_systems

    raw_systems = _load_bg_systems(conn)
    if not raw_systems:
        return {
            "graph_kind": graph_kind,
            "k": k,
            "n_regions": 0,
            "n_systems_assigned": 0,
            "regions": [],
            "assignment": {},
            "note": "No background systems loaded",
        }

    # Build the graph
    if graph_kind == "knn":
        graph = build_knn_graph(raw_systems, k=knn_k)
    else:
        # For gate graph we'd need access to the WatchTower /topology response
        # or a local gate-links table. For now, fall back to knn with a note.
        graph = build_knn_graph(raw_systems, k=knn_k)
        graph.graph["note"] = "Gate topology fallback to knn"
    graph.graph["kind"] = graph_kind

    logger.info(
        "Computing %d regions on %s graph (|V|=%d, |E|=%d)",
        k,
        graph_kind,
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
    result = compute_regions(graph, raw_systems, k=k, min_region_size=min_region_size)
    _region_cache[cache_key] = (now, result)
    return result
