from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)
from quantum_economic_auditor.pipeline.orchestrator import HalyxOrchestrator


def test_end_to_end_orchestrator_runs_context_methodology_and_consensus(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "README.md").write_text(
        "# Program\n\n## Scope\nBridge transfers and vault accounting.\n\n## Known Issues\n- Oracle staleness.\n",
        encoding="utf-8",
    )
    (repo_root / "src" / "bridge.py").write_text("def transfer():\n    return 'ok'\n", encoding="utf-8")

    eir = EconomicIntermediateRepresentation(
        protocol_name="bridge-program",
        variables=[EconomicVariable(name="Collateral", category="collateral")],
        actions=[EconomicAction(name="Borrow", kind="borrow")],
        relationships=[EconomicRelationship(source="Collateral", relation="collateralizes", target="Borrow")],
        invariants=[EconomicInvariant(name="Collateralization", kind="collateralization", expression="Collateral >= 0")],
        objectives=[EconomicObjective(name="Profit", kind="profit", expression="Collateral", weight=1.0)],
    )

    orchestrator = HalyxOrchestrator()
    result = orchestrator.run(repository_path=repo_root, eir=eir, program_scope="bridge")

    assert result["repository_context"].repository_path == repo_root
    assert result["methodology"].phase_count >= 3
    assert result["consensus"].classical_classification.value == "unknown"
    assert result["consensus"].research_priority >= 0.0

    payload = result["persistence"].read_text(encoding="utf-8")
    assert "evidence" in payload.lower()
    assert "equations" in payload.lower() or "economic_equations" in payload.lower()
