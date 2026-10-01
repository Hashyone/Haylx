from pathlib import Path

from typer.testing import CliRunner

from quantum_economic_auditor.cli.main import app


def test_inspect_command_outputs_economic_filter_report() -> None:
    repo_path = Path(__file__).resolve().parents[1] / "olympus-v3"
    runner = CliRunner()

    result = runner.invoke(app, ["inspect", str(repo_path)])

    assert result.exit_code == 0, result.output
    assert "source_location" in result.output
    assert "reason_kept" in result.output
    assert "reason_discarded" in result.output
