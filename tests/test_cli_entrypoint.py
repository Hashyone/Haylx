from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from quantum_economic_auditor.cli.main import app, build_cli
from quantum_economic_auditor.source_acquisition.agent import AcquisitionResult


def test_cli_entrypoint_builds_and_runs(tmp_path: Path) -> None:
    cli = build_cli()
    assert cli is not None


def test_analyze_command_resolves_contract_address_before_orchestration(monkeypatch, tmp_path: Path) -> None:
    acquired_root = tmp_path / "acquired"
    acquired_root.mkdir()
    (acquired_root / "Contract.sol").write_text("contract Contract {}", encoding="utf-8")
    metadata_path = acquired_root / ".halyx-acquisition.json"
    metadata_path.write_text("{}", encoding="utf-8")

    def fake_resolve_input(self, value: str, *, chain: str | None = None, output_root: Path | None = None) -> AcquisitionResult:
        assert value == "0x1234567890abcdef1234567890abcdef12345678"
        assert chain == "base"
        return AcquisitionResult(
            source_root=acquired_root,
            input_kind="contract_address",
            primary_contract_name="Contract",
            contract_count=1,
            metadata_path=metadata_path,
        )

    def fake_orchestrator_run(self, *, repository_path: Path, eir, program_scope: str):
        assert repository_path == acquired_root
        return {
            "repository_context": SimpleNamespace(repository_path=repository_path),
            "methodology": SimpleNamespace(phase_count=10),
            "consensus": SimpleNamespace(classical_classification=SimpleNamespace(value="survives")),
            "persistence": SimpleNamespace(read=lambda: {"subsystem_plan": {"subsystems": [], "reconstructions": []}}),
        }

    monkeypatch.setattr("quantum_economic_auditor.source_acquisition.agent.SourceAcquisitionAgent.resolve_input", fake_resolve_input)
    monkeypatch.setattr("quantum_economic_auditor.pipeline.orchestrator.HalyxOrchestrator.run", fake_orchestrator_run)

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "0x1234567890abcdef1234567890abcdef12345678", "--chain", "base", "--scope", "Base Bridge"])

    assert result.exit_code == 0, result.output
    assert "Repository context captured" in result.output


def test_acquire_command_resolves_github_reference(monkeypatch, tmp_path: Path) -> None:
    acquired_root = tmp_path / "github"
    acquired_root.mkdir()
    metadata_path = acquired_root / ".halyx-acquisition.json"
    metadata_path.write_text("{}", encoding="utf-8")

    def fake_resolve_input(self, value: str, *, chain: str | None = None, output_root: Path | None = None) -> AcquisitionResult:
        assert value == "OlympusDAO/olympus-v3"
        return AcquisitionResult(
            source_root=acquired_root,
            input_kind="github",
            primary_contract_name="olympus-v3",
            contract_count=1,
            metadata_path=metadata_path,
        )

    monkeypatch.setattr("quantum_economic_auditor.source_acquisition.agent.SourceAcquisitionAgent.resolve_input", fake_resolve_input)

    runner = CliRunner()
    result = runner.invoke(app, ["acquire", "OlympusDAO/olympus-v3"])

    assert result.exit_code == 0, result.output
    assert str(acquired_root) in result.output


def test_acquire_command_accepts_manual_source_file(monkeypatch, tmp_path: Path) -> None:
    acquired_root = tmp_path / "manual"
    acquired_root.mkdir()
    metadata_path = acquired_root / ".halyx-acquisition.json"
    metadata_path.write_text("{}", encoding="utf-8")

    source_file = tmp_path / "Manual.sol"
    source_file.write_text("pragma solidity ^0.8.20;\ncontract Manual {}\n", encoding="utf-8")

    def fake_resolve_input(self, value: str, *, chain: str | None = None, output_root: Path | None = None) -> AcquisitionResult:
        assert "pragma solidity" in value
        return AcquisitionResult(
            source_root=acquired_root,
            input_kind="manual_source",
            primary_contract_name="Manual",
            contract_count=1,
            metadata_path=metadata_path,
        )

    monkeypatch.setattr("quantum_economic_auditor.source_acquisition.agent.SourceAcquisitionAgent.resolve_input", fake_resolve_input)

    runner = CliRunner()
    result = runner.invoke(app, ["acquire", "ignored-target", "--source-file", str(source_file)])

    assert result.exit_code == 0, result.output
    assert str(acquired_root) in result.output
