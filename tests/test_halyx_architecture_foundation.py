from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.consensus.engine import ConsensusEngine, FinalClassification
from quantum_economic_auditor.environment_orchestration.manager import EnvironmentOrchestrationManager
from quantum_economic_auditor.models.cpm import Actor, CanonicalProtocolModel, Role, TrustBoundary
from quantum_economic_auditor.models.evidence import AgentEvidence, ClaimSource, EvidencedClaim
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
from quantum_economic_auditor.models.truth_layer import MathematicalTruthLayer
from quantum_economic_auditor.openclaw.agents.repository_context import RepositoryContextAgent
from quantum_economic_auditor.openclaw.orchestrator import CognitiveTarget, OpenClawOrchestrator, SpecialistAgent
from quantum_economic_auditor.reasoning_engines.engines import ClassicalReasoner


def test_evidence_and_graph_models_capture_traceable_claims() -> None:
    claim = EvidencedClaim(
        id="claim-1",
        statement="The subsystem has a pause guard.",
        source=ClaimSource.CODE,
        source_reference="src/protocol.sol:42",
        confidence=0.94,
        verification_method="AST inspection",
        verified=True,
    )
    evidence = AgentEvidence(
        agent_name="architecture_reconstructor",
        subsystem_id="liquidation",
        claim=claim,
        supporting_references=["src/protocol.sol:42"],
        confidence="direct AST match",
    )

    node = KnowledgeGraphNode(id="liquidation", kind=NodeKind.SUBSYSTEM, label="Liquidation")
    edge = KnowledgeGraphEdge(source="liquidation", target="pause_guard", kind=EdgeKind.SHARED_INVARIANT)
    graph = KnowledgeGraph(nodes=[node], edges=[edge])

    assert evidence.claim.statement == "The subsystem has a pause guard."
    assert graph.get_node("liquidation").label == "Liquidation"
    assert graph.get_edge("liquidation", "pause_guard").kind == EdgeKind.SHARED_INVARIANT


def test_canonical_model_and_truth_layer_are_structured_for_reasoning() -> None:
    protocol = CanonicalProtocolModel(
        protocol_name="Olympus V3",
        assets=["gOHM"],
        liabilities=["debt"],
        actors=[Actor(name="governor", permissions=["pause"])],
        roles=[Role(name="governor", description="Governance authority")],
        trust_boundaries=[TrustBoundary(name="governance", description="Governance-controlled actions")],
        state_variables=["debt", "collateral"],
        actions=["borrow", "repay"],
        dependencies=["oracle"],
        accepted_tradeoffs=[],
        invariants=[],
    )

    truth_layer = MathematicalTruthLayer(
        subsystem_id="liquidation",
        transition_matrix_ref="matrix:liquidation",
        state_graph_ref="graph:liquidation",
        authority_graph_ref="authority:liquidation",
        constraint_graph_ref="constraints:liquidation",
        optimization_formulation="maximize profit",
        economic_equations=["debt' = debt + borrow - repay"],
    )

    assert protocol.protocol_name == "Olympus V3"
    assert truth_layer.subsystem_id == "liquidation"
    assert truth_layer.immutable is True


def test_environment_manager_reports_research_ready_when_prereqs_are_met() -> None:
    manager = EnvironmentOrchestrationManager(repository_path=Path("/tmp/olympus"))
    report = manager.evaluate_environment(
        dependencies_installed=True,
        compiler_configured=True,
        framework_installed=True,
        build_successful=True,
        tests_compiled=True,
        fork_available=True,
        knowledge_graph_generation_ready=True,
    )

    assert report.research_ready is True
    assert report.repository_imported is True


def test_openclaw_orchestrator_routes_evidence_from_specialist_agents() -> None:
    class DummyAgent(SpecialistAgent):
        name = "dummy_agent"

        def run(self, payload: dict[str, object]) -> list[AgentEvidence]:
            return [
                AgentEvidence(
                    agent_name=self.name,
                    subsystem_id=str(payload.get("subsystem_id")),
                    claim=EvidencedClaim(
                        id="claim-2",
                        statement="The subsystem is reachable.",
                        source=ClaimSource.CODE,
                        source_reference="src/example.sol",
                        confidence=0.9,
                        verification_method="manual trace",
                        verified=True,
                    ),
                    supporting_references=["src/example.sol"],
                    confidence="direct AST match",
                )
            ]

    orchestrator = OpenClawOrchestrator()
    orchestrator.register_agent(DummyAgent())
    evidence = orchestrator.run_agent("dummy_agent", {"subsystem_id": "vault"})

    assert len(evidence) == 1
    assert evidence[0].claim.statement == "The subsystem is reachable."


def test_openclaw_can_route_payloads_by_cognitive_target() -> None:
    orchestrator = OpenClawOrchestrator()
    payload = {
        "truth_layer": "truth",
        "constraint_graph": "constraints",
        "state_graph": "state",
        "verified_evidence": ["fact"],
        "historical_patterns": ["maker-like"],
        "protocol_family": "CDP Stablecoin",
        "reviewer_history": ["needs end-to-end evidence"],
        "accepted_findings": ["oracle manipulation"],
        "protocol_graph": "protocol",
        "semantic_dossiers": [{"name": "Collateral Accounting"}],
        "evidence_graph": "evidence",
        "expectation_graph": "expectation",
        "investigation_reports": [{"subsystem": "Collateral Accounting"}],
    }

    routed = orchestrator.route_payload_by_target(payload)

    assert routed[CognitiveTarget.CLASSICAL.value]["truth_layer"] == "truth"
    assert routed[CognitiveTarget.ML.value]["protocol_family"] == "CDP Stablecoin"
    assert routed[CognitiveTarget.QUANTUM.value]["expectation_graph"] == "expectation"


def test_repository_context_agent_separates_scope_from_known_issues(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(
        "# Program\n\n## Scope\nBridge transfers and vault accounting.\n\n## Known Issues\n- Oracle staleness.\n- Relayer frontrun.\n",
        encoding="utf-8",
    )

    context = RepositoryContextAgent().collect_repository_context(repository_path=repo, program_scope="bridge")

    assert "Bridge transfers and vault accounting." in context.scope_summary
    assert "Oracle staleness." in context.known_issues
    assert "Relayer frontrun." in context.known_issues
    assert all("Bridge transfers" not in issue for issue in context.known_issues)


def test_reasoning_engine_scores_structural_constraints_more_highly() -> None:
    truth_layer = MathematicalTruthLayer(
        subsystem_id="bridge",
        transition_matrix_ref="matrix:bridge",
        state_graph_ref="graph:bridge",
        authority_graph_ref="authority:bridge",
        constraint_graph_ref="constraints:bridge",
        optimization_formulation="maximize collateral while enforcing solvency",
        economic_equations=["collateral >= debt", "debt' = debt + borrow - repay"],
    )

    classical = ClassicalReasoner().reason(truth_layer)

    assert classical.score >= 0.5
    assert "constraint" in classical.summary.lower() or "optimization" in classical.summary.lower()


def test_evidence_graph_supports_traceable_reasoning() -> None:
    graph = EvidenceGraph(
        nodes=[
            EvidenceNode(id="e1", kind=EvidenceNodeKind.EVIDENCE, label="State transition", evidence_type="state_transition"),
            EvidenceNode(id="e2", kind=EvidenceNodeKind.CLAIM, label="Invariant preserved", evidence_type="invariant"),
        ],
        edges=[EvidenceEdge(source="e1", target="e2", kind=EvidenceEdgeKind.SUPPORTS)],
    )

    assert graph.get_node("e1").kind == EvidenceNodeKind.EVIDENCE
    assert graph.get_edge("e1", "e2").kind == EvidenceEdgeKind.SUPPORTS


def test_consensus_engine_detects_conflicting_signals_as_disagreement() -> None:
    consensus = ConsensusEngine().evaluate(
        subsystem_id="bridge",
        hypothesis_id="bridge-hypothesis",
        classical_classification=FinalClassification.SURVIVES,
        ml_prior=0.2,
        quantum_output=0.8,
    )

    assert consensus.agreement_level == "disagreement"


def test_reasoning_engine_incorporates_scope_context_and_known_issues() -> None:
    truth_layer = MathematicalTruthLayer(
        subsystem_id="bridge",
        transition_matrix_ref="matrix:bridge",
        state_graph_ref="graph:bridge",
        authority_graph_ref="authority:bridge",
        constraint_graph_ref="constraints:bridge",
        optimization_formulation="maximize collateral while enforcing solvency",
        economic_equations=["collateral >= debt", "debt' = debt + borrow - repay"],
        scope_context="Bridge transfers and vault accounting",
        known_issues=["Oracle staleness", "Relayer frontrun"],
        variable_names=["Collateral", "Debt"],
        objective_expressions=["maximize collateral"],
        evidence_summary="Bridge protocol with oracle and relayer risk",
    )

    classical = ClassicalReasoner().reason(truth_layer)

    assert "oracle" in classical.summary.lower() or "issue" in classical.summary.lower()
    assert classical.score < 0.9
