from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.pipeline.orchestrator import HalyxOrchestrator
from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)


def test_every_hypothesis_receives_an_execution_case_regardless_of_sequence_validity(tmp_path: Path) -> None:
    """Every hypothesis must have an execution_case; no hypothesis may silently fall through to untested."""
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Core.sol").write_text("pragma solidity ^0.8.13; contract Core {}", encoding="utf-8")
    (repo_root / "README.md").write_text("# repo\n", encoding="utf-8")

    eir = EconomicIntermediateRepresentation(
        protocol_name="linkage-test",
        variables=[EconomicVariable(name="Collateral", category="collateral")],
        actions=[EconomicAction(name="Borrow", kind="borrow")],
        relationships=[EconomicRelationship(source="Collateral", relation="collateralizes", target="Borrow")],
        invariants=[EconomicInvariant(name="Collateralization", kind="collateralization", expression="Collateral >= 0")],
        objectives=[EconomicObjective(name="Profit", kind="profit", expression="Collateral", weight=1.0)],
    )

    orchestrator = HalyxOrchestrator(storage_dir=tmp_path / "out")
    result = orchestrator.run(repository_path=repo_root, eir=eir, program_scope="linkage")

    ledger = result.get("hypothesis_evidence_ledger", [])
    assert ledger, "expected hypothesis evidence ledger entries"

    # Every ledger entry must have a populated execution_case (no silent gaps).
    for entry in ledger:
        assert "execution_case" in entry, f"hypothesis {entry.get('hypothesis_id')} missing execution_case"
        case_status = entry["execution_case"]["status"]
        assert case_status, f"hypothesis {entry.get('hypothesis_id')} has empty case status"

    # Every entry must have a populated stage evidence object.
    evidence_objects = result.get("hypothesis_evidence_objects", [])
    assert len(evidence_objects) == len(ledger), "evidence object count must match ledger count"
    for obj in evidence_objects:
        assert obj["current_stage"] != "", "evidence object missing current_stage"
        assert obj["verdict"] != "", "evidence object missing verdict"
        assert len(obj["stage_history"]) >= 1, "evidence object missing stage_history"

    # Consensus must never be SURVIVES when no behavioral confirmation exists.
    consensus = result["consensus"].classical_classification.value
    falsification = result.get("falsification_execution", {})
    any_confirmed = any(
        c.get("status") in {"execution_proof_criteria_satisfied"}
        for c in falsification.get("cases", [])
        if isinstance(c, dict)
    )
    if not any_confirmed:
        assert consensus != "survives", f"consensus is 'survives' without behavioral proof (got {consensus})"
