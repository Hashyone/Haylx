from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.consensus.engine import ConsensusEngine, FinalClassification
from quantum_economic_auditor.methodology.pipeline import ProtocolMethodologyPipeline
from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)
from quantum_economic_auditor.openclaw.agents.repository_context import RepositoryContext


def test_methodology_pipeline_builds_phase_reports_and_consensus() -> None:
    eir = EconomicIntermediateRepresentation(
        protocol_name="bridge-program",
        variables=[
            EconomicVariable(name="Collateral", category="collateral"),
            EconomicVariable(name="Debt", category="debt"),
        ],
        actions=[EconomicAction(name="Borrow", kind="borrow")],
        relationships=[
            EconomicRelationship(source="Collateral", relation="collateralizes", target="Borrow"),
            EconomicRelationship(source="Borrow", relation="updates", target="Debt"),
        ],
        invariants=[EconomicInvariant(name="Collateralization", kind="collateralization", expression="Collateral >= Debt")],
        objectives=[EconomicObjective(name="Profit", kind="profit", expression="Collateral - Debt", weight=1.0)],
    )
    context = RepositoryContext(
        repository_path=Path("/tmp/program-repo"),
        scope_summary="Bridge transfers and vault accounting.",
        known_issues=["Oracle staleness", "Relayer frontrun"],
    )

    pipeline = ProtocolMethodologyPipeline()
    report = pipeline.run(eir=eir, repository_context=context)

    assert report.phase_count >= 8
    assert any(phase.name == "phase0" for phase in report.phases)
    assert any(phase.name == "phase1" for phase in report.phases)
    assert any(phase.name == "phase2" for phase in report.phases)
    assert any(phase.name == "phase3" for phase in report.phases)
    assert any(phase.name == "phase4" for phase in report.phases)
    assert any(phase.name == "phase5" for phase in report.phases)
    assert any(phase.name == "phase6" for phase in report.phases)
    assert any(phase.name == "phase7" for phase in report.phases)
    assert any(phase.name == "phase7_5" for phase in report.phases)
    assert any(phase.name == "phase8" for phase in report.phases)
    assert report.overall_status == "ready"

    consensus = ConsensusEngine().evaluate(
        subsystem_id="bridge",
        hypothesis_id="hypothesis-1",
        classical_classification=FinalClassification.SURVIVES,
        ml_prior=0.82,
        quantum_output=0.79,
    )

    assert consensus.classical_classification == FinalClassification.SURVIVES
    assert consensus.agreement_level in {"strong_agreement", "partial_agreement", "disagreement"}
    assert consensus.research_priority >= 0.0
