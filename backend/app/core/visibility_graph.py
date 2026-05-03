"""
Visibility Graph & Distance Matrix — Section 5.1 of PRD.
Builds an obstacle-aware graph over delivery points + depot + NFZ vertices.
Uses shapely for geometric tests and NetworkX for all-pairs Dijkstra.
"""
from __future__ import annotations

import math
import networkx as nx
from shapely.geometry import LineString, Polygon, Point

from app.models.scenario import Scenario, Position


# Node key helpers
DEPOT_KEY = "depot"


def pos_key(p: Position) -> str:
    return f"{p.x:.2f},{p.y:.2f}"


def key_to_pos(key: str) -> Position:
    x, y = key.split(",")
    return Position(x=float(x), y=float(y))


def build_visibility_graph_and_matrix(scenario: Scenario) -> dict:
    """
    Returns:
        {
          "graph": nx.Graph,
          "nodes": {node_key: Position},
          "distance_matrix": {id1: {id2: float}},
          "path_cache": {(id1, id2): [Position, ...]},
          "centrality_ids": [delivery_point_ids + "depot"],
        }
    """
    nfz_polygons = [
        Polygon([(v.x, v.y) for v in zone.polygon])
        for zone in scenario.no_fly_zones
    ]

    # Build node set
    nodes: dict[str, Position] = {}

    nodes[DEPOT_KEY] = scenario.depot
    for dp in scenario.delivery_points:
        nodes[dp.id] = dp.position
    for zone in scenario.no_fly_zones:
        for i, v in enumerate(zone.polygon):
            k = f"{zone.id}_v{i}"
            nodes[k] = v

    # Build visibility graph
    G = nx.Graph()
    for k, pos in nodes.items():
        G.add_node(k, pos=pos)

    node_keys = list(nodes.keys())
    for i in range(len(node_keys)):
        for j in range(i + 1, len(node_keys)):
            k1, k2 = node_keys[i], node_keys[j]
            p1 = nodes[k1]
            p2 = nodes[k2]
            if _segment_free(p1, p2, nfz_polygons):
                dist = math.hypot(p2.x - p1.x, p2.y - p1.y)
                G.add_edge(k1, k2, weight=dist)

    # All-pairs Dijkstra for interest nodes only (depot + delivery points)
    interest_keys = [DEPOT_KEY] + [dp.id for dp in scenario.delivery_points]

    distance_matrix: dict[str, dict[str, float]] = {}
    path_cache: dict[tuple[str, str], list[Position]] = {}

    for src in interest_keys:
        if src not in G:
            continue
        try:
            lengths, paths = nx.single_source_dijkstra(G, src, weight="weight")
        except nx.NetworkXError:
            continue
        distance_matrix[src] = {}
        for tgt in interest_keys:
            if tgt == src:
                distance_matrix[src][tgt] = 0.0
                path_cache[(src, tgt)] = [nodes[src]]
            elif tgt in lengths:
                distance_matrix[src][tgt] = lengths[tgt]
                path_positions = [nodes[nk] for nk in paths[tgt]]
                path_cache[(src, tgt)] = path_positions
            else:
                # Fallback: straight line if no path (should not happen with valid graph)
                d = math.hypot(
                    nodes[tgt].x - nodes[src].x,
                    nodes[tgt].y - nodes[src].y,
                )
                distance_matrix[src][tgt] = d
                path_cache[(src, tgt)] = [nodes[src], nodes[tgt]]

    return {
        "graph": G,
        "nodes": nodes,
        "distance_matrix": distance_matrix,
        "path_cache": path_cache,
        "interest_keys": interest_keys,
    }


def _segment_free(p1: Position, p2: Position, polygons: list[Polygon]) -> bool:
    """Return True if segment p1→p2 doesn't pass through any NFZ interior."""
    seg = LineString([(p1.x, p1.y), (p2.x, p2.y)])
    mid = Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    for poly in polygons:
        if not poly.is_valid:
            continue
        # Segment intersects polygon boundary AND midpoint is inside → blocked
        if poly.contains(mid):
            return False
        if seg.crosses(poly):
            return False
    return True


def dist(dist_matrix: dict, a: str, b: str) -> float:
    """Safe distance lookup."""
    try:
        return dist_matrix[a][b]
    except KeyError:
        try:
            return dist_matrix[b][a]
        except KeyError:
            return float("inf")
