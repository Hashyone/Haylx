"""Research framework for comparing classical and quantum optimization on protocol economics.

The package intentionally separates the economic extraction layer from the mathematical
optimization pipeline so that the LLM only describes the protocol and all downstream
transformations remain deterministic and reproducible.
"""

from .consensus.engine import ConsensusEngine, ConsensusResult, FinalClassification
from .environment_orchestration.manager import EnvironmentHealthReport, EnvironmentOrchestrationManager
from .graph.economic_dependency_graph import EconomicDependencyGraph, build_dependency_graph
from .models.constraint import Constraint, ConstraintType
from .models.cpm import Actor, CanonicalProtocolModel, Role, TrustBoundary
from .models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)
from .models.evidence import AgentEvidence, ClaimSource, EvidencedClaim
from .models.graph import EdgeKind, KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode, NodeKind
from .models.objective import ObjectiveSpec, ObjectiveWeight, OptimizationCandidate
from .models.protocol import ProtocolSpec
from .models.state import EncodedVariable, OptimizationResult, PipelineRunSummary
from .methodology.pipeline import MethodologyPhase, MethodologyReport, ProtocolMethodologyPipeline
from .models.truth_layer import MathematicalTruthLayer
from .openclaw.orchestrator import OpenClawOrchestrator, SpecialistAgent
from .reasoning_engines.engines import ClassicalReasoner, MLReasoner, QuantumReasoner, ReasoningOutput

__all__ = [
    "Actor",
    "AgentEvidence",
    "CanonicalProtocolModel",
    "ClaimSource",
    "ConsensusEngine",
    "ConsensusResult",
    "Constraint",
    "ConstraintType",
    "EconomicAction",
    "EconomicDependencyGraph",
    "EconomicIntermediateRepresentation",
    "EdgeKind",
    "EnvironmentHealthReport",
    "FinalClassification",
    "EnvironmentOrchestrationManager",
    "EvidencedClaim",
    "EconomicInvariant",
    "EconomicObjective",
    "EconomicRelationship",
    "EconomicVariable",
    "EncodedVariable",
    "KnowledgeGraph",
    "KnowledgeGraphEdge",
    "MethodologyPhase",
    "MethodologyReport",
    "KnowledgeGraphNode",
    "MathematicalTruthLayer",
    "NodeKind",
    "ObjectiveSpec",
    "ObjectiveWeight",
    "OptimizationCandidate",
    "OptimizationResult",
    "OpenClawOrchestrator",
    "PipelineRunSummary",
    "ClassicalReasoner",
    "MLReasoner",
    "QuantumReasoner",
    "ReasoningOutput",
    "ProtocolMethodologyPipeline",
    "ProtocolSpec",
    "Role",
    "SpecialistAgent",
    "TrustBoundary",
    "build_dependency_graph",
]
