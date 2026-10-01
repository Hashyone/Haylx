from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.parser.repository_loader import load_repository
from quantum_economic_auditor.semantic.tutor_engine import TutorResearchNote
from quantum_economic_auditor.semantic.verification_engine import DeterministicVerificationEngine


def test_deterministic_verification_engine_verifies_with_matching_source(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Pool.sol").write_text(
        """
        contract Pool {
            uint256 public feeAccumulator;
            function claimFees() external {}
            function updateOracle() external {}
        }
        """,
        encoding="utf-8",
    )

    repo = load_repository(str(repo_root))
    note = TutorResearchNote(
        concept="Fee Distribution",
        subsystem="Fee Distribution",
        protocol_pattern="AMM",
        summary="Fee accumulator and claim fees pathway should be validated.",
        candidate_explanations=["fees accrue per swap"],
        evidence_targets=["feeAccumulator", "claimFees", "updateOracle"],
    )

    report = DeterministicVerificationEngine().verify_tutor_note(
        note=note,
        repository_model=repo,
        expected_guarantees=["fee accumulator conservation"],
    )

    assert report.verified is True
    assert report.verification_score >= 0.55
    assert report.matched_files


def test_deterministic_verification_engine_rejects_when_evidence_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Vault.sol").write_text("contract Vault { uint256 public collateral; }", encoding="utf-8")

    repo = load_repository(str(repo_root))
    note = TutorResearchNote(
        concept="Oracle Dependencies",
        subsystem="Oracle Dependencies",
        protocol_pattern="Lending",
        summary="Uses freshness windows and heartbeat checks.",
        evidence_targets=["priceOracle", "heartbeat", "stalePrice"],
    )

    report = DeterministicVerificationEngine().verify_tutor_note(
        note=note,
        repository_model=repo,
        expected_guarantees=["oracle freshness bounded"],
    )

    assert report.verified is False
    assert report.verification_score < 0.55
    assert report.missing_terms


def test_deterministic_verification_engine_scans_non_solidity_sources(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "oracle.rs").write_text(
        """
        pub fn update_oracle(price_oracle: &str) {
            let heartbeat_window = 30;
            let stale_price_guard = true;
            println!("{} {} {}", price_oracle, heartbeat_window, stale_price_guard);
        }
        """,
        encoding="utf-8",
    )

    repo = load_repository(str(repo_root))
    note = TutorResearchNote(
        concept="Oracle Dependencies",
        subsystem="Oracle Dependencies",
        protocol_pattern="AMM",
        summary="price oracle heartbeat and stale price guard should be checked",
        evidence_targets=["price_oracle", "heartbeat_window", "stale_price_guard"],
    )

    report = DeterministicVerificationEngine().verify_tutor_note(
        note=note,
        repository_model=repo,
        expected_guarantees=["oracle freshness bounded"],
    )

    assert report.verification_score > 0.0
    assert report.matched_files