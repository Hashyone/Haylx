from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from quantum_economic_auditor.models.eir import EconomicIntermediateRepresentation
from quantum_economic_auditor.models.graph import NodeKind
from quantum_economic_auditor.pipeline.orchestrator import HalyxOrchestrator
from quantum_economic_auditor.reasoning_engines.engines import ReasoningOutput
from quantum_economic_auditor.semantic.subsystem_engine import (
    EvidenceReference,
    SubsystemDiscoveryEngine,
    SubsystemReconstructionEngine,
)


def test_subsystem_discovery_produces_prioritized_audit_queue(tmp_path: Path) -> None:
    repo_root = tmp_path / "subsystem-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Vault.sol").write_text(
        """
        contract Vault {
            address public owner;
            uint public collateral;
            uint public debt;

            function deposit(uint amount) public {
                collateral += amount;
            }

            function borrow(uint amount) public {
                debt += amount;
            }
        }
        """,
        encoding="utf-8",
    )

    engine = SubsystemDiscoveryEngine()
    plan = engine.discover(repository_path=repo_root)

    assert plan.ordered_queue
    assert any(subsystem.name == "Treasury" for subsystem in plan.subsystems)
    assert any(subsystem.name == "Vault" for subsystem in plan.subsystems)
    assert plan.ordered_queue[0].priority_score >= plan.ordered_queue[-1].priority_score


def test_subsystem_reconstruction_builds_state_accounting_and_invariants(tmp_path: Path) -> None:
    repo_root = tmp_path / "subsystem-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Vault.sol").write_text(
        """
        contract Vault {
            address public owner;
            uint public collateral;
            uint public debt;

            function deposit(uint amount) public {
                collateral += amount;
            }

            function borrow(uint amount) public {
                debt += amount;
            }
        }
        """,
        encoding="utf-8",
    )

    discovery_engine = SubsystemDiscoveryEngine()
    plan = discovery_engine.discover(repository_path=repo_root)
    reconstruction_engine = SubsystemReconstructionEngine()
    result = reconstruction_engine.reconstruct(repository_path=repo_root, audit_plan=plan)

    assert result.subsystems
    treasury = next(subsystem for subsystem in result.subsystems if subsystem.name == "Treasury")
    assert treasury.identity is not None
    assert treasury.contract_membership is not None
    assert treasury.contract_membership.primary_contracts
    assert treasury.state_model is not None
    assert treasury.state_machine.states
    assert treasury.state_machine.transitions
    assert treasury.accounting_model is not None
    assert treasury.economic_model is not None
    assert treasury.permission_model is not None
    assert treasury.permission_model.permission_edges
    assert treasury.mathematical_model is not None
    assert treasury.invariants
    assert treasury.report is not None
    assert treasury.report.purpose


def test_subsystem_reconstruction_builds_semantic_subsystem_model(tmp_path: Path) -> None:
    repo_root = tmp_path / "subsystem-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "README.md").write_text(
        "# Treasury\n\nThe treasury manages reserve balances and withdrawals.\n",
        encoding="utf-8",
    )
    (repo_root / "src" / "Treasury.sol").write_text(
        """
        contract Treasury {
            uint256 public reserveBalance;

            function deposit(uint256 amount) public {
                reserveBalance += amount;
            }

            function withdrawReserves(uint256 amount) public {
                reserveBalance -= amount;
            }
        }
        """,
        encoding="utf-8",
    )
    (repo_root / "src" / "Vault.sol").write_text(
        """
        contract Vault {
            uint256 public collateral;
            uint256 public debt;

            function borrow(uint256 amount) public {
                debt += amount;
            }
        }
        """,
        encoding="utf-8",
    )

    discovery_engine = SubsystemDiscoveryEngine()
    plan = discovery_engine.discover(repository_path=repo_root)
    reconstruction_engine = SubsystemReconstructionEngine()
    result = reconstruction_engine.reconstruct(repository_path=repo_root, audit_plan=plan)

    treasury = next(subsystem for subsystem in result.subsystems if subsystem.name == "Treasury")
    assert len(treasury.invariants) >= 2
    assert treasury.dependency_model.dependency_edges
    assert treasury.economic_model is not None
    assert treasury.economic_model.assets_entering
    assert treasury.economic_model.value_conservation
    assert treasury.trust_model.external_dependencies


def test_subsystem_reconstruction_attaches_repository_evidence(tmp_path: Path) -> None:
    repo_root = tmp_path / "subsystem-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "README.md").write_text(
        "# Treasury\n\nThe treasury manages reserve balances and withdrawals.\n",
        encoding="utf-8",
    )
    (repo_root / "src" / "Treasury.sol").write_text(
        """
        contract Treasury {
            uint256 public reserveBalance;

            function deposit(uint256 amount) public {
                reserveBalance += amount;
            }

            function withdrawReserves(uint256 amount) public {
                reserveBalance -= amount;
            }
        }
        """,
        encoding="utf-8",
    )

    discovery_engine = SubsystemDiscoveryEngine()
    plan = discovery_engine.discover(repository_path=repo_root)
    reconstruction_engine = SubsystemReconstructionEngine()
    result = reconstruction_engine.reconstruct(repository_path=repo_root, audit_plan=plan)

    treasury = next(subsystem for subsystem in result.subsystems if subsystem.name == "Treasury")
    assert treasury.identity is not None
    assert treasury.identity.evidence
    assert treasury.contract_membership is not None
    assert treasury.contract_membership.evidence
    assert treasury.state_machine.transitions
    assert treasury.state_machine.transitions[0].evidence
    assert treasury.invariants
    assert treasury.invariants[0].evidence
    assert treasury.invariants[0].evidence[0].source_type == "contract"
    assert isinstance(treasury.invariants[0].evidence[0], EvidenceReference)


def test_subsystem_reconstruction_uses_repository_specific_contract_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "olympus-style-repo"
    (repo_root / "src" / "modules" / "TRSRY").mkdir(parents=True)
    (repo_root / "src" / "policies").mkdir(parents=True)
    (repo_root / "src" / "modules" / "TRSRY" / "OlympusTreasury.sol").write_text(
        """
        contract OlympusTreasury {
            uint256 public reserveBalance;

            function withdrawReserves(uint256 amount) public {
                reserveBalance -= amount;
            }
        }
        """,
        encoding="utf-8",
    )
    (repo_root / "src" / "policies" / "VohmVault.sol").write_text(
        """
        contract VohmVault {
            uint256 public collateral;
            uint256 public debt;

            function borrow(uint256 amount) public {
                debt += amount;
            }
        }
        """,
        encoding="utf-8",
    )

    discovery_engine = SubsystemDiscoveryEngine()
    plan = discovery_engine.discover(repository_path=repo_root)
    reconstruction_engine = SubsystemReconstructionEngine()
    result = reconstruction_engine.reconstruct(repository_path=repo_root, audit_plan=plan)

    treasury = next(subsystem for subsystem in result.subsystems if subsystem.name == "Treasury")
    evidence = next(
        (ref for ref in treasury.identity.evidence if ref.repository_file == "src/modules/TRSRY/OlympusTreasury.sol"),
        None,
    )
    assert evidence is not None
    assert evidence.contract == "OlympusTreasury"


def test_subsystem_reconstruction_captures_provenance_and_transition_semantics(tmp_path: Path) -> None:
    repo_root = tmp_path / "provenance-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Treasury.sol").write_text(
        """
        contract Treasury {
            uint256 public reserveBalance;

            function deposit(uint256 amount) public {
                reserveBalance += amount;
            }

            function withdrawReserves(uint256 amount) public {
                reserveBalance -= amount;
            }
        }
        """,
        encoding="utf-8",
    )

    discovery_engine = SubsystemDiscoveryEngine()
    plan = discovery_engine.discover(repository_path=repo_root)
    reconstruction_engine = SubsystemReconstructionEngine()
    result = reconstruction_engine.reconstruct(repository_path=repo_root, audit_plan=plan)

    treasury = next(subsystem for subsystem in result.subsystems if subsystem.name == "Treasury")
    invariant = treasury.invariants[0]
    assert invariant.origin == "code_inference"
    assert invariant.supporting_artifacts
    assert invariant.evidence_strength >= 0.0
    assert treasury.state_machine.transitions[0].provenance is not None
    assert treasury.state_machine.transitions[0].provenance.function == "deposit"
    assert treasury.state_machine.transitions[0].provenance.storage_variables


def test_subsystem_reconstruction_collects_rich_implementation_traces(tmp_path: Path) -> None:
    repo_root = tmp_path / "trace-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Treasury.sol").write_text(
        """
        interface ITreasury {
            function deposit(uint256 amount) external;
        }

        contract Treasury is ITreasury {
            uint256 public reserveBalance;
            uint256 internal constant MAX_WITHDRAW = 1000;

            event Deposit(address indexed user, uint256 amount);
            error InsufficientFunds();
            struct Allocation { uint256 amount; address recipient; }
            enum Status { Active, Paused }

            modifier onlyOwner() { _; }

            function deposit(uint256 amount) public onlyOwner {
                reserveBalance += amount;
                emit Deposit(msg.sender, amount);
            }

            function withdrawReserves(uint256 amount) public onlyOwner {
                if (reserveBalance < amount) revert InsufficientFunds();
                reserveBalance -= amount;
            }
        }
        """,
        encoding="utf-8",
    )

    discovery_engine = SubsystemDiscoveryEngine()
    plan = discovery_engine.discover(repository_path=repo_root)
    reconstruction_engine = SubsystemReconstructionEngine()
    result = reconstruction_engine.reconstruct(repository_path=repo_root, audit_plan=plan)

    treasury = next(subsystem for subsystem in result.subsystems if subsystem.name == "Treasury")
    trace = treasury.implementation_traces[0]
    assert trace.modifiers == ["onlyOwner"]
    assert "MAX_WITHDRAW" in trace.constants
    assert "Deposit" in trace.events
    assert "InsufficientFunds" in trace.errors
    assert "Allocation" in trace.structs
    assert "Status" in trace.enums
    assert "ITreasury" in trace.interfaces
    assert trace.call_graph
    assert any(node.kind == NodeKind.IMPLEMENTATION_TRACE for node in treasury.semantic_graph.nodes)


def test_orchestrator_persists_richer_subsystem_dossiers(tmp_path: Path) -> None:
    repo_root = tmp_path / "orchestrator-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "Treasury.sol").write_text(
        """
        contract Treasury {
            uint256 public reserveBalance;

            function deposit(uint256 amount) public {
                reserveBalance += amount;
            }
        }
        """,
        encoding="utf-8",
    )

    orchestrator = HalyxOrchestrator(storage_dir=tmp_path / "out")
    orchestrator.repository_agent.collect_repository_context = lambda **kwargs: SimpleNamespace(
        repository_path=repo_root,
        scope_summary="treasury subsystem",
        known_issues=[],
        markdown_files=[],
        source_files=["src/Treasury.sol"],
    )
    orchestrator.methodology_pipeline.run = lambda **kwargs: SimpleNamespace(
        phase_count=1,
        overall_status="ready",
        phases=[SimpleNamespace(name="phase0", status=SimpleNamespace(value="ready"), summary="ok")],
    )
    orchestrator.classical_reasoner.reason = lambda truth_layer: ReasoningOutput(score=0.95, summary="classical ok", role="classical", artifacts=["a"], verdicts=[])
    orchestrator.ml_reasoner.reason = lambda truth_layer: ReasoningOutput(score=0.9, summary="ml ok", role="ml", artifacts=["b"])
    orchestrator.quantum_reasoner.reason = lambda truth_layer: ReasoningOutput(score=0.87, summary="quantum ok", role="quantum", artifacts=["c"])
    orchestrator.consensus_engine.evaluate = lambda **kwargs: SimpleNamespace(classical_classification=SimpleNamespace(value="survives"), research_priority=0.95)

    result = orchestrator.run(
        repository_path=repo_root,
        eir=EconomicIntermediateRepresentation(protocol_name="demo"),
        program_scope="demo",
    )

    payload = json.loads((result["persistence"]).read_text(encoding="utf-8"))
    reconstructions = payload["subsystem_plan"]["reconstructions"]
    assert reconstructions
    assert reconstructions[0]["implementation_traces"]
    assert reconstructions[0]["guarantees"]
    assert reconstructions[0]["evidence_quality"]
