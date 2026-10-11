"""Build an undirected explainable graph without transitive identity claims."""

from __future__ import annotations

import hashlib
from itertools import combinations

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from idlink.core.models import Edge, Profile
from idlink.core.scoring import score


def edge_id(a: str, b: str) -> str:
    """Derive a direction-independent ID using unambiguous length prefixes."""
    left, right = sorted((a, b))
    return hashlib.sha256(f"{len(left)}:{left}{len(right)}:{right}".encode()).hexdigest()[:16]


class Node(BaseModel):
    """Only the public locator and display label go into the report."""

    model_config = ConfigDict(extra="forbid")
    id: str
    platform: str
    username: str


class Report(BaseModel):
    """User-requested artifact; never a persistent full-profile cache."""

    model_config = ConfigDict(extra="forbid")
    version: str = "1"
    nodes: list[Node]
    edges: dict[str, Edge]
    warnings: list[str] = Field(default_factory=list)


def build_graph(profiles: list[Profile]) -> nx.Graph[str]:
    """Evaluate each pair independently; duplicate profile URLs are rejected."""
    graph: nx.Graph[str] = nx.Graph()
    for profile in profiles:
        if profile.url in graph:
            raise ValueError("duplicate profile URL")
        graph.add_node(profile.url, platform=profile.platform, username=profile.username)
    for a, b in combinations(profiles, 2):
        edge = score(a, b)
        graph.add_edge(a.url, b.url, id=edge_id(a.url, b.url), edge=edge, weight=edge.probability)
    return graph


def make_report(profiles: list[Profile], warnings: list[str] | None = None) -> Report:
    """Project the graph to a typed minimal report schema."""
    graph = build_graph(profiles)
    edges: dict[str, Edge] = {}
    for _, _, attrs in graph.edges(data=True):
        edge = attrs["edge"]
        if not isinstance(edge, Edge):
            raise TypeError("graph edge must contain an Edge")
        edges[str(attrs["id"])] = edge
    return Report(
        nodes=[Node(id=p.url, platform=p.platform, username=p.username) for p in profiles],
        edges=edges,
        warnings=warnings or [],
    )
