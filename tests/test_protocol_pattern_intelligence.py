from __future__ import annotations

import json
from pathlib import Path

from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)
from quantum_economic_auditor.openclaw.agents.repository_context import RepositoryContext
from quantum_economic_auditor.pipeline.orchestrator import HalyxOrchestrator
from quantum_economic_auditor.semantic.protocol_pattern_engine import (
    ExpectedObservedComparator,
    ExpectedProtocolModelRegistry,
    ProtocolPatternRecognitionEngine,
)


def _sample_eir(protocol_name: str) -> EconomicIntermediateRepresentation:
    return EconomicIntermediateRepresentation(
        protocol_name=protocol_name,
        variables=[EconomicVariable(name="Liquidity", category="liquidity")],
        actions=[EconomicAction(name="Swap", kind="swap")],
        relationships=[EconomicRelationship(source="Liquidity", relation="depends_on", target="Swap")],
        invariants=[EconomicInvariant(name="Conservation", kind="conservation", expression="reserve_x * reserve_y = k")],
        objectives=[EconomicObjective(name="FeeRevenue", kind="profit", expression="fees", weight=1.0)],
    )


def test_pattern_recognition_identifies_amm_from_repository_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "raydium-like"
    (repo / "programs" / "amm").mkdir(parents=True)
    (repo / "programs" / "amm" / "swap.rs").write_text("pub fn swap() {}", encoding="utf-8")
    (repo / "programs" / "amm" / "pool.rs").write_text("pub struct Pool {}", encoding="utf-8")

    context = RepositoryContext(
        repository_path=repo,
        scope_summary="AMM swap, liquidity pool, and fee distribution",
        known_issues=[],
    )

    result = ProtocolPatternRecognitionEngine().classify(
        repository_path=repo,
        repository_context=context,
        eir=_sample_eir("raydium-like"),
    )

    assert result.pattern_id == "amm"
    assert result.confidence >= 0.35
    assert result.evidence


def test_expected_observed_comparison_reports_missing_expected_subsystems() -> None:
    expected_model = ExpectedProtocolModelRegistry().get("amm")
    comparison = ExpectedObservedComparator().compare(
        expected_model=expected_model,
        observed_subsystems=["Swap Mathematics", "Authority Model"],
    )

    assert "Pool Accounting" in comparison.missing_expected
    assert comparison.match_ratio < 1.0


def test_orchestrator_persists_pattern_and_expectation_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "amm-repo"
    (repo / "src").mkdir(parents=True)
    (repo / "README.md").write_text("AMM protocol with swap and pool accounting", encoding="utf-8")
    (repo / "src" / "pool.sol").write_text(
        "contract Pool { uint reserveX; uint reserveY; function swap(uint a) public {} }",
        encoding="utf-8",
    )

    orchestrator = HalyxOrchestrator(storage_dir=tmp_path)
    orchestrator.run(repository_path=repo, eir=_sample_eir("amm-repo"), program_scope="amm")

    payload = json.loads((tmp_path / "halyx_pipeline_result.json").read_text(encoding="utf-8"))
    assert "protocol_pattern" in payload
    assert "expected_protocol_model" in payload
    assert "expectation_graph" in payload
    assert "expected_vs_observed" in payload
    assert "semantic_dossiers" in payload
    assert payload["protocol_pattern"]["pattern_id"] in {"amm", "lending", "reserve_currency"}
