from __future__ import annotations

import networkx as nx

from quantum_economic_auditor.models.eir import EconomicIntermediateRepresentation


class EconomicDependencyGraph(nx.DiGraph):
    """Directed dependency graph for protocol dynamics."""

    def __init__(self, eir: EconomicIntermediateRepresentation | None = None) -> None:
        super().__init__()
        if eir is not None:
            self._load_from_eir(eir)

    def _load_from_eir(self, eir: EconomicIntermediateRepresentation) -> None:
        for variable in eir.variables:
            self.add_node(variable.name, category=variable.category)
        for action in eir.actions:
            self.add_node(action.name, category="action")
        for relationship in eir.relationships:
            self.add_edge(relationship.source, relationship.target, relation=relationship.relation)


def build_dependency_graph(eir: EconomicIntermediateRepresentation) -> EconomicDependencyGraph:
    """Deterministically materialize an economic dependency graph from EIR objects."""

    graph = EconomicDependencyGraph(eir)
    return graph
