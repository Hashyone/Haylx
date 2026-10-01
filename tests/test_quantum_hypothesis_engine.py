from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.parser.repository_loader import load_repository
from quantum_economic_auditor.semantic.quantum_hypothesis_engine import QuantumHypothesisEngine


def _write_contract(repo: Path, relative_path: str, content: str) -> None:
    file_path = repo / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def test_quantum_hypothesis_engine_generates_executable_hypotheses(tmp_path: Path) -> None:
    repo = tmp_path / "proto"
    _write_contract(
        repo,
        "src/Pool.sol",
        """
        contract Pool {
            function swap(uint256 amountIn) external {}
            function flashLoan(uint256 amount, address borrower) external {}
            function collectFee(address to) external {}
            function withdraw(uint256 shares) external {}
        }
        """,
    )
    _write_contract(
        repo,
        "src/Vault.sol",
        """
        contract Vault {
            function deposit(uint256 amount) external {}
            function redeem(uint256 shares) external {}
            function setOracle(address oracle) external {}
        }
        """,
    )

    model = load_repository(str(repo))
    engine = QuantumHypothesisEngine(max_qubits=6, max_hypotheses=3)

    hypotheses = engine.generate(
        repository_model=model,
        pattern_label="AMM",
        pattern_id="amm",
        existing_hypothesis_ids=[],
    )

    assert hypotheses
    assert all(h.hypothesis_id.startswith("H-QAMM-") for h in hypotheses)

    first = hypotheses[0]
    assert first.expected_attack_sequence
    assert all(step.startswith("attacker calls ") for step in first.expected_attack_sequence)
    assert first.required_actors
    assert first.required_capital > 0
    assert first.predicted_attacker_profit > 0
    assert "quantum_superposition_path_search" in first.threat_vectors


def test_quantum_hypothesis_engine_avoids_hypothesis_id_collisions(tmp_path: Path) -> None:
    repo = tmp_path / "proto"
    _write_contract(
        repo,
        "src/Bridge.sol",
        """
        contract Bridge {
            function lock(address token, uint256 amount) external {}
            function relay(bytes calldata payload) external {}
            function unlock(address token, uint256 amount) external {}
        }
        """,
    )

    model = load_repository(str(repo))
    engine = QuantumHypothesisEngine(max_qubits=4, max_hypotheses=2)

    hypotheses = engine.generate(
        repository_model=model,
        pattern_label="Cross-Chain Bridge",
        pattern_id="bridge",
        existing_hypothesis_ids=["H-QBRI-001"],
    )

    assert hypotheses
    assert all(h.hypothesis_id != "H-QBRI-001" for h in hypotheses)
