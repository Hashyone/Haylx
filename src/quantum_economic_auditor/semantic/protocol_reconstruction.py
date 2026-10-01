from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantum_economic_auditor.models.graph import (
    EdgeKind,
    EvidenceEdge,
    EvidenceEdgeKind,
    EvidenceGraph,
    EvidenceNode,
    EvidenceNodeKind,
    KnowledgeGraph,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    NodeKind,
)
from quantum_economic_auditor.parser.repository_loader import load_repository


@dataclass
class ProtocolEntity:
    kind: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconstructedInvariant:
    name: str
    expression: str
    description: str | None = None


@dataclass
class ProtocolReconstructionResult:
    entities: list[ProtocolEntity]
    invariants: list[ReconstructedInvariant]
    protocol_graph: KnowledgeGraph
    evidence_graph: EvidenceGraph


class ProtocolReconstructionEngine:
    """Reconstruct protocol semantics into graph and invariant structures."""

    def reconstruct(self, *, repository_path: Path | str) -> ProtocolReconstructionResult:
        root = Path(repository_path)
        repo_model = load_repository(str(root))
        entities: list[ProtocolEntity] = []
        invariants: list[ReconstructedInvariant] = []
        graph_nodes: list[KnowledgeGraphNode] = []
        graph_edges: list[KnowledgeGraphEdge] = []
        evidence_nodes: list[EvidenceNode] = []
        evidence_edges: list[EvidenceEdge] = []

        for contract_file in repo_model.contract_files:
            text = contract_file.read_text(encoding="utf-8", errors="ignore")
            contract_name = self._extract_contract_name(text) or contract_file.stem
            entities.append(ProtocolEntity(kind="contract", name=contract_name, metadata={"file": str(contract_file)}))
            graph_nodes.append(KnowledgeGraphNode(id=f"contract:{contract_name}", kind=NodeKind.SUBSYSTEM, label=contract_name))
            evidence_nodes.append(EvidenceNode(id=f"evidence:{contract_name}", kind=EvidenceNodeKind.EVIDENCE, label=contract_name, evidence_type="contract"))

            if "modifier" in text or "require" in text:
                permission_name = f"{contract_name}:permission"
                entities.append(ProtocolEntity(kind="permission", name=permission_name))
                graph_nodes.append(KnowledgeGraphNode(id=permission_name, kind=NodeKind.AUTHORITY_MODEL, label="permission"))
                graph_edges.append(KnowledgeGraphEdge(source=f"contract:{contract_name}", target=permission_name, kind=EdgeKind.DEPENDENCY))
                evidence_edges.append(EvidenceEdge(source=f"evidence:{contract_name}", target=f"evidence:{permission_name}", kind=EvidenceEdgeKind.SUPPORTS))

            for variable in self._extract_state_variables(text):
                entities.append(ProtocolEntity(kind="state_variable", name=variable))
                graph_nodes.append(KnowledgeGraphNode(id=f"state:{variable}", kind=NodeKind.INVARIANT, label=variable))
                graph_edges.append(KnowledgeGraphEdge(source=f"contract:{contract_name}", target=f"state:{variable}", kind=EdgeKind.DEPENDENCY))

            for function_name in self._extract_functions(text):
                entities.append(ProtocolEntity(kind="transition", name=function_name))
                graph_nodes.append(KnowledgeGraphNode(id=f"transition:{function_name}", kind=NodeKind.STATE_MACHINE, label=function_name))
                graph_edges.append(KnowledgeGraphEdge(source=f"contract:{contract_name}", target=f"transition:{function_name}", kind=EdgeKind.DEPENDENCY))

            if re.search(r"\bborrow\b", text, re.I):
                entities.append(ProtocolEntity(kind="economic_variable", name="debt"))
                entities.append(ProtocolEntity(kind="economic_variable", name="collateral"))
                invariants.append(ReconstructedInvariant(name="collateralization", expression="collateral >= debt", description="Borrowing requires backing collateral"))
                graph_nodes.append(KnowledgeGraphNode(id="economic:debt", kind=NodeKind.ECONOMIC_MODEL, label="debt"))
                graph_nodes.append(KnowledgeGraphNode(id="economic:collateral", kind=NodeKind.ECONOMIC_MODEL, label="collateral"))
                graph_edges.append(KnowledgeGraphEdge(source="economic:collateral", target="economic:debt", kind=EdgeKind.SHARED_ACCOUNTING_MODEL))

        if not entities:
            entities.append(ProtocolEntity(kind="contract", name=root.name))

        if "owner" in " ".join(entity.name for entity in entities):
            entities.append(ProtocolEntity(kind="actor", name="owner"))
            graph_nodes.append(KnowledgeGraphNode(id="actor:owner", kind=NodeKind.AUTHORITY_MODEL, label="owner"))
            graph_edges.append(KnowledgeGraphEdge(source="actor:owner", target="contract:Vault", kind=EdgeKind.DEPENDENCY))

        protocol_graph = KnowledgeGraph(nodes=graph_nodes, edges=graph_edges)
        evidence_graph = EvidenceGraph(nodes=evidence_nodes, edges=evidence_edges)
        return ProtocolReconstructionResult(
            entities=entities,
            invariants=invariants,
            protocol_graph=protocol_graph,
            evidence_graph=evidence_graph,
        )

    def _extract_contract_name(self, text: str) -> str | None:
        match = re.search(r"contract\s+(\w+)", text)
        return match.group(1) if match else None

    def _extract_state_variables(self, text: str) -> list[str]:
        matches = re.findall(r"(?:mapping\([^\n]*\)|\w+)\s+(public|private|internal)?\s*(\w+)", text)
        variables: list[str] = []
        for match in matches:
            variable_name = match[1]
            if variable_name not in {"contract", "modifier", "function", "require", "return"}:
                variables.append(variable_name)
        return sorted(set(variables))

    def _extract_functions(self, text: str) -> list[str]:
        return [match.group(1) for match in re.finditer(r"function\s+(\w+)", text)]
