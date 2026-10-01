from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from quantum_economic_auditor.semantic.falsification_engine import FalsificationCase, FalsificationExecutionEngine


def test_falsification_engine_skips_non_foundry_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    report = FalsificationExecutionEngine(which=lambda _: None).execute(
        repository_path=repo,
        hypothesis_ledger=[{"hypothesis_id": "hyp:a", "status": "unresolved"}],
    )

    assert report.executed is False
    assert report.mode == "non_foundry"
    assert report.fork_rpc_source is None
    assert report.reason


def test_falsification_engine_requires_explorer_key_in_strict_verified_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HALYX_REQUIRE_VERIFIED_TARGETS", "1")
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.delenv("ETHERSCAN_API_KEY_ALT", raising=False)
    monkeypatch.delenv("ETHERSCAN_API_TOKEN", raising=False)

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Pool.sol").write_text("contract Pool {}", encoding="utf-8")

    report = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example").execute(
        repository_path=repo,
        hypothesis_ledger=[{"hypothesis_id": "hyp:a", "status": "unresolved"}],
        chain="ethereum",
    )

    assert report.executed is False
    assert report.mode == "foundry_missing_explorer_key"
    assert "no Etherscan API key" in (report.reason or "")


def test_falsification_engine_generates_and_parses_foundry_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Pool.sol").write_text(
        "contract Pool { function swap(uint256 amount) external {} }",
        encoding="utf-8",
    )

    def fake_runner(*args, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="[FAIL. Reason: hyp unresolved] test_HalyxHypothesis_hyp_a()\n[PASS] test_HalyxHypothesis_hyp_b()",
            stderr="",
        )

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[
            {"hypothesis_id": "hyp:a", "status": "unresolved", "evidence_needed": ["swap path conservation"]},
            {"hypothesis_id": "hyp:b", "status": "provisionally_supported", "evidence_needed": ["liquidity solvency"]},
        ],
    )

    assert report.executed is True
    assert report.mode == "foundry_isolated"
    assert report.generated_test_file
    assert report.harness_dir
    assert report.command
    assert report.fork_rpc_source == "environment"
    foundry_toml = Path(report.harness_dir) / "foundry.toml"
    assert "via_ir = true" in foundry_toml.read_text(encoding="utf-8")
    statuses = {case.hypothesis_id: case.status for case in report.cases}
    assert statuses["hyp:a"] == "falsification_triggered"
    assert statuses["hyp:b"] == "supported_by_execution"
    hyp_a = next(case for case in report.cases if case.hypothesis_id == "hyp:a")
    assert hyp_a.target_contracts
    assert hyp_a.target_functions
    assert hyp_a.target_invariants


def test_falsification_engine_marks_toolchain_blocked_runs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Pool.sol").write_text("contract Pool {}", encoding="utf-8")

    def fake_runner(*args, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Encountered invalid solc version in test/Foo.t.sol",
        )

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[
            {"hypothesis_id": "hyp:a", "status": "unresolved"},
        ],
    )

    assert report.executed is True
    assert report.reason is not None
    assert report.fork_rpc_source == "environment"
    assert report.cases[0].status == "execution_blocked_toolchain"


def test_falsification_engine_uses_mevblocker_fallback_when_fork_rpc_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HALYX_FORK_RPC_URL", raising=False)
    monkeypatch.delenv("ETH_RPC_URL", raising=False)
    monkeypatch.delenv("RPC_URL", raising=False)

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Pool.sol").write_text("contract Pool {}", encoding="utf-8")

    captured_env = {}

    def fake_runner(*args, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return SimpleNamespace(returncode=0, stdout="[PASS] test_HalyxHypothesis_hyp_a()", stderr="")

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url=None)
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[{"hypothesis_id": "hyp:a", "status": "unresolved"}],
    )

    assert report.executed is True
    assert report.mode == "foundry_isolated"
    assert report.fork_rpc_source == "fallback:mevblocker"
    assert captured_env.get("HALYX_FORK_RPC_URL") == "https://rpc.mevblocker.io"


def test_falsification_engine_discovers_fork_rpc_from_env_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Pool.sol").write_text("contract Pool {}", encoding="utf-8")
    (repo / ".env").write_text("FORK_TEST_RPC_URL=https://rpc.from.env\n", encoding="utf-8")

    captured_env = {}

    def fake_runner(*args, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return SimpleNamespace(returncode=0, stdout="[PASS] test_HalyxHypothesis_hyp_a()", stderr="")

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url=None)
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[{"hypothesis_id": "hyp:a", "status": "supported"}],
    )

    assert report.executed is True
    assert report.mode == "foundry_isolated"
    assert report.fork_rpc_source == "env:FORK_TEST_RPC_URL"
    assert captured_env.get("HALYX_FORK_RPC_URL") == "https://rpc.from.env"


def test_falsification_engine_discovers_fork_rpc_from_foundry_template(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HALYX_FORK_RPC_URL", raising=False)
    monkeypatch.delenv("ETH_RPC_URL", raising=False)
    monkeypatch.delenv("RPC_URL", raising=False)

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Pool.sol").write_text("contract Pool {}", encoding="utf-8")
    (repo / "foundry.toml").write_text(
        "[rpc_endpoints]\nmainnet = { endpoint = \"https://eth-mainnet.g.alchemy.com/v2/${ALCHEMY_API_KEY}\" }\n",
        encoding="utf-8",
    )
    (repo / ".env").write_text("ALCHEMY_API_KEY=abc123\n", encoding="utf-8")

    captured_env = {}

    def fake_runner(*args, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return SimpleNamespace(returncode=0, stdout="[PASS] test_HalyxHypothesis_hyp_a()", stderr="")

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url=None)
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[{"hypothesis_id": "hyp:a", "status": "supported"}],
    )

    assert report.executed is True
    assert report.mode == "foundry_isolated"
    assert report.fork_rpc_source == "foundry.toml:rpc_endpoints.mainnet"
    assert captured_env.get("HALYX_FORK_RPC_URL") == "https://eth-mainnet.g.alchemy.com/v2/abc123"


def test_falsification_engine_renders_behavioral_sequence_when_steps_exist(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Vault.sol").write_text(
        "contract Vault { function deposit() external {} function redeem() external {} }",
        encoding="utf-8",
    )

    def fake_runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="[PASS] test_HalyxHypothesis_hyp_seq()", stderr="")

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[
            {
                "hypothesis_id": "hyp:seq",
                "status": "provisionally_supported",
                "subsystem": "Vault",
                    "execution_case": {
                        "target_addresses": ["0x0000000000000000000000000000000000000001"],
                    },
                "execution_sequence": {
                    "sequence_id": "seq:hyp_seq",
                    "economic_consequence": "leakage",
                    "violated_invariants": ["INV-SHARE-RATE"],
                    "ordered_steps": [
                        {"index": 1, "handler": "deposit", "caller": "external_user"},
                        {"index": 2, "handler": "redeem", "caller": "external_user"},
                    ],
                },
            }
        ],
    )

    generated = Path(str(report.generated_test_file or ""))
    assert generated.exists()
    source = generated.read_text(encoding="utf-8")
    assert "HALYX_TEST_COMPLETED:hyp:seq" in source
    assert "vm.prank(attacker);" in source
    assert "pathProgress" in source
    assert "HalyxConsole.logString" in source
    assert "forge-std/console2.sol" not in source
    assert (Path(str(report.harness_dir)) / "src" / "HalyxConsole.sol").exists()
    assert "emit log_string" not in source


def test_falsification_engine_treats_synthetic_confirmation_marker_as_metadata() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:seq",
            test_name="test_HalyxHypothesis_hyp_seq",
            status="unresolved",
            rationale="",
            should_fail=True,
            execution_sequence_id="seq:hyp_seq",
            execution_steps=[{"index": 1, "handler": "deposit", "caller": "external_user"}],
            economic_consequence="leakage",
            violated_invariants=["INV-SHARE-RATE"],
            target_contracts=[],
            target_addresses=[],
            target_functions=[],
            target_invariants=[],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_TEST_COMPLETED:hyp:seq] test_HalyxHypothesis_hyp_seq()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "falsification_triggered"


def test_falsification_engine_skips_sequence_render_without_target_addresses() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    source = engine._render_test_contract(
        [
            FalsificationCase(
                hypothesis_id="hyp:noaddr",
                test_name="test_HalyxHypothesis_hyp_noaddr",
                status="unresolved",
                rationale="",
                should_fail=True,
                execution_steps=[{"index": 1, "handler": "deposit", "caller": "external_user"}],
                target_contracts=["Vault"],
                target_addresses=[],
                target_functions=["deposit()"],
                target_invariants=["INV-VAULT"],
            )
        ],
        fork_block_number=None,
    )

    assert "address primaryTarget = primaryTarget;" not in source


def test_falsification_engine_detects_dvdefi_unstoppable_native_mode(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Vault.sol").write_text("contract Vault {}", encoding="utf-8")
    (repo / "test" / "unstoppable").mkdir(parents=True)
    (repo / "test" / "unstoppable" / "Unstoppable.t.sol").write_text("contract UnstoppableChallenge {}", encoding="utf-8")

    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    case = FalsificationCase(
        hypothesis_id="H-AMM-001",
        test_name="test_HalyxHypothesis_H_AMM_001",
        status="unresolved",
        rationale="",
        should_fail=True,
        target_contracts=["UnstoppableVault"],
        target_functions=["maxFlashLoan(address)"],
    )

    assert engine._can_use_dvdefi_unstoppable_native_mode(repository_path=repo, cases=[case]) is True


def test_falsification_engine_executes_dvdefi_unstoppable_native_mode(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Vault.sol").write_text("contract Vault {}", encoding="utf-8")
    (repo / "test" / "unstoppable").mkdir(parents=True)
    (repo / "test" / "unstoppable" / "Unstoppable.t.sol").write_text("contract UnstoppableChallenge {}", encoding="utf-8")

    def fake_runner(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(
                [
                    "[PASS] test_HalyxHypothesis_H_AMM_001()",
                    "HALYX_TEST_COMPLETED:H-AMM-001",
                ]
            ),
            stderr="",
        )

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[
            {
                "hypothesis_id": "H-AMM-001",
                "status": "unresolved",
                "execution_case": {
                    "target_contracts": ["UnstoppableVault"],
                    "target_functions": ["maxFlashLoan(address)"],
                },
            }
        ],
    )

    assert report.mode == "foundry_repo_native_unstoppable"
    assert report.executed is True
    assert report.return_code == 0
    assert report.generated_test_file and Path(report.generated_test_file).exists()
    assert report.cases[0].status == "supported_by_execution"


def test_falsification_engine_omits_path_progress_gate_without_execution_steps() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    source = engine._render_test_contract(
        [
            FalsificationCase(
                hypothesis_id="hyp:plain",
                test_name="test_HalyxHypothesis_hyp_plain",
                status="unresolved",
                rationale="",
                should_fail=True,
                target_contracts=["Vault"],
                target_addresses=["0x0000000000000000000000000000000000000001"],
                target_functions=["deposit()"],
                target_invariants=["INV-VAULT"],
            )
        ],
        fork_block_number=None,
    )

    assert "no executable interaction path reached target functions" not in source
    assert "HALYX_INCONCLUSIVE_SYNTHETIC:hyp:plain no post-state or economic movement observed" in source


def test_falsification_engine_marks_synthetic_inconclusive() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:synthetic",
            test_name="test_HalyxHypothesis_hyp_synthetic",
            status="unresolved",
            rationale="",
            should_fail=True,
            execution_sequence_id=None,
            execution_steps=[],
            economic_consequence="",
            violated_invariants=[],
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["deposit()"],
            target_invariants=["INV-1"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_INCONCLUSIVE_SYNTHETIC:hyp:synthetic no post-state or economic movement observed] test_HalyxHypothesis_hyp_synthetic()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_inconclusive_synthetic"


def test_falsification_engine_marks_flashloan_assumption_gap() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:flash",
            test_name="test_HalyxHypothesis_hyp_flash",
            status="unresolved",
            rationale="",
            should_fail=True,
            execution_sequence_id=None,
            execution_steps=[],
            economic_consequence="",
            violated_invariants=[],
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["borrow(uint256)"],
            target_invariants=["INV-1"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_ASSUMPTION_FLASHLOAN_NOT_REPRODUCED:modeled as capital assumption only] test_HalyxHypothesis_hyp_flash()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_assumption_gap_flashloan"


def test_falsification_engine_marks_economic_impact_not_confirmed() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:econ",
            test_name="test_HalyxHypothesis_hyp_econ",
            status="unresolved",
            rationale="",
            should_fail=True,
            execution_sequence_id=None,
            execution_steps=[],
            economic_consequence="",
            violated_invariants=[],
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["withdraw(uint256)"],
            target_invariants=["INV-1"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_ECONOMIC_IMPACT_NOT_CONFIRMED:attacker profit below prediction] test_HalyxHypothesis_hyp_econ()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_economic_impact_not_confirmed"


def test_falsification_engine_marks_behavior_not_observed() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:behavior",
            test_name="test_HalyxHypothesis_hyp_behavior",
            status="unresolved",
            rationale="",
            should_fail=True,
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["deposit()"],
            target_invariants=["INV-1"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_BEHAVIOR_NOT_OBSERVED:hyp:behavior expected invariant transition was not observed] test_HalyxHypothesis_hyp_behavior()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_behavior_not_observed"


def test_falsification_engine_marks_economic_effect_not_observed() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:effect",
            test_name="test_HalyxHypothesis_hyp_effect",
            status="unresolved",
            rationale="",
            should_fail=True,
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["withdraw(uint256)"],
            target_invariants=["INV-1"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_ECONOMIC_EFFECT_NOT_OBSERVED:hyp:effect invariant moved but economic consequence was not observed] test_HalyxHypothesis_hyp_effect()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_economic_effect_not_observed"


def test_falsification_engine_marks_reconciliation_failed() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:recon",
            test_name="test_HalyxHypothesis_hyp_recon",
            status="unresolved",
            rationale="",
            should_fail=True,
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["withdraw(uint256)"],
            target_invariants=["INV-1"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_ECONOMIC_RECONCILIATION_FAILED:attacker profit not reconciled by protocol-side movement] test_HalyxHypothesis_hyp_recon()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_inconclusive_reconciliation"


def test_falsification_engine_marks_proof_criteria_satisfied() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:proofok",
            test_name="test_HalyxHypothesis_hyp_proofok",
            status="unresolved",
            rationale="",
            should_fail=True,
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["borrow(uint256)"],
            target_invariants=["INV-1"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_PROOF_CRITERIA_SATISFIED:hyp:proofok] test_HalyxHypothesis_hyp_proofok()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_proof_criteria_satisfied"
    assert parsed[0].observed_values["proof_criteria_satisfied"] is True


def test_falsification_engine_derives_loss_attribution_metrics_from_logs() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="H-AMM-001",
            test_name="test_HalyxHypothesis_H_AMM_001",
            status="unresolved",
            rationale="",
            should_fail=False,
            target_contracts=["UnstoppableVault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["checkFlashLoan(uint256)"],
            target_invariants=["INV-UNSTOPPABLE"],
        )
    ]

    parsed = engine._parse_case_results(
        stdout=(
            "[PASS] test_HalyxHypothesis_H_AMM_001()\n"
            "H-AMM-001_PRE_VAULT_PAUSED: 0\n"
            "H-AMM-001_POST_VAULT_PAUSED: 1\n"
            "H-AMM-001_ECON_ATTACKER_BALANCE_DELTA: -1\n"
            "H-AMM-001_ECON_VAULT_BALANCE_DELTA: 1\n"
            "H-AMM-001_ECON_VAULT_FROZEN: 1\n"
            "HALYX_PROOF_CRITERIA_SATISFIED:H-AMM-001\n"
        ),
        stderr="",
        cases=cases,
    )

    observed = parsed[0].observed_values
    assert parsed[0].status == "execution_proof_criteria_satisfied"
    assert observed["proof_criteria_satisfied"] is True
    assert observed["attacker_net_pnl"] == -1
    assert observed["protocol_direct_token_loss"] == 0
    assert observed["protocol_liveness_loss"] is True
    assert observed["user_access_impairment_score"] == 80


def test_falsification_engine_marks_invariant_not_testable() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    cases = [
        FalsificationCase(
            hypothesis_id="hyp:noinv",
            test_name="test_HalyxHypothesis_hyp_noinv",
            status="unresolved",
            rationale="",
            should_fail=True,
            target_contracts=["Vault"],
            target_addresses=["0x1111111111111111111111111111111111111111"],
            target_functions=["borrow(uint256)"],
            target_invariants=[],
        )
    ]

    parsed = engine._parse_case_results(
        stdout="[FAIL. Reason: HALYX_INVARIANT_NOT_TESTABLE:hyp:noinv no executable invariant assertion] test_HalyxHypothesis_hyp_noinv()",
        stderr="",
        cases=cases,
    )
    assert parsed[0].status == "execution_invariant_not_testable"


def test_falsification_engine_derives_fallback_sequence_from_hypothesis(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Pool.sol").write_text(
        "contract Pool { function deposit(uint256 amount) external {} function withdraw(uint256 amount) external {} }",
        encoding="utf-8",
    )

    def fake_runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="[PASS] test_HalyxHypothesis_hyp_fallback()", stderr="")

    engine = FalsificationExecutionEngine(command_runner=fake_runner, which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[
            {
                "hypothesis_id": "hyp:fallback",
                "status": "unresolved",
                "subsystem": "Pool Accounting",
                "required_actors": ["attacker", "protocol"],
                "required_assumptions": ["Pool accounting is mutable through deposit/withdraw path"],
                "expected_attack_sequence": [
                    "acquire capital",
                    "deposit into pool",
                    "withdraw with accounting imbalance",
                ],
                "expected_state_transition": "pre -> post",
                "evidence_needed": ["INV-POOL"],
            }
        ],
    )

    case = report.cases[0]
    assert case.execution_steps
    assert case.sequence_source == "hypothesis_expected_attack_sequence"


def test_falsification_engine_marks_privileged_governance_targets_reachability_blocked() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    source = engine._render_test_contract(
        [
            FalsificationCase(
                hypothesis_id="hyp:gov",
                test_name="test_HalyxHypothesis_hyp_gov",
                status="unresolved",
                rationale="",
                should_fail=True,
                target_contracts=["OlympusAuthority"],
                target_addresses=["0x0000000000000000000000000000000000000001"],
                target_functions=["pushGovernor(address,bool)", "pushGuardian(address,bool)"],
                target_invariants=["INV-AUTH"],
                actors=["attacker", "protocol"],
            )
        ],
        fork_block_number=None,
    )

    assert "HALYX_REACHABILITY_FAILED:privileged governance role required for selected target functions" in source


def test_falsification_engine_emits_sequence_proof_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Vault.sol").write_text(
        "contract Vault { function deposit() external {} function redeem() external {} }",
        encoding="utf-8",
    )
    (repo / "deployments").mkdir(parents=True)
    (repo / "deployments" / "vault.json").write_text(
        '{"address":"0x1111111111111111111111111111111111111111","contract":"Vault"}',
        encoding="utf-8",
    )

    def fake_runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="[PASS] test_HalyxHypothesis_hyp_proof()", stderr="")

    engine = FalsificationExecutionEngine(
        command_runner=fake_runner,
        which=lambda _: "forge",
        fork_rpc_url="https://rpc.example",
    )
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[
            {
                "hypothesis_id": "hyp:proof",
                "status": "unresolved",
                "subsystem": "Vault",
                "execution_sequence": {
                    "sequence_id": "seq:hyp_proof",
                    "economic_consequence": "drain",
                    "violated_invariants": ["INV-SHARE-RATE"],
                    "ordered_steps": [
                        {"index": 1, "handler": "deposit", "caller": "external_user"},
                        {"index": 2, "handler": "redeem", "caller": "external_user"},
                    ],
                },
            }
        ],
    )

    assert report.executed is True
    case = report.cases[0]
    assert case.proof_marker == "HALYX_TEST_COMPLETED:hyp:proof"
    assert case.proof_summary.startswith("Replay")
    generated = Path(str(report.generated_test_file or ""))
    source = generated.read_text(encoding="utf-8")
    assert "HALYX_TEST_COMPLETED:hyp:proof" in source
    assert "step:1:deposit" in source
    assert "step:2:redeem" in source


def test_falsification_engine_blocks_when_no_verified_targets_survive(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Vault.sol").write_text("contract Vault { function deposit() external {} }", encoding="utf-8")
    (repo / "deployments").mkdir(parents=True)
    (repo / "deployments" / "vault.json").write_text(
        '{"address":"0x1111111111111111111111111111111111111111","contract":"Vault"}',
        encoding="utf-8",
    )

    def fake_urlopen(request):
        response = MagicMock()
        response.read.return_value = json.dumps({"status": "0", "message": "NOTOK", "result": "No source"}).encode()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    def fake_runner(*args, **kwargs):
        raise AssertionError("forge should not run when no verified addresses survive")

    engine = FalsificationExecutionEngine(
        command_runner=fake_runner,
        which=lambda _: "forge",
        fork_rpc_url="https://rpc.example",
        etherscan_api_keys=["test-key"],
        etherscan_urlopen=fake_urlopen,
    )
    report = engine.execute(
        repository_path=repo,
        hypothesis_ledger=[{"hypothesis_id": "hyp:a", "status": "unresolved"}],
        chain="ethereum",
    )

    assert report.executed is False
    assert report.mode == "foundry_missing_verified_targets"
    assert "No verified explorer-backed contract addresses" in (report.reason or "")


def test_falsification_engine_ignores_embedded_hex_and_uses_explicit_address_fields(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Vault.sol").write_text("contract Vault { function deposit() external {} }", encoding="utf-8")
    (repo / "deployments").mkdir(parents=True)
    (repo / "deployments" / "vault.json").write_text(
        json.dumps(
            {
                "contractName": "Vault",
                "address": "0x2222222222222222222222222222222222222222",
                "bytecode": "0x6000600055600011223344556677889900aabbccddeeff00112233445566778899",
                "metadata": {
                    "note": "contains random hex 0x0000000000000000000000001066620ae90cab64 that should be ignored"
                },
            }
        ),
        encoding="utf-8",
    )

    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    mapping, discovered, _verified = engine._collect_contract_addresses(  # noqa: SLF001
        repo,
        source_map=[{"contracts": ["Vault"], "functions": [], "search_text": "vault"}],
        chain="ethereum",
    )

    assert discovered >= 1
    assert mapping["Vault"] == ["0x2222222222222222222222222222222222222222"]


def test_falsification_engine_prefers_execution_case_targets_over_heuristics() -> None:
    engine = FalsificationExecutionEngine(which=lambda _: "forge", fork_rpc_url="https://rpc.example")
    ledger = [
        {
            "hypothesis_id": "H-EX-001",
            "status": "supported",
            "subsystem": "Vault",
            "execution_case": {
                "target_contracts": ["Vault"],
                "target_addresses": ["0x3333333333333333333333333333333333333333"],
                "target_functions": ["withdraw(uint256)"],
                "target_invariants": ["INV-WITHDRAW"],
                "execution_steps": [{"index": 1, "handler": "withdraw", "caller": "external_user"}],
                "economic_consequence": "fund drain",
                "violated_invariants": ["INV-WITHDRAW"],
            },
        }
    ]

    cases = engine._build_cases(
        ledger,
        source_map=[{"contracts": ["Other"], "functions": ["noop()"], "search_text": "other"}],
        address_map={"Other": ["0x4444444444444444444444444444444444444444"]},
    )

    assert len(cases) == 1
    case = cases[0]
    assert case.target_contracts == ["Vault"]
    assert case.target_addresses == ["0x3333333333333333333333333333333333333333"]
    assert case.target_functions == ["withdraw(uint256)"]
    assert case.target_invariants == ["INV-WITHDRAW"]
    assert case.economic_consequence == "fund drain"