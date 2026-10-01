from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import quantum_economic_auditor.api.app as api_app

app = api_app.app


def test_halyx_ui_serves_dashboard_and_latest_result(tmp_path: Path, monkeypatch) -> None:
    result_path = tmp_path / "halyx_pipeline_result.json"
    result_path.write_text(
        json.dumps(
            {
                "repository_context": {"repository_path": "/tmp/raydium"},
                "methodology": {"phases": [{"name": "phase0", "status": "ready", "summary": "scope captured"}]},
                "protocol_pattern": {"label": "AMM", "confidence": 0.88},
                "expected_vs_observed": {"match_ratio": 0.57, "missing_expected": ["Fee Distribution"]},
                "planning": {"uncertainty_score": 0.52, "next_action": {"action": "invoke_tutor", "rationale": "gap detected", "expected_information_gain": 0.9, "uncertainty_reduction": 0.6}},
                "subsystem_plan": {"reconstructions": []},
                "tutor_research": [],
                "verification_reports": [
                    {
                        "concept": "Fee Distribution",
                        "subsystem": "Fee Distribution",
                        "verified": False,
                        "verification_score": 0.42,
                        "rationale": "Insufficient deterministic evidence",
                        "matched_files": [],
                        "missing_terms": ["feeAccumulator"],
                    }
                ],
                "investigation_reports": [],
                "research_hypotheses": [],
                "hypothesis_evidence_ledger": [
                    {
                        "hypothesis_id": "hyp:fee-distribution",
                        "title": "Fee Distribution Coverage",
                        "subsystem": "Fee Distribution",
                        "status": "unresolved",
                        "proof_attempts": [{"attempt_id": "proof:hyp:fee-distribution:tutor"}],
                        "falsification_attempts": [{"attempt_id": "falsify:hyp:fee-distribution:investigator"}],
                        "confidence_trajectory": [
                            {
                                "timestamp": "2026-01-01T00:00:00+00:00",
                                "stage": "surfaced",
                                "confidence": 0.35,
                                "delta": 0.0,
                                "reason": "Gap detected",
                            }
                        ],
                        "final_confidence": 0.35,
                    }
                ],
                "reasoning": {},
                "falsification_execution": {
                    "mode": "non_foundry",
                    "executed": False,
                    "cases": [],
                    "reason": "Repository does not contain foundry.toml",
                },
                "consensus": {"classification": "survives", "confidence": 0.8},
                "evidence_graph": {},
                "protocol_reconstruction": {},
                "protocol_semantics": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(result_path))
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))

    client = TestClient(app)

    root_response = client.get("/")
    dashboard_response = client.get("/api/dashboard")

    assert root_response.status_code == 200
    assert "Halyx Mission Control" in root_response.text
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["planning"]["next_action"]["action"] == "invoke_tutor"
    assert dashboard_response.json()["hypothesis_trace"][0]["hypothesis_id"] == "hyp:fee-distribution"
    assert dashboard_response.json()["verification_reports"][0]["concept"] == "Fee Distribution"
    assert dashboard_response.json()["falsification_execution"]["mode"] == "non_foundry"


def test_halyx_ui_launch_endpoint_executes_pipeline(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=10),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="survives")),
            }

    monkeypatch.setattr(api_app, "_resolve_repository_input", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)

    client = TestClient(app)
    response = client.post(
        "/api/launch",
        json={"target": "Raydium", "scope": "Raydium", "chain": "solana"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["protocol"] == tmp_path.name
    assert payload["methodology_phases"] == 10
    assert payload["consensus"] == "survives"


def test_halyx_ui_launch_uses_source_code_when_provided(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=4),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="unknown")),
            }

    def fake_resolve_repository_input(value: str, **_kwargs) -> Path:
        assert "pragma solidity" in value
        return tmp_path

    monkeypatch.setattr(api_app, "_resolve_repository_input", fake_resolve_repository_input)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)

    client = TestClient(app)
    response = client.post(
        "/api/launch",
        json={
            "target": "ignored",
            "scope": "Manual",
            "chain": "ethereum",
            "source_code": "pragma solidity ^0.8.20;\\ncontract Manual { }\\n",
        },
    )

    assert response.status_code == 200


def test_halyx_ui_launch_returns_400_for_acquisition_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))

    def fake_resolve_repository_input(*_args, **_kwargs) -> Path:
        raise ValueError("no Etherscan API key configured")

    monkeypatch.setattr(api_app, "_resolve_repository_input", fake_resolve_repository_input)

    client = TestClient(app)
    response = client.post(
        "/api/launch",
        json={
            "target": "https://immunefi.com/bug-bounty/capyfi/information/",
            "chain": "ethereum",
        },
    )

    assert response.status_code == 400
    assert "no Etherscan API key configured" in response.json()["detail"]


def test_halyx_ui_launch_forwards_scope_url_and_keys(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=1),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="unknown")),
            }

    captured: dict[str, object] = {}

    def fake_resolve_repository_input(value: str, **kwargs) -> Path:
        captured["value"] = value
        captured["kwargs"] = kwargs
        return tmp_path

    monkeypatch.setattr(api_app, "_resolve_repository_input", fake_resolve_repository_input)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)

    client = TestClient(app)
    response = client.post(
        "/api/launch",
        json={
            "target": "https://immunefi.com/bug-bounty/capyfi/information/",
            "scope": "capyfi",
            "chain": "ethereum",
            "etherscan_api_key": "primary",
            "etherscan_api_key_alt": "fallback",
        },
    )

    assert response.status_code == 200
    assert captured["value"] == "https://immunefi.com/bug-bounty/capyfi/information/"
    kwargs = captured["kwargs"]
    assert kwargs["etherscan_api_key"] == "primary"
    assert kwargs["etherscan_api_key_alt"] == "fallback"


def test_halyx_launch_uses_persisted_global_explorer_keys(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.delenv("ETHERSCAN_API_KEY_ALT", raising=False)

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=1),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="unknown")),
            }

    captured: dict[str, object] = {}

    def fake_resolve_repository_input(value: str, **kwargs) -> Path:
        captured["kwargs"] = kwargs
        return tmp_path

    api_app._persist_global_explorer_keys(etherscan_api_key="persisted-primary", etherscan_api_key_alt="persisted-alt")
    monkeypatch.setattr(api_app, "_resolve_repository_input", fake_resolve_repository_input)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)

    client = TestClient(app)
    response = client.post(
        "/api/launch",
        json={
            "target": "https://immunefi.com/bug-bounty/capyfi/information/",
            "scope": "capyfi",
            "chain": "ethereum",
        },
    )

    assert response.status_code == 200
    kwargs = captured["kwargs"]
    assert kwargs["etherscan_api_key"] == "persisted-primary"
    assert kwargs["etherscan_api_key_alt"] == "persisted-alt"


def test_resolve_effective_explorer_keys_prefers_explicit_then_env_then_global(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.delenv("ETHERSCAN_API_KEY_ALT", raising=False)

    api_app._persist_global_explorer_keys(etherscan_api_key="global-primary", etherscan_api_key_alt="global-alt")
    primary, alt = api_app._resolve_effective_explorer_keys(etherscan_api_key=None, etherscan_api_key_alt=None)
    assert primary == "global-primary"
    assert alt == "global-alt"

    monkeypatch.setenv("ETHERSCAN_API_KEY", "env-primary")
    monkeypatch.setenv("ETHERSCAN_API_KEY_ALT", "env-alt")
    primary, alt = api_app._resolve_effective_explorer_keys(etherscan_api_key=None, etherscan_api_key_alt=None)
    assert primary == "env-primary"
    assert alt == "env-alt"

    primary, alt = api_app._resolve_effective_explorer_keys(etherscan_api_key="explicit-primary", etherscan_api_key_alt="explicit-alt")
    assert primary == "explicit-primary"
    assert alt == "explicit-alt"


def test_write_run_env_persists_global_explorer_keys(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.delenv("ETHERSCAN_API_KEY_ALT", raising=False)

    repo_root = tmp_path / "acquired_repo"
    repo_root.mkdir(parents=True)
    (repo_root / "README.md").write_text("repo", encoding="utf-8")

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=1),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="unknown")),
            }

    monkeypatch.setattr(api_app, "_resolve_repository_input", lambda *args, **kwargs: repo_root)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)

    client = TestClient(app)
    launch = client.post("/api/launch", json={"target": "Origin Protocol", "scope": "Origin", "chain": "ethereum"})
    assert launch.status_code == 200
    run_id = launch.json()["run_id"]

    write_env = client.post(
        f"/api/runs/{run_id}/env",
        json={"file_name": ".env.local", "etherscan_api_key": "saved-primary", "etherscan_api_key_alt": "saved-alt"},
    )
    assert write_env.status_code == 200

    primary, alt = api_app._resolve_effective_explorer_keys(etherscan_api_key=None, etherscan_api_key_alt=None)
    assert primary == "saved-primary"
    assert alt == "saved-alt"


def test_dashboard_payload_exposes_hypothesis_and_falsification_summary() -> None:
    payload = api_app._build_dashboard_payload_from_result(
        result={
            "hypothesis_evidence_ledger": [
                {"status": "supported", "execution_case": {"status": "supported_by_execution"}},
                {"status": "disproved", "execution_case": {"status": "falsification_triggered"}},
                {"status": "rejected_before_ranking"},
            ],
            "falsification_execution": {
                "mode": "foundry_isolated",
                "executed": True,
                "cases": [
                    {"status": "supported_by_execution"},
                    {"status": "falsification_triggered"},
                ],
                "reason": "No compatible target found",
            },
        },
        runs=[],
        latest_run_id=None,
    )

    assert payload["hypothesis_outcomes"]["supported"] == 1
    assert payload["hypothesis_outcomes"]["disproved"] == 1
    assert payload["hypothesis_outcomes"]["unresolved"] == 1
    assert payload["falsification_summary"]["case_count"] == 2
    assert payload["falsification_summary"]["summary"].startswith("Foundry")


def test_halyx_ui_launch_endpoint_prefers_fresh_orchestrator_result(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(runs_root))

    stale_result = tmp_path / "stale_result.json"
    stale_result.write_text(json.dumps({"research_hypotheses": [], "falsification_execution": {"mode": "stale"}}), encoding="utf-8")
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(stale_result))

    fresh_result = tmp_path / "fresh_result.json"
    fresh_result.write_text(
        json.dumps(
            {
                "repository_context": {"repository_path": str(tmp_path)},
                "methodology": {"phases": [{"name": "phase0", "status": "ready", "summary": "fresh"}]},
                "planning": {"next_action": {"action": "invoke_tutor"}},
                "research_hypotheses": [{"hypothesis_id": "fresh-1", "title": "Fresh hypothesis", "rationale": "fresh"}],
                "falsification_execution": {"mode": "fresh_foundry", "executed": True, "cases": []},
                "consensus": {"classification": "survives"},
            }
        ),
        encoding="utf-8",
    )

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=2),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="survives")),
                "persistence": fresh_result,
            }

    monkeypatch.setattr(api_app, "_resolve_repository_input", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)

    client = TestClient(app)
    response = client.post("/api/launch", json={"target": "Origin Protocol", "scope": "Origin", "chain": "ethereum"})

    assert response.status_code == 200
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["research_hypotheses"][0]["title"] == "Fresh hypothesis"
    assert dashboard.json()["falsification_execution"]["mode"] == "fresh_foundry"


def test_halyx_ui_run_management_endpoints(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))

    repo_root = tmp_path / "acquired_repo"
    (repo_root / "contracts").mkdir(parents=True)
    (repo_root / "contracts" / "Core.sol").write_text("contract Core {}", encoding="utf-8")
    (repo_root / "README.md").write_text("repo", encoding="utf-8")

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=7),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="survives")),
            }

    monkeypatch.setattr(api_app, "_resolve_repository_input", lambda *args, **kwargs: repo_root)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)

    client = TestClient(app)
    launch = client.post("/api/launch", json={"target": "Origin Protocol", "scope": "Origin", "chain": "ethereum"})
    assert launch.status_code == 200
    run_id = launch.json()["run_id"]

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert runs.json()["runs"]

    tree = client.get(f"/api/runs/{run_id}/tree")
    assert tree.status_code == 200
    tree_entries = tree.json()["entries"]
    assert any(entry["path"] == "contracts" for entry in tree_entries)

    file_read = client.get(f"/api/runs/{run_id}/file", params={"path": "contracts/Core.sol"})
    assert file_read.status_code == 200
    assert "contract Core" in file_read.json()["content"]

    file_write = client.put(
        f"/api/runs/{run_id}/file",
        json={"path": "contracts/Core.sol", "content": "contract Core { function ping() external pure returns (bool) { return true; } }\n"},
    )
    assert file_write.status_code == 200

    file_read_after = client.get(f"/api/runs/{run_id}/file", params={"path": "contracts/Core.sol"})
    assert file_read_after.status_code == 200
    assert "function ping()" in file_read_after.json()["content"]

    terminal = client.get(f"/api/runs/{run_id}/terminal")
    assert terminal.status_code == 200
    assert "Halyx launch completed" in terminal.json()["text"]

    poc = client.post(f"/api/runs/{run_id}/poc-run")
    assert poc.status_code == 400
    assert "No hypothesis evidence was recorded" in poc.json()["detail"]

    deletion = client.delete(f"/api/runs/{run_id}")
    assert deletion.status_code == 200
    assert deletion.json()["deleted_run"] is True


def test_halyx_ui_poc_run_regenerates_from_current_engine(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))

    repo_root = tmp_path / "acquired_repo"
    (repo_root / "contracts").mkdir(parents=True)
    (repo_root / "contracts" / "Core.sol").write_text("contract Core {}", encoding="utf-8")
    (repo_root / "README.md").write_text("repo", encoding="utf-8")

    fresh_result = tmp_path / "fresh_result.json"
    fresh_result.write_text(
        json.dumps(
            {
                "repository_context": {"repository_path": str(repo_root)},
                "methodology": {"phases": [{"name": "phase0", "status": "ready", "summary": "fresh"}]},
                "planning": {"next_action": {"action": "invoke_tutor"}},
                "research_hypotheses": [{"hypothesis_id": "fresh-1", "title": "Fresh hypothesis", "rationale": "fresh"}],
                "hypothesis_evidence_ledger": [
                    {
                        "hypothesis_id": "fresh-1",
                        "status": "unresolved",
                        "subsystem": "Core",
                        "evidence_needed": ["verified address"],
                    }
                ],
                "falsification_execution": {
                    "mode": "stale",
                    "executed": False,
                    "command": ["forge", "test"],
                    "harness_dir": str(tmp_path / "stale"),
                },
                "consensus": {"classification": "survives"},
            }
        ),
        encoding="utf-8",
    )

    class _FakeOrchestrator:
        def run(self, repository_path: Path, eir: object, program_scope: str) -> dict[str, object]:
            return {
                "methodology": SimpleNamespace(phase_count=2),
                "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="survives")),
                "persistence": fresh_result,
            }

    captured = {}

    class _FakeFalsificationEngine:
        def __init__(self, *, fork_rpc_url: str | None = None, etherscan_api_keys: list[str] | None = None):
            captured["fork_rpc_url"] = fork_rpc_url
            captured["etherscan_api_keys"] = etherscan_api_keys

        def _discover_fork_rpc(self, repository_path: Path):
            return "https://rpc.example", "env:FORK_TEST_RPC_URL"

        def execute(self, *, repository_path: Path, hypothesis_ledger: list[dict[str, object]], chain: str | None = None):
            captured["repository_path"] = repository_path
            captured["hypothesis_ledger"] = hypothesis_ledger
            captured["chain"] = chain
            return SimpleNamespace(
                executed=True,
                command=["forge", "test", "--match-path", "test/HalyxHypothesisEvidence.t.sol", "-vv"],
                harness_dir=str(repo_root / ".halyx" / "fresh_harness"),
                fork_rpc_source="env:FORK_TEST_RPC_URL",
                returncode=0,
                passed=True,
                stdout_tail="[PASS] test_HalyxHypothesis_fresh_1()",
                stderr_tail="",
                cases=[],
                reason=None,
            )

    monkeypatch.setattr(api_app, "_resolve_repository_input", lambda *args, **kwargs: repo_root)
    monkeypatch.setattr(api_app, "HalyxOrchestrator", _FakeOrchestrator)
    monkeypatch.setattr(api_app, "FalsificationExecutionEngine", _FakeFalsificationEngine)

    client = TestClient(app)
    launch = client.post("/api/launch", json={"target": "Origin Protocol", "scope": "Origin", "chain": "ethereum"})
    assert launch.status_code == 200
    run_id = launch.json()["run_id"]

    poc = client.post(f"/api/runs/{run_id}/poc-run")
    assert poc.status_code == 200
    payload = poc.json()
    assert payload["passed"] is True
    assert payload["fork_rpc_source"] == "env:FORK_TEST_RPC_URL"
    assert captured["chain"] == "ethereum"
    assert captured["hypothesis_ledger"][0]["hypothesis_id"] == "fresh-1"


def test_halyx_terminal_log_sanitizes_overlong_phase_summary(tmp_path: Path) -> None:
    noisy = "x" * 400
    result = {
        "repository_context": {"repository_path": "/tmp/repo"},
        "methodology": {"phases": [{"name": "phase0", "status": "ready", "summary": noisy}]},
        "planning": {"next_action": {"action": "invoke_tutor", "expected_information_gain": 0.9}},
        "consensus": {"classification": "survives"},
    }
    text = api_app._build_terminal_log(result)
    assert "[phase]" in text
    assert len(text) < 900


def test_halyx_terminal_line_sanitizer_truncates_phase_spillover() -> None:
    noisy = "[phase] phase0 :: ready :: " + ("abc " * 300)
    line = api_app._sanitize_terminal_line(noisy)
    assert line.startswith("[phase] phase0 :: ready ::")
    assert len(line) < 360