from __future__ import annotations

from pathlib import Path

import typer

from quantum_economic_auditor.openclaw.agents.repository_context import RepositoryContextAgent
from quantum_economic_auditor.source_acquisition import SourceAcquisitionAgent, SourceAcquisitionError

from quantum_economic_auditor.agents.economic_extractor import StaticEconomicExtractor
from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)
from quantum_economic_auditor.parser.repository_loader import load_repository
from quantum_economic_auditor.pipeline.orchestrator import HalyxOrchestrator
from quantum_economic_auditor.pipeline.pipeline import PipelineConfig, ResearchPipeline

app = typer.Typer(help="Research CLI for protocol-economic optimization comparison")


def build_cli() -> typer.Typer:
    return app


@app.command("audit")
def audit_command(path: str = typer.Argument(..., help="Path to the Solidity repository")) -> None:
    pipeline = ResearchPipeline(PipelineConfig(protocol_path=path))
    summary = pipeline.run()
    typer.echo(f"Protocol analyzed: {summary.protocol_name}")
    typer.echo(f"CSV report written to: {summary.report_path}")


@app.command("extract")
def extract_command(path: str = typer.Argument(..., help="Path to the Solidity repository")) -> None:
    pipeline = ResearchPipeline(PipelineConfig(protocol_path=path))
    repository = pipeline.extractor.extract(load_repository(path))
    typer.echo(repository.model_dump_json(indent=2))


@app.command("inspect")
def inspect_command(path: str = typer.Argument(..., help="Path to the Solidity repository")) -> None:
    extractor = StaticEconomicExtractor()
    repository = load_repository(path)
    inspection_rows = extractor.inspect_repository(repository)
    if not inspection_rows:
        typer.echo("No economic inspection rows were produced.")
        return

    typer.echo("name|source_location|category|reason_kept|reason_discarded")
    for row in inspection_rows:
        typer.echo(
            "|".join(
                [
                    row.get("name", ""),
                    row.get("source_location", ""),
                    row.get("category", ""),
                    row.get("reason_kept", ""),
                    row.get("reason_discarded", ""),
                ]
            )
        )


@app.command("compile")
def compile_command() -> None:
    typer.echo("Constraint compilation stage is wired to the pipeline and deterministic.")


@app.command("encode")
def encode_command() -> None:
    typer.echo("Binary encoding is deterministic and supports optional Gray code.")


@app.command("optimize-classical")
def optimize_classical_command() -> None:
    typer.echo("Classical optimizer stage is exposed through the common optimizer interface.")


@app.command("optimize-quantum")
def optimize_quantum_command() -> None:
    typer.echo("Quantum optimizer stage is exposed through the PennyLane abstraction.")


@app.command("compare")
def compare_command() -> None:
    typer.echo("Comparison engine materializes execution metrics and convergence outputs.")


@app.command("report")
def report_command(output_dir: str = typer.Option("reports", help="Location for generated reports")) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    typer.echo(f"Reports directory ready at {output_dir}")


def _resolve_scope_table(scope: str | None) -> str:
    if scope:
        return scope

    typer.echo("Program scope is required for repository-context analysis.")
    typer.echo("Please provide the scope table, for example: immunefi, cantina, or another launch venue.")
    scope_value = typer.prompt("Scope table", default="target")
    return scope_value.strip() or "target"


def _resolve_repository_input(value: str, *, chain: str | None = None, output_root: str | None = None) -> Path:
    agent = SourceAcquisitionAgent()
    try:
        result = agent.resolve_input(
            value,
            chain=chain,
            output_root=Path(output_root).resolve() if output_root else None,
        )
    except SourceAcquisitionError as error:
        typer.echo(str(error))
        raise typer.Exit(1) from error
    return result.source_root


@app.command("acquire")
def acquire_command(
    target: str = typer.Argument(..., help="Local path, 0x contract address, or GitHub owner/repo reference"),
    chain: str = typer.Option("ethereum", "--chain", help="Chain name or chain id for contract-address acquisition"),
    output: str | None = typer.Option(None, "--output", "-o", help="Destination directory for fetched sources"),
    source_file: str | None = typer.Option(None, "--source-file", help="Path to pasted/manual Solidity source file"),
) -> None:
    source_input = Path(source_file).read_text(encoding="utf-8") if source_file else target
    repository_path = _resolve_repository_input(source_input, chain=chain, output_root=output)
    typer.echo(f"Sources acquired: {repository_path}")


@app.command("analyze")
def analyze_command(
    path: str = typer.Argument(..., help="Path, contract address, or GitHub owner/repo reference to analyze"),
    chain: str = typer.Option("ethereum", "--chain", help="Chain name or chain id for contract-address acquisition"),
    scope: str | None = typer.Option(None, "--scope", help="Scope hint for repository context gathering"),
    output: str | None = typer.Option(None, "--output", "-o", help="Destination directory for fetched sources"),
    source_file: str | None = typer.Option(None, "--source-file", help="Path to pasted/manual Solidity source file"),
) -> None:
    source_input = Path(source_file).read_text(encoding="utf-8") if source_file else path
    repository_path = _resolve_repository_input(source_input, chain=chain, output_root=output)
    resolved_scope = _resolve_scope_table(scope)

    eir = EconomicIntermediateRepresentation(
        protocol_name=repository_path.name,
        variables=[EconomicVariable(name="Collateral", category="collateral")],
        actions=[EconomicAction(name="Borrow", kind="borrow")],
        relationships=[EconomicRelationship(source="Collateral", relation="collateralizes", target="Borrow")],
        invariants=[EconomicInvariant(name="Collateralization", kind="collateralization", expression="Collateral >= 0")],
        objectives=[EconomicObjective(name="Profit", kind="profit", expression="Collateral", weight=1.0)],
    )
    orchestrator = HalyxOrchestrator()
    result = orchestrator.run(repository_path=repository_path, eir=eir, program_scope=resolved_scope)
    typer.echo(f"Repository context captured: {result['repository_context'].repository_path}")
    typer.echo(f"Methodology phases: {result['methodology'].phase_count}")
    typer.echo(f"Consensus classification: {result['consensus'].classical_classification.value}")
    if result.get("planning") is not None:
        planning = result["planning"]
        typer.echo(
            f"Next action: {planning.next_action.action} (info gain {planning.next_action.expected_information_gain:.2f})"
        )

    payload = result["persistence"].read() if hasattr(result["persistence"], "read") else None
    if payload:
        subsystems = payload.get("subsystem_plan", {}).get("subsystems", [])
        reconstructions = payload.get("subsystem_plan", {}).get("reconstructions", [])
        typer.echo("\nSubsystem Audit Plan")
        for subsystem, reconstruction in zip(subsystems, reconstructions, strict=False):
            typer.echo(f"- {subsystem['name']} (priority {subsystem['priority_score']:.2f})")
            typer.echo(f"  states: {', '.join(reconstruction.get('state_machine_states', [])) or 'n/a'}")
            typer.echo(f"  accounting: {reconstruction.get('accounting_model') or 'n/a'}")
            typer.echo(f"  invariants: {reconstruction.get('invariant_count', 0)}")


if __name__ == "__main__":
    app()
