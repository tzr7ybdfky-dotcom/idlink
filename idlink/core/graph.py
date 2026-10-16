"""Build an undirected explainable graph without transitive identity claims."""

from __future__ import annotations

import hashlib
from itertools import combinations
from typing import Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from idlink.core.discovery import SimilarMatch
from idlink.core.models import Edge, Profile
from idlink.core.scoring import score
from idlink.plugins.base import ErrorKind
from idlink.signals.links import canonical_url


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


class SourceCheck(BaseModel):
    """Record a lookup outcome separately from person-link probabilities."""

    platform: str
    status: Literal["found", "missing", "error", "invalid", "unverified"]
    detail: str
    error_kind: ErrorKind | None = None
    url: str | None = None


class Report(BaseModel):
    """User-requested artifact; never a persistent full-profile cache."""

    model_config = ConfigDict(extra="forbid")
    version: str = "1"
    nodes: list[Node]
    edges: dict[str, Edge]
    warnings: list[str] = Field(default_factory=list)
    checks: list[SourceCheck] = Field(default_factory=list)
    similar: list[SimilarMatch] = Field(default_factory=list)


def build_graph(profiles: list[Profile], *, sparse: bool = False) -> nx.Graph[str]:
    """Evaluate each pair independently; duplicate profile URLs are rejected."""
    graph: nx.Graph[str] = nx.Graph()
    for profile in profiles:
        if profile.url in graph:
            raise ValueError("duplicate profile URL")
        graph.add_node(profile.url, platform=profile.platform, username=profile.username)
    pairs = sparse_pairs(profiles) if sparse else combinations(range(len(profiles)), 2)
    for left, right in pairs:
        a, b = profiles[left], profiles[right]
        edge = score(a, b)
        if not sparse or edge.probability >= 0.3:
            graph.add_edge(
                a.url, b.url, id=edge_id(a.url, b.url), edge=edge, weight=edge.probability
            )
    return graph


def sparse_pairs(profiles: list[Profile]) -> list[tuple[int, int]]:
    """Only links, avatar pairs or shared bio tokens can raise an edge to 30%."""
    candidates: set[tuple[int, int]] = set()
    urls: dict[str, list[int]] = {}
    for index, profile in enumerate(profiles):
        urls.setdefault(canonical_url(profile.url), []).append(index)
    tokens: dict[str, list[int]] = {}
    avatars: list[int] = []
    for index, profile in enumerate(profiles):
        for link in profile.outbound_links:
            locator = canonical_url(link)
            for other in urls.get(locator, []) if locator else []:
                if other != index:
                    candidates.add((min(index, other), max(index, other)))
        for token in profile.bio_tokens:
            previous = tokens.setdefault(token, [])
            candidates.update((other, index) for other in previous)
            previous.append(index)
        if profile.avatar_phash is not None and not profile.avatar_is_default:
            avatars.append(index)
    candidates.update(combinations(avatars, 2))
    return sorted(candidates)


def make_report(
    profiles: list[Profile], warnings: list[str] | None = None, *, sparse: bool = False
) -> Report:
    """Project the graph to a typed minimal report schema."""
    graph = build_graph(profiles, sparse=sparse)
    edges: dict[str, Edge] = {}
    for _, _, attrs in graph.edges(data=True):
        edge = attrs["edge"]
        if not isinstance(edge, Edge):
            raise TypeError("graph edge must contain an Edge")
        edges[str(attrs["id"])] = edge
    return Report(
        nodes=[Node(id=p.url, platform=p.platform, username=p.username) for p in profiles],
        edges=edges,
        warnings=(warnings or [])
        + (
            ["В большой карте показаны связи с оценкой ≥30%; остальные пары скрыты."]
            if sparse
            else []
        ),
    )
