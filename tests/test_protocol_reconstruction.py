from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.semantic.protocol_reconstruction import ProtocolReconstructionEngine


def test_protocol_reconstruction_extracts_entities_invariants_and_graph(tmp_path: Path) -> None:
    repo_root = tmp_path / "protocol-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Vault.sol").write_text(
        """
        contract Vault {
            address public owner;
            mapping(address => uint) public balances;
            uint public debt;
            uint public collateral;

            modifier onlyOwner() {
                require(msg.sender == owner);
                _;
            }

            function deposit(uint amount) public {
                balances[msg.sender] += amount;
                collateral += amount;
            }

            function borrow(uint amount) public onlyOwner {
                debt += amount;
            }
        }
        """,
        encoding="utf-8",
    )

    engine = ProtocolReconstructionEngine()
    result = engine.reconstruct(repository_path=repo_root)

    assert any(entity.kind == "contract" and entity.name == "Vault" for entity in result.entities)
    assert any(entity.kind == "actor" and entity.name == "owner" for entity in result.entities)
    assert any(entity.kind == "permission" for entity in result.entities)
    assert any(entity.kind == "transition" for entity in result.entities)
    assert any("collateral" in invariant.expression.lower() or "debt" in invariant.expression.lower() for invariant in result.invariants)
    assert result.protocol_graph.nodes
    assert result.protocol_graph.edges
