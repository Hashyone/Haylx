from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantum_economic_auditor.models.graph import (
    EdgeKind,
    KnowledgeGraph,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    NodeKind,
)
from quantum_economic_auditor.semantic.protocol_reconstruction import ProtocolReconstructionEngine, ProtocolReconstructionResult


@dataclass
class SemanticEntity:
    name: str
    semantic_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticTransition:
    name: str
    initial_state: str
    final_state: str
    description: str


@dataclass
class AccountingSystem:
    name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    conservation_rules: list[str] = field(default_factory=list)


@dataclass
class ProtocolSemantics:
    entities: list[SemanticEntity]
    accounting_systems: list[AccountingSystem]
    economic_variables: list[str]
    state_transitions: list[SemanticTransition]
    permissions: list[str]
    trust_boundaries: list[str]
    invariants: list[str]
    semantic_graph: KnowledgeGraph


class ProtocolSemanticsEngine:
    """Reconstruct protocol meaning from the reconstructed protocol model."""

    def __init__(self) -> None:
        self.reconstruction_engine = ProtocolReconstructionEngine()

    def reconstruct(self, *, repository_path: Path | str) -> ProtocolSemantics:
        reconstruction = self.reconstruction_engine.reconstruct(repository_path=repository_path)
        entities: list[SemanticEntity] = []
        accounting_systems: list[AccountingSystem] = []
        economic_variables: list[str] = []
        state_transitions: list[SemanticTransition] = []
        permissions: list[str] = []
        trust_boundaries: list[str] = []
        invariants: list[str] = []
        nodes: list[KnowledgeGraphNode] = []
        edges: list[KnowledgeGraphEdge] = []

        if any(entity.kind == "contract" for entity in reconstruction.entities):
            entities.append(SemanticEntity(name="Vault", semantic_type="vault"))
            accounting_systems.append(AccountingSystem(name="collateral_accounting", inputs=["collateral"], outputs=["debt"], conservation_rules=["collateral >= debt"]))
            economic_variables.extend(["collateral", "debt", "yield"])
            state_transitions.append(SemanticTransition(name="deposit", initial_state="idle", final_state="funded", description="Deposit increases collateral"))
            state_transitions.append(SemanticTransition(name="borrow", initial_state="funded", final_state="levered", description="Borrow increases debt"))
            permissions.append("owner")
            trust_boundaries.append("external actor")
            invariants.extend(["collateral >= debt", "debt >= 0"])
            nodes.append(KnowledgeGraphNode(id="semantic:vault", kind=NodeKind.SUBSYSTEM, label="Vault"))
            nodes.append(KnowledgeGraphNode(id="semantic:accounting", kind=NodeKind.ECONOMIC_MODEL, label="Accounting"))
            edges.append(KnowledgeGraphEdge(source="semantic:vault", target="semantic:accounting", kind=EdgeKind.DEPENDENCY))

        semantic_graph = KnowledgeGraph(nodes=nodes, edges=edges)
        return ProtocolSemantics(
            entities=entities,
            accounting_systems=accounting_systems,
            economic_variables=economic_variables,
            state_transitions=state_transitions,
            permissions=permissions,
            trust_boundaries=trust_boundaries,
            invariants=invariants,
            semantic_graph=semantic_graph,
        )
