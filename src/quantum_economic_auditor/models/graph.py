from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NodeKind(str, Enum):
    SUBSYSTEM = "subsystem"
    GUARANTEE = "guarantee"
    MATHEMATICAL_SPECIFICATION = "mathematical_specification"
    INVARIANT = "invariant"
    STATE_MACHINE = "state_machine"
    AUTHORITY_MODEL = "authority_model"
    THREAT_MODEL = "threat_model"
    HISTORICAL_EXPLOIT = "historical_exploit"
    AUDIT_OBSERVATION = "audit_observation"
    ECONOMIC_MODEL = "economic_model"
    PROTOCOL_RELATIONSHIP = "protocol_relationship"
    IMPLEMENTATION_BOUNDARY = "implementation_boundary"
    IMPLEMENTATION_TRACE = "implementation_trace"
    DESIGN_TRADEOFF = "design_tradeoff"
    VALIDATION_RESULT = "validation_result"
    CROSS_PROTOCOL_SIMILARITY = "cross_protocol_similarity"


class EdgeKind(str, Enum):
    SIMILARITY = "similarity"
    DEPENDENCY = "dependency"
    IMPLEMENTS = "implements"
    SUPPORTS = "supports"
    DEPENDS_ON = "depends_on"
    SHARED_INVARIANT = "shared_invariant"
    SHARED_AUTHORITY_STRUCTURE = "shared_authority_structure"
    SHARED_ACCOUNTING_MODEL = "shared_accounting_model"
    SHARED_EXPLOIT_CLASS = "shared_exploit_class"


class KnowledgeGraphNode(BaseModel):
    id: str
    kind: NodeKind
    label: str
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeGraphEdge(BaseModel):
    source: str
    target: str
    kind: EdgeKind
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeGraph(BaseModel):
    nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    edges: list[KnowledgeGraphEdge] = Field(default_factory=list)

    def get_node(self, node_id: str) -> KnowledgeGraphNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_edge(self, source: str, target: str) -> KnowledgeGraphEdge | None:
        for edge in self.edges:
            if edge.source == source and edge.target == target:
                return edge
        return None


class EvidenceNodeKind(str, Enum):
    EVIDENCE = "evidence"
    CLAIM = "claim"
    HYPOTHESIS = "hypothesis"
    VALIDATION = "validation"


class EvidenceEdgeKind(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVES_FROM = "derives_from"
    REINFORCES = "reinforces"


class EvidenceNode(BaseModel):
    id: str
    kind: EvidenceNodeKind
    label: str
    evidence_type: str
    metadata: dict[str, object] = Field(default_factory=dict)


class EvidenceEdge(BaseModel):
    source: str
    target: str
    kind: EvidenceEdgeKind
    metadata: dict[str, object] = Field(default_factory=dict)


class EvidenceGraph(BaseModel):
    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)

    def get_node(self, node_id: str) -> EvidenceNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_edge(self, source: str, target: str) -> EvidenceEdge | None:
        for edge in self.edges:
            if edge.source == source and edge.target == target:
                return edge
        return None
