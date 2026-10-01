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


def test_orchestrator_persists_results_and_validates_pipeline(tmp_path: Path) -> None:
    repo_root = tmp_path / "persisted-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "README.md").write_text(
        "# Program\n\n## Scope\nBridge transfers and vault accounting.\n",
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

    orchestrator = HalyxOrchestrator(storage_dir=tmp_path)
    result = orchestrator.run(repository_path=repo_root, eir=eir, program_scope="bridge")

    assert result["persistence"].exists()
    assert result["validation"].is_valid is True
    assert result["validation"].issues == []
