from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.semantic.semantics_engine import ProtocolSemanticsEngine


def test_semantics_engine_reconstructs_accounting_economics_and_transitions(tmp_path: Path) -> None:
    repo_root = tmp_path / "semantic-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Vault.sol").write_text(
        """
        contract Vault {
            address public owner;
            uint public collateral;
            uint public debt;
            mapping(address => uint) balances;

            function deposit(uint amount) public {
                balances[msg.sender] += amount;
                collateral += amount;
            }

            function borrow(uint amount) public {
                debt += amount;
            }
        }
        """,
        encoding="utf-8",
    )

    engine = ProtocolSemanticsEngine()
    semantics = engine.reconstruct(repository_path=repo_root)

    assert any(entity.semantic_type == "vault" for entity in semantics.entities)
    assert semantics.accounting_systems
    assert semantics.economic_variables
    assert semantics.state_transitions
    assert semantics.permissions
    assert semantics.trust_boundaries
    assert semantics.invariants
    assert semantics.semantic_graph.nodes
