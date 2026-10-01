from __future__ import annotations

from datetime import UTC, datetime
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from quantum_economic_auditor.models.protocol import ProtocolSpec
from quantum_economic_auditor.parser.repository_loader import load_repository
from quantum_economic_auditor.pipeline.orchestrator import HalyxOrchestrator
from quantum_economic_auditor.pipeline.pipeline import PipelineConfig, ResearchPipeline
from quantum_economic_auditor.semantic.falsification_engine import FalsificationExecutionEngine
from quantum_economic_auditor.source_acquisition.agent import (
    SourceAcquisitionAgent,
    SourceAcquisitionError,
    is_contract_address,
    is_github_reference,
    is_git_reference,
    is_scope_url,
    is_solidity_source_blob,
)

app = FastAPI(title="Quantum Economic Auditor API")

STATIC_DIR = Path(__file__).resolve().parent / "static"
RESULT_PATH_ENV = "HALYX_PIPELINE_RESULT_PATH"
RUNS_ROOT_ENV = "HALYX_RUNS_ROOT"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR, html=False), name="static")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _runs_root() -> Path:
    env_value = os.getenv(RUNS_ROOT_ENV)
    if env_value:
        root = Path(env_value).expanduser()
    else:
        root = Path(os.getenv("HALYX_HOME") or str(Path.cwd() / ".halyx-home")) / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _runs_index_path() -> Path:
    return _runs_root() / "index.json"


def _load_runs_index() -> dict[str, object]:
    path = _runs_index_path()
    if not path.exists():
        return {"latest_run_id": None, "runs": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"latest_run_id": None, "runs": []}
    payload.setdefault("latest_run_id", None)
    payload.setdefault("runs", [])
    return payload


def _save_runs_index(index: dict[str, object]) -> None:
    _runs_index_path().write_text(json.dumps(index, indent=2), encoding="utf-8")


def _run_dir(run_id: str) -> Path:
    return _runs_root() / run_id


def _upsert_run(record: dict[str, object]) -> None:
    index = _load_runs_index()
    runs = [item for item in index.get("runs", []) if isinstance(item, dict)]
    runs = [item for item in runs if item.get("run_id") != record.get("run_id")]
    runs.insert(0, record)
    index["runs"] = runs
    index["latest_run_id"] = record.get("run_id")
    _save_runs_index(index)


def _get_run_record(run_id: str) -> dict[str, object]:
    index = _load_runs_index()
    for item in index.get("runs", []):
        if isinstance(item, dict) and item.get("run_id") == run_id:
            return item
    raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")


def _drop_run_record(run_id: str) -> dict[str, object]:
    index = _load_runs_index()
    runs = [item for item in index.get("runs", []) if isinstance(item, dict)]
    matched = None
    retained: list[dict[str, object]] = []
    for item in runs:
        if item.get("run_id") == run_id:
            matched = item
        else:
            retained.append(item)
    if matched is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
    index["runs"] = retained
    index["latest_run_id"] = retained[0]["run_id"] if retained else None
    _save_runs_index(index)
    return matched


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _summarize_consensus(result: dict[str, object]) -> dict[str, object]:
    consensus = result.get("consensus", {}) if isinstance(result, dict) else {}
    expected_vs_observed = result.get("expected_vs_observed", {}) if isinstance(result, dict) else {}
    reasoning = result.get("reasoning", {}) if isinstance(result, dict) else {}
    missing = expected_vs_observed.get("missing_expected", []) if isinstance(expected_vs_observed, dict) else []
    falsification = result.get("falsification_execution", {}) if isinstance(result.get("falsification_execution"), dict) else {}
    cases = falsification.get("cases", []) if isinstance(falsification, dict) else []
    supported_cases = sum(
        1
        for case in cases
        if isinstance(case, dict) and case.get("status") in {"supported_by_execution"}
    )
    disproved_cases = sum(1 for case in cases if isinstance(case, dict) and case.get("status") == "falsification_triggered")
    unknown_cases = sum(
        1
        for case in cases
        if isinstance(case, dict) and case.get("status") not in {"supported_by_execution", "falsification_triggered"}
    )

    classification = str(consensus.get("classification") or "unknown")
    if classification == "survives":
        explanation = (
            "Classification is survives because no decisive protocol-level contradiction was proven; "
            f"execution evidence supported {supported_cases} hypotheses, disproved {disproved_cases}, "
            f"and left {unknown_cases} unresolved; open gaps: {', '.join(missing) if missing else 'none'}."
        )
    else:
        explanation = (
            f"Classification is {classification}; execution evidence supported {supported_cases}, "
            f"disproved {disproved_cases}, unresolved {unknown_cases}; open gaps: {', '.join(missing) if missing else 'none'}."
        )

    return {
        "classification": classification,
        "research_priority": consensus.get("research_priority"),
        "missing_expected": missing,
        "classical_summary": reasoning.get("classical_summary", ""),
        "ml_summary": reasoning.get("ml_summary", ""),
        "quantum_summary": reasoning.get("quantum_summary", ""),
        "supported_cases": supported_cases,
        "disproved_cases": disproved_cases,
        "unknown_cases": unknown_cases,
        "explanation": explanation,
    }


def _build_hypothesis_trace(result: dict[str, object]) -> list[dict[str, object]]:
    provided_ledger = result.get("hypothesis_evidence_ledger", []) if isinstance(result, dict) else []
    if isinstance(provided_ledger, list) and provided_ledger:
        return [item for item in provided_ledger if isinstance(item, dict)]

    hypotheses = result.get("research_hypotheses", []) if isinstance(result, dict) else []
    investigation_reports = result.get("investigation_reports", []) if isinstance(result, dict) else []
    tutor_notes = result.get("tutor_research", []) if isinstance(result, dict) else []
    expected_vs_observed = result.get("expected_vs_observed", {}) if isinstance(result, dict) else {}
    missing = set(expected_vs_observed.get("missing_expected", []) if isinstance(expected_vs_observed, dict) else [])
    consensus = result.get("consensus", {}) if isinstance(result, dict) else {}
    consensus_class = str(consensus.get("classification") or "unknown")
    traces: list[dict[str, object]] = []

    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict):
            continue
        subsystem = str(hypothesis.get("missing_subsystem") or "")
        report = next(
            (
                item
                for item in investigation_reports
                if isinstance(item, dict) and subsystem and subsystem.lower() in str(item.get("subsystem") or "").lower()
            ),
            None,
        )
        note = next(
            (
                item
                for item in tutor_notes
                if isinstance(item, dict) and subsystem and subsystem.lower() in str(item.get("subsystem") or item.get("concept") or "").lower()
            ),
            None,
        )

        status = "surfaced"
        lifecycle = ["surfaced"]
        if report:
            status = "tested"
            lifecycle.append("tested")
        if note and not bool(note.get("verified")):
            status = "pending_verification"
            lifecycle.append("pending_verification")
        risk_signal = str((report or {}).get("overall_risk_signal") or "").lower()
        if "critical" in risk_signal or "high" in risk_signal:
            status = "risk_flagged"
            lifecycle.append("risk_flagged")
        elif consensus_class == "survives" and subsystem not in missing:
            status = "provisionally_supported"
            lifecycle.append("provisionally_supported")
        elif consensus_class == "survives":
            status = "unresolved"
            lifecycle.append("unresolved")

        traces.append(
            {
                "hypothesis_id": hypothesis.get("hypothesis_id"),
                "title": hypothesis.get("title"),
                "subsystem": subsystem,
                "status": status,
                "lifecycle": lifecycle,
                "rationale": hypothesis.get("rationale"),
                "evidence_needed": hypothesis.get("evidence_needed", []),
                "risk_signal": (report or {}).get("overall_risk_signal"),
                "investigation_tasks": (report or {}).get("investigation_tasks", []),
                "adversarial_hypotheses": (report or {}).get("adversarial_hypotheses", []),
                "tutor_summary": (note or {}).get("summary"),
                "tutor_verified": bool((note or {}).get("verified")) if note else None,
            }
        )
    return traces


def _build_terminal_log(result: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append(f"[{_utc_now()}] Halyx launch completed")
    repository_context = result.get("repository_context", {}) if isinstance(result, dict) else {}
    if isinstance(repository_context, dict):
        lines.append(f"[context] repository={repository_context.get('repository_path', 'unknown')}")
    methodology = result.get("methodology", {}) if isinstance(result, dict) else {}
    phases = methodology.get("phases", []) if isinstance(methodology, dict) else []
    for phase in phases:
        if isinstance(phase, dict):
            summary = _sanitize_summary_text(str(phase.get("summary", "")))
            lines.append(f"[phase] {phase.get('name', 'unknown')} :: {phase.get('status', 'unknown')} :: {summary}")
    planning = result.get("planning", {}) if isinstance(result, dict) else {}
    next_action = planning.get("next_action", {}) if isinstance(planning, dict) else {}
    if isinstance(next_action, dict):
        lines.append(
            f"[planner] action={next_action.get('action', 'unknown')} info_gain={next_action.get('expected_information_gain', 'n/a')}"
        )
    consensus = result.get("consensus", {}) if isinstance(result, dict) else {}
    if isinstance(consensus, dict):
        lines.append(f"[consensus] classification={consensus.get('classification', 'unknown')}")
    return "\n".join(lines)


def _build_tree_entries(root: Path, *, max_depth: int, max_entries: int) -> tuple[list[dict[str, object]], bool]:
    entries: list[dict[str, object]] = []
    truncated = False

    def visit(path: Path, depth: int) -> None:
        nonlocal truncated
        if truncated or len(entries) >= max_entries:
            truncated = True
            return
        relative = "." if path == root else str(path.relative_to(root))
        entries.append(
            {
                "path": relative,
                "type": "dir" if path.is_dir() else "file",
                "depth": depth,
                "size": path.stat().st_size if path.is_file() else None,
            }
        )
        if not path.is_dir() or depth >= max_depth:
            return
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        for child in children:
            if child.name.startswith(".git"):
                continue
            visit(child, depth + 1)

    visit(root, 0)
    return entries, truncated


def _candidate_result_paths() -> list[Path]:
    candidates: list[Path] = []
    env_value = os.getenv(RESULT_PATH_ENV)
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.extend(
        [
            Path.cwd() / "halyx_pipeline_result.json",
            Path(__file__).resolve().parents[3] / "halyx_pipeline_result.json",
        ]
    )
    return candidates


def _load_latest_result() -> dict[str, object] | None:
    for candidate in _candidate_result_paths():
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def _normalize_for_json(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_for_json(item) for item in value]
    if hasattr(value, "__dict__") and not isinstance(value, (str, bytes, int, float, bool, type(None))):
        return {str(key): _normalize_for_json(item) for key, item in vars(value).items() if not str(key).startswith("_")}
    return value


def _materialize_launch_result(result: object) -> dict[str, object]:
    if isinstance(result, dict):
        persistence = result.get("persistence")
        if isinstance(persistence, (str, Path)):
            persistence_path = Path(persistence).expanduser()
            if persistence_path.exists() and persistence_path.is_file():
                try:
                    payload = json.loads(persistence_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    payload = None
                if isinstance(payload, dict):
                    return payload
        normalized = _normalize_for_json(result)
        if isinstance(normalized, dict):
            return normalized
    return {}


def _summarize_hypothesis_outcomes(result: dict[str, object]) -> dict[str, object]:
    ledger = result.get("hypothesis_evidence_ledger", []) if isinstance(result, dict) else []
    if not isinstance(ledger, list):
        ledger = []

    supported = 0
    disproved = 0
    unresolved = 0
    for item in ledger:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        execution_case = item.get("execution_case") if isinstance(item.get("execution_case"), dict) else {}
        execution_status = str(execution_case.get("status") or "")
        if status == "supported" or execution_status in {"supported_by_execution"}:
            supported += 1
        elif status == "disproved" or execution_status == "falsification_triggered":
            disproved += 1
        elif status == "untested" or execution_status == "untested":
            unresolved += 1
        else:
            unresolved += 1

    return {
        "supported": supported,
        "disproved": disproved,
        "unresolved": unresolved,
    }


def _summarize_falsification(result: dict[str, object]) -> dict[str, object]:
    falsification_execution = result.get("falsification_execution", {}) if isinstance(result, dict) else {}
    if not isinstance(falsification_execution, dict):
        falsification_execution = {}

    cases = falsification_execution.get("cases", []) if isinstance(falsification_execution, dict) else []
    if not isinstance(cases, list):
        cases = []

    supported = sum(1 for case in cases if isinstance(case, dict) and case.get("status") in {"supported_by_execution"})
    disproved = sum(1 for case in cases if isinstance(case, dict) and case.get("status") == "falsification_triggered")
    unresolved = len(cases) - supported - disproved
    mode = str(falsification_execution.get("mode") or "n/a")
    reason = str(falsification_execution.get("reason") or "")

    summary = f"Foundry harness {mode} executed with {len(cases)} case(s)."
    if reason:
        summary = f"{summary} Reason: {reason}"
    if supported or disproved:
        summary = f"{summary} Outcomes: supported {supported}, disproved {disproved}, unresolved {unresolved}."

    return {
        "mode": mode,
        "case_count": len(cases),
        "supported": supported,
        "disproved": disproved,
        "unresolved": unresolved,
        "summary": summary,
        "executed": bool(falsification_execution.get("executed")),
        "return_code": falsification_execution.get("return_code"),
        "passed": falsification_execution.get("passed"),
    }


def _build_dashboard_payload_from_result(
    *,
    result: dict[str, object],
    runs: list[dict[str, object]],
    latest_run_id: str | None,
) -> dict[str, object]:
    subsystem_plan = result.get("subsystem_plan", {}) if isinstance(result, dict) else {}
    reconstructions = subsystem_plan.get("reconstructions", []) if isinstance(subsystem_plan, dict) else []
    falsification_execution = result.get("falsification_execution", {}) if isinstance(result, dict) else {}
    if not isinstance(falsification_execution, dict) or not falsification_execution:
        falsification_execution = {
            "mode": "not_recorded",
            "executed": False,
            "cases": [],
            "reason": "This run artifact did not include falsification execution details.",
        }
    return {
        "status": "ready",
        "repository_context": result.get("repository_context", {}),
        "methodology": result.get("methodology", {}),
        "protocol_pattern": result.get("protocol_pattern", {}),
        "expected_protocol_model": result.get("expected_protocol_model", {}),
        "expected_vs_observed": result.get("expected_vs_observed", {}),
        "planning": result.get("planning", {}),
        "tutor_research": result.get("tutor_research", []),
        "verification_reports": result.get("verification_reports", []),
        "semantic_dossiers": result.get("semantic_dossiers", []),
        "investigation_reports": result.get("investigation_reports", []),
        "research_hypotheses": result.get("research_hypotheses", []),
        "hypothesis_evidence_ledger": result.get("hypothesis_evidence_ledger", []),
        "subsystems": reconstructions,
        "reasoning": result.get("reasoning", {}),
        "falsification_execution": falsification_execution,
        "hypothesis_outcomes": _summarize_hypothesis_outcomes(result),
        "falsification_summary": _summarize_falsification(result),
        "hypothesis_evidence_objects": result.get("hypothesis_evidence_objects", []),
        "training": result.get("training", {}),
        "consensus": result.get("consensus", {}),
        "consensus_explain": _summarize_consensus(result),
        "hypothesis_trace": _build_hypothesis_trace(result),
        "evidence_graph": result.get("evidence_graph", {}),
        "protocol_reconstruction": result.get("protocol_reconstruction", {}),
        "protocol_semantics": result.get("protocol_semantics", {}),
        "runs": runs[:20],
        "latest_run_id": latest_run_id,
    }


class LaunchRequest(BaseModel):
    target: str = Field(..., description="Protocol name, repository reference, or contract address")
    scope: str | None = Field(default=None, description="Optional audit scope hint")
    chain: str = Field(default="ethereum", description="Chain name or chain id for acquisition")
    output: str | None = Field(default=None, description="Optional destination for fetched sources")
    source_code: str | None = Field(default=None, description="Optional pasted Solidity source text")
    etherscan_api_key: str | None = Field(default=None, description="Primary Etherscan API key for source acquisition")
    etherscan_api_key_alt: str | None = Field(default=None, description="Alternate Etherscan API key for fallback acquisition")


class EnvWriteRequest(BaseModel):
    file_name: str = Field(default=".env", description="Environment file name at repository root")
    fork_test_rpc_url: str | None = Field(default=None, description="Value for FORK_TEST_RPC_URL")
    rpc_url: str | None = Field(default=None, description="Value for RPC_URL")
    alchemy_api_key: str | None = Field(default=None, description="Value for ALCHEMY_API_KEY")
    etherscan_api_key: str | None = Field(default=None, description="Value for ETHERSCAN_API_KEY")
    etherscan_api_key_alt: str | None = Field(default=None, description="Value for ETHERSCAN_API_KEY_ALT")


class RunFileUpdateRequest(BaseModel):
    path: str = Field(..., description="Path relative to selected run repository")
    content: str = Field(..., description="New file content")


def _build_default_eir(protocol_name: str):
    from quantum_economic_auditor.models.eir import (
        EconomicAction,
        EconomicIntermediateRepresentation,
        EconomicInvariant,
        EconomicObjective,
        EconomicRelationship,
        EconomicVariable,
    )

    return EconomicIntermediateRepresentation(
        protocol_name=protocol_name,
        variables=[EconomicVariable(name="Collateral", category="collateral")],
        actions=[EconomicAction(name="Borrow", kind="borrow")],
        relationships=[EconomicRelationship(source="Collateral", relation="collateralizes", target="Borrow")],
        invariants=[EconomicInvariant(name="Collateralization", kind="collateralization", expression="Collateral >= 0")],
        objectives=[EconomicObjective(name="Profit", kind="profit", expression="Collateral", weight=1.0)],
    )


def _sanitize_summary_text(value: str, *, max_length: int = 260) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if len(compact) <= max_length:
        return compact
    return f"{compact[:max_length - 1]}..."


def _sanitize_terminal_line(line: str) -> str:
    if not line.startswith("[phase]"):
        return line
    parts = line.split("::", 2)
    if len(parts) != 3:
        return _sanitize_summary_text(line, max_length=320)
    prefix = f"{parts[0].strip()} :: {parts[1].strip()}"
    summary = _sanitize_summary_text(parts[2], max_length=260)
    return f"{prefix} :: {summary}"


def _resolve_run_repository_path(run_id: str) -> Path:
    if run_id == "latest_artifact":
        latest = _load_latest_result() or {}
        repository_context = latest.get("repository_context", {}) if isinstance(latest.get("repository_context"), dict) else {}
        repository_path = Path(str(repository_context.get("repository_path") or "")).expanduser()
    else:
        run = _get_run_record(run_id)
        repository_path = Path(str(run.get("repository_path") or "")).expanduser()

    if not repository_path.exists() or not repository_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Repository path not found for run '{run_id}'")
    return repository_path.resolve()


def _resolve_repo_relative_file(repository_path: Path, relative_path: str) -> Path:
    rel = relative_path.strip().replace("\\", "/")
    if not rel or rel.startswith("/"):
        raise HTTPException(status_code=400, detail="File path must be a non-empty repository-relative path")
    candidate = (repository_path / rel).resolve()
    if not _is_under_root(candidate, repository_path):
        raise HTTPException(status_code=400, detail="File path escapes repository root")
    return candidate


def _load_run_dashboard_result(run_id: str) -> dict[str, object]:
    if run_id == "latest_artifact":
        return _load_latest_result() or {}
    run = _get_run_record(run_id)
    dashboard_path = Path(str(run.get("dashboard_path") or "")).expanduser()
    if dashboard_path.exists() and dashboard_path.is_file():
        try:
            payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return _load_latest_result() or {}


def _resolve_fork_rpc_for_repo(repository_path: Path) -> tuple[str, str]:
    resolver = FalsificationExecutionEngine()
    value, source = resolver._discover_fork_rpc(repository_path)  # noqa: SLF001
    if value:
        return value, source or "resolver"
    return "https://rpc.mevblocker.io", "fallback:mevblocker"


def _analyze_poc_output(*, stdout: str, stderr: str, return_code: int) -> dict[str, object]:
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    output = f"{stdout}\n{stderr}"
    pass_matches = _unique(re.findall(r"\[PASS\]\s+([A-Za-z0-9_]+\(\))", output))
    fail_matches = _unique(re.findall(r"\[FAIL(?:[^\]]*)\]\s+([A-Za-z0-9_]+\(\))", output))
    fail_reason_matches = re.findall(r"\[FAIL:\s*([^\]]+)\]\s+([A-Za-z0-9_]+\(\))", output)

    reason_by_test: dict[str, str] = {test_name: reason for reason, test_name in fail_reason_matches}
    validation_miss = [
        test_name
        for test_name in fail_matches
        if "could not be validated on fork state" in reason_by_test.get(test_name, "").lower()
    ]
    synthetic_inconclusive = [
        test_name
        for test_name in fail_matches
        if "halyx_inconclusive_synthetic:" in reason_by_test.get(test_name, "").lower()
    ]
    reachability_failed = [
        test_name
        for test_name in fail_matches
        if "halyx_reachability_failed:" in reason_by_test.get(test_name, "").lower()
    ]
    flashloan_assumption_gap = [
        test_name
        for test_name in fail_matches
        if "halyx_assumption_flashloan_not_reproduced:" in reason_by_test.get(test_name, "").lower()
    ]
    economic_impact_not_confirmed = [
        test_name
        for test_name in fail_matches
        if "halyx_economic_impact_not_confirmed:" in reason_by_test.get(test_name, "").lower()
    ]
    behavior_not_observed = [
        test_name
        for test_name in fail_matches
        if "halyx_behavior_not_observed:" in reason_by_test.get(test_name, "").lower()
    ]
    economic_effect_not_observed = [
        test_name
        for test_name in fail_matches
        if "halyx_economic_effect_not_observed:" in reason_by_test.get(test_name, "").lower()
    ]
    reconciliation_failed = [
        test_name
        for test_name in fail_matches
        if "halyx_economic_reconciliation_failed:" in reason_by_test.get(test_name, "").lower()
    ]

    compile_or_toolchain_error = (
        "compilation failed" in output.lower()
        or "compiler run failed" in output.lower()
        or "invalid solc version" in output.lower()
    )
    marker_only = all(
        (
            "halyx_exploit_sequence_confirmed" in (reason_by_test.get(test_name, "").lower())
            or "halyx_test_completed" in (reason_by_test.get(test_name, "").lower())
        )
        for test_name in fail_matches
    ) if fail_matches else False

    if compile_or_toolchain_error:
        implication = "inconclusive_toolchain"
        explanation = "POC failed due to compilation/toolchain issues, so hypothesis outcomes are inconclusive."
    elif marker_only:
        implication = "inconclusive_marker_only"
        explanation = "Output contained marker strings without independent invariant/economic evidence; marker-only outcomes are inconclusive."
    elif return_code == 0:
        implication = "supported_by_execution"
        explanation = "POC checks passed on the selected fork state, which supports the tested hypotheses under current assertions."
    elif fail_matches and len(reachability_failed) == len(fail_matches):
        implication = "reachability_failed"
        explanation = "Modeled attack path prerequisites were not reachable in execution (capital/permission/state constraints blocked the sequence)."
    elif fail_matches and len(flashloan_assumption_gap) == len(fail_matches):
        implication = "assumption_gap_flashloan"
        explanation = "Hypothesis requires flashloan capital but the borrow/repay lender mechanism was not behaviorally reproduced."
    elif fail_matches and len(economic_impact_not_confirmed) == len(fail_matches):
        implication = "economic_impact_not_confirmed"
        explanation = "Attack sequence executed but predicted economic impact was not confirmed by post-state math assertions."
    elif fail_matches and len(behavior_not_observed) == len(fail_matches):
        implication = "behavior_not_observed"
        explanation = "Reachable calls executed but the hypothesis-claimed state transition/invariant movement was not observed."
    elif fail_matches and len(economic_effect_not_observed) == len(fail_matches):
        implication = "economic_effect_not_observed"
        explanation = "A behavioral transition signal was present, but the claimed economic extraction/effect was not observed."
    elif fail_matches and len(reconciliation_failed) == len(fail_matches):
        implication = "inconclusive_reconciliation"
        explanation = "Observed movement could not be economically reconciled between attacker/protocol ledgers."
    elif fail_matches and len(synthetic_inconclusive) == len(fail_matches):
        implication = "inconclusive_synthetic_execution"
        explanation = (
            "Execution reached target contracts but produced no measurable post-state or economic movement. "
            "This is synthetic/inconclusive evidence, not exploit confirmation and not hypothesis disproval."
        )
    elif fail_matches and len(validation_miss) == len(fail_matches):
        implication = "inconclusive_target_validation"
        explanation = (
            "All failures were target-validation misses (e.g., could not validate addresses/functions on fork state). "
            "This is not strong evidence that hypotheses are disproved."
        )
    elif fail_matches:
        implication = "potential_falsification"
        explanation = "One or more hypothesis tests failed with behavioral assertions; this can indicate potential hypothesis falsification."
    else:
        implication = "execution_unknown"
        explanation = "POC ended unsuccessfully but no test-level pass/fail pattern was detected."

    if implication in {"supported_by_execution"}:
        verdict = "PASS"
    elif implication in {
        "inconclusive_toolchain",
        "inconclusive_synthetic_execution",
        "inconclusive_target_validation",
        "inconclusive_reconciliation",
        "inconclusive_marker_only",
        "execution_unknown",
    }:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "FAIL"

    return {
        "verdict": verdict,
        "implication": implication,
        "explanation": explanation,
        "passed_tests": pass_matches,
        "failed_tests": fail_matches,
        "failed_reasons": [{"test_name": test_name, "reason": reason_by_test.get(test_name)} for test_name in fail_matches],
        "target_validation_miss_tests": validation_miss,
        "synthetic_inconclusive_tests": synthetic_inconclusive,
        "reachability_failed_tests": reachability_failed,
        "flashloan_assumption_gap_tests": flashloan_assumption_gap,
        "economic_impact_not_confirmed_tests": economic_impact_not_confirmed,
        "behavior_not_observed_tests": behavior_not_observed,
        "economic_effect_not_observed_tests": economic_effect_not_observed,
        "reconciliation_failed_tests": reconciliation_failed,
        "compile_or_toolchain_error": compile_or_toolchain_error,
    }


def _upsert_env_line(lines: list[str], key: str, value: str) -> list[str]:
    replacement = f"{key}={value}"
    updated = False
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") and not updated:
            output.append(replacement)
            updated = True
        else:
            output.append(line)
    if not updated:
        output.append(replacement)
    return output


def _load_repo_env_pairs(repository_path: Path) -> dict[str, str]:
    env_files = [
        repository_path / ".env",
        repository_path / ".env.local",
        repository_path / ".env.deploy",
        repository_path / ".env.deploy.local",
        repository_path / ".env.example",
        repository_path / ".env.deploy.example",
        repository_path / ".env.L2.example",
    ]
    pairs: dict[str, str] = {}
    for file_path in env_files:
        if not file_path.exists() or not file_path.is_file():
            continue
        for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in pairs:
                pairs[key] = value
    return pairs


def _global_config_path() -> Path:
    return _runs_root() / "config.json"


def _load_global_config() -> dict[str, object]:
    path = _global_config_path()
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_global_config(config: dict[str, object]) -> None:
    _global_config_path().write_text(json.dumps(config, indent=2), encoding="utf-8")


def _persist_global_explorer_keys(*, etherscan_api_key: str | None, etherscan_api_key_alt: str | None) -> None:
    primary = (etherscan_api_key or "").strip()
    alternate = (etherscan_api_key_alt or "").strip()
    if not primary and not alternate:
        return

    config = _load_global_config()
    explorer = config.get("explorer") if isinstance(config.get("explorer"), dict) else {}
    if primary:
        explorer["etherscan_api_key"] = primary
    if alternate:
        explorer["etherscan_api_key_alt"] = alternate
    config["explorer"] = explorer
    _save_global_config(config)


def _resolve_effective_explorer_keys(*, etherscan_api_key: str | None, etherscan_api_key_alt: str | None) -> tuple[str | None, str | None]:
    explicit_primary = (etherscan_api_key or "").strip() or None
    explicit_alt = (etherscan_api_key_alt or "").strip() or None

    if explicit_primary or explicit_alt:
        return explicit_primary, explicit_alt

    env_primary = (os.getenv("ETHERSCAN_API_KEY") or "").strip() or None
    env_alt = (os.getenv("ETHERSCAN_API_KEY_ALT") or "").strip() or None
    if env_primary or env_alt:
        return env_primary, env_alt

    config = _load_global_config()
    explorer = config.get("explorer") if isinstance(config.get("explorer"), dict) else {}
    stored_primary = str(explorer.get("etherscan_api_key") or "").strip() or None
    stored_alt = str(explorer.get("etherscan_api_key_alt") or "").strip() or None
    return stored_primary, stored_alt


def _persist_launch_explorer_keys(repository_path: Path, *, etherscan_api_key: str | None, etherscan_api_key_alt: str | None) -> None:
    updates: list[tuple[str, str]] = []
    if etherscan_api_key and etherscan_api_key.strip():
        updates.append(("ETHERSCAN_API_KEY", etherscan_api_key.strip()))
    if etherscan_api_key_alt and etherscan_api_key_alt.strip():
        updates.append(("ETHERSCAN_API_KEY_ALT", etherscan_api_key_alt.strip()))
    if not updates:
        return

    env_path = (repository_path / ".env.local").resolve()
    existing = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    lines = existing[:]
    for key, value in updates:
        lines = _upsert_env_line(lines, key, value)
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


@contextmanager
def _temporary_env(updates: dict[str, str | None]):
    previous: dict[str, object] = {}
    sentinel = object()
    try:
        for key, value in updates.items():
            previous[key] = os.environ.get(key, sentinel)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)


def _resolve_repository_input(
    value: str,
    *,
    chain: str | None = None,
    output_root: str | None = None,
    etherscan_api_key: str | None = None,
    etherscan_api_key_alt: str | None = None,
) -> Path:
    agent = SourceAcquisitionAgent(api_key=etherscan_api_key, api_key_alt=etherscan_api_key_alt)
    try:
        result = agent.resolve_input(
            value,
            chain=chain,
            output_root=Path(output_root).resolve() if output_root else None,
        )
    except SourceAcquisitionError as error:
        raise ValueError(str(error)) from error
    return result.source_root


def _build_dashboard_payload() -> dict[str, object]:
    result = _load_latest_result()
    run_index = _load_runs_index()
    runs = [item for item in run_index.get("runs", []) if isinstance(item, dict)]
    latest_run_id = run_index.get("latest_run_id")

    if not runs and isinstance(result, dict):
        repository_context = result.get("repository_context", {}) if isinstance(result.get("repository_context"), dict) else {}
        repository_path = str(repository_context.get("repository_path") or "").strip()
        if repository_path:
            synthetic_id = "latest_artifact"
            runs = [
                {
                    "run_id": synthetic_id,
                    "started_at": _utc_now(),
                    "target": Path(repository_path).name,
                    "scope": None,
                    "chain": "unknown",
                    "repository_path": repository_path,
                    "consensus": str((result.get("consensus") or {}).get("classification") or "unknown"),
                    "methodology_phases": len(((result.get("methodology") or {}).get("phases") or [])),
                    "planner_action": ((result.get("planning") or {}).get("next_action") or {}).get("action"),
                    "run_dir": str(_run_dir(synthetic_id)),
                    "synthetic": True,
                }
            ]
            latest_run_id = synthetic_id

    if result is None:
        return {
            "status": "idle",
            "message": "No analysis artifact has been generated yet.",
            "repository_context": {},
            "protocol_pattern": {},
            "expected_vs_observed": {},
            "planning": {},
            "tutor_research": [],
            "verification_reports": [],
            "investigation_reports": [],
            "research_hypotheses": [],
            "subsystems": [],
            "reasoning": {},
            "falsification_execution": {},
            "methodology": {},
            "hypothesis_trace": [],
            "consensus_explain": {},
            "training": {},
            "runs": runs[:20],
            "latest_run_id": latest_run_id,
        }

    selected_result = result
    if latest_run_id:
        selected_run = next((run for run in runs if str(run.get("run_id") or "") == str(latest_run_id)), None)
        dashboard_path = Path(str((selected_run or {}).get("dashboard_path") or "")).expanduser()
        if dashboard_path.exists() and dashboard_path.is_file():
            try:
                selected_result = json.loads(dashboard_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                selected_result = result

    return _build_dashboard_payload_from_result(result=selected_result, runs=runs, latest_run_id=latest_run_id)


@app.get("/", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Halyx UI unavailable</h1>", status_code=503)


@app.get("/api/dashboard")
def dashboard() -> dict[str, object]:
    return _build_dashboard_payload()


def _execute_launch_request(*, request: LaunchRequest) -> dict[str, object]:
    run_id = uuid4().hex[:12]
    started_at = _utc_now()
    source_input = request.source_code if request.source_code and request.source_code.strip() else request.target
    effective_primary, effective_alt = _resolve_effective_explorer_keys(
        etherscan_api_key=request.etherscan_api_key,
        etherscan_api_key_alt=request.etherscan_api_key_alt,
    )
    _persist_global_explorer_keys(etherscan_api_key=effective_primary, etherscan_api_key_alt=effective_alt)
    try:
        repository_path = _resolve_repository_input(
            source_input,
            chain=request.chain,
            output_root=request.output,
            etherscan_api_key=effective_primary,
            etherscan_api_key_alt=effective_alt,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _persist_launch_explorer_keys(
        repository_path,
        etherscan_api_key=effective_primary,
        etherscan_api_key_alt=effective_alt,
    )
    eir = _build_default_eir(repository_path.name)
    env_updates: dict[str, str | None] = {
        "ETHERSCAN_API_KEY": effective_primary,
        "ETHERSCAN_API_KEY_ALT": effective_alt,
        "ETHERSCAN_API_KEYS": ",".join(
            value
            for value in [
                effective_primary,
                effective_alt,
            ]
            if value
        ) or None,
        "HALYX_FORK_CHAIN": request.chain.strip() if request.chain.strip() else "ethereum",
        "HALYX_REQUIRE_VERIFIED_TARGETS": "1",
    }
    with _temporary_env(env_updates):
        orchestrator = HalyxOrchestrator()
        result = orchestrator.run(repository_path=repository_path, eir=eir, program_scope=request.scope or request.target)

    latest_result = _materialize_launch_result(result)
    if not isinstance(latest_result, dict):
        latest_result = {}
    if not latest_result.get("repository_context"):
        latest_result["repository_context"] = {"repository_path": str(repository_path)}

    final_repo_paths = {repository_path.resolve()}
    repository_context = latest_result.get("repository_context", {}) if isinstance(latest_result, dict) else {}
    context_repo_path = Path(str(repository_context.get("repository_path") or "")).expanduser()
    if context_repo_path.exists() and context_repo_path.is_dir():
        final_repo_paths.add(context_repo_path.resolve())
    for repo_path in final_repo_paths:
        _persist_launch_explorer_keys(
            repo_path,
            etherscan_api_key=effective_primary,
            etherscan_api_key_alt=effective_alt,
        )

    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = run_dir / "dashboard.json"
    dashboard_path.write_text(json.dumps(latest_result, indent=2), encoding="utf-8")
    dashboard_payload = _build_dashboard_payload_from_result(result=latest_result, runs=[], latest_run_id=run_id)
    terminal_log = _build_terminal_log(dashboard_payload)
    (run_dir / "terminal.log").write_text(terminal_log, encoding="utf-8")
    report_path_obj = result.get("report_path")
    report_path_str = str(report_path_obj) if report_path_obj else ""

    falsification_execution = dashboard_payload.get("falsification_execution", {}) if isinstance(dashboard_payload, dict) else {}
    record = {
        "run_id": run_id,
        "started_at": started_at,
        "target": request.target,
        "scope": request.scope,
        "chain": request.chain,
        "repository_path": str(repository_path),
        "consensus": result["consensus"].classical_classification.value,
        "methodology_phases": result["methodology"].phase_count,
        "planner_action": dashboard_payload.get("planning", {}).get("next_action", {}).get("action"),
        "falsification_mode": falsification_execution.get("mode"),
        "falsification_cases": len(falsification_execution.get("cases", []) if isinstance(falsification_execution, dict) else []),
        "dashboard_path": str(dashboard_path),
        "report_path": report_path_str,
        "run_dir": str(run_dir),
    }
    (run_dir / "metadata.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    _upsert_run(record)

    return {
        "run_id": run_id,
        "repository_path": str(repository_path),
        "protocol": repository_path.name,
        "methodology_phases": result["methodology"].phase_count,
        "consensus": result["consensus"].classical_classification.value,
        "report_path": report_path_str,
        "dashboard": _build_dashboard_payload(),
    }


@app.post("/api/launch")
def launch(request: LaunchRequest) -> dict[str, object]:
    return _execute_launch_request(request=request)


@app.get("/api/runs")
def list_runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, object]:
    index = _load_runs_index()
    runs = [item for item in index.get("runs", []) if isinstance(item, dict)]
    return {
        "latest_run_id": index.get("latest_run_id"),
        "runs": runs[:limit],
    }


@app.get("/api/runs/{run_id}/tree")
def run_tree(
    run_id: str,
    max_depth: int = Query(default=5, ge=1, le=12),
    max_entries: int = Query(default=1200, ge=50, le=10000),
) -> dict[str, object]:
    repository_path = _resolve_run_repository_path(run_id)
    entries, truncated = _build_tree_entries(repository_path, max_depth=max_depth, max_entries=max_entries)
    return {
        "run_id": run_id,
        "repository_path": str(repository_path),
        "entry_count": len(entries),
        "truncated": truncated,
        "entries": entries,
    }


@app.get("/api/runs/{run_id}/terminal")
def run_terminal(run_id: str, tail: int = Query(default=400, ge=1, le=5000)) -> dict[str, object]:
    if run_id == "latest_artifact":
        latest = _load_latest_result() or {}
        text = _build_terminal_log(_build_dashboard_payload_from_result(result=latest, runs=[], latest_run_id=run_id))
        lines = text.splitlines()
        sliced = lines[-tail:]
        return {
            "run_id": run_id,
            "line_count": len(lines),
            "lines": sliced,
            "text": "\n".join(sliced),
        }

    run = _get_run_record(run_id)
    run_dir = Path(str(run.get("run_dir") or _run_dir(run_id))).expanduser()
    log_path = run_dir / "terminal.log"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"No terminal log found for run '{run_id}'")
    lines = [_sanitize_terminal_line(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    sliced = lines[-tail:]
    return {
        "run_id": run_id,
        "line_count": len(lines),
        "lines": sliced,
        "text": "\n".join(sliced),
    }


@app.get("/api/runs/{run_id}/file")
def run_file_get(run_id: str, path: str = Query(..., description="Repository-relative file path")) -> dict[str, object]:
    repository_path = _resolve_run_repository_path(run_id)
    file_path = _resolve_repo_relative_file(repository_path, path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "run_id": run_id,
        "repository_path": str(repository_path),
        "path": str(file_path.relative_to(repository_path)),
        "content": text,
        "size": len(text.encode("utf-8")),
    }


@app.put("/api/runs/{run_id}/file")
def run_file_put(run_id: str, request: RunFileUpdateRequest) -> dict[str, object]:
    repository_path = _resolve_run_repository_path(run_id)
    file_path = _resolve_repo_relative_file(repository_path, request.path)
    if file_path.exists() and file_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is a directory: {request.path}")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(request.content, encoding="utf-8")
    return {
        "run_id": run_id,
        "repository_path": str(repository_path),
        "path": str(file_path.relative_to(repository_path)),
        "bytes_written": len(request.content.encode("utf-8")),
    }


@app.get("/api/runs/{run_id}/report")
def run_report(run_id: str) -> dict[str, object]:
    """Return the markdown report for a run, generating it on demand if not yet present."""
    if run_id == "latest_artifact":
        result = _load_latest_result() or {}
        report_path_str = ""
    else:
        run = _get_run_record(run_id)
        report_path_str = str(run.get("report_path") or "")
        result = _load_run_dashboard_result(run_id)

    # Try the path recorded in the run record first.
    if report_path_str:
        p = Path(report_path_str).expanduser()
        if p.exists() and p.is_file():
            return {"run_id": run_id, "report_path": str(p), "content": p.read_text(encoding="utf-8")}

    # Regenerate from the dashboard payload.
    if not result:
        raise HTTPException(status_code=404, detail=f"No pipeline artifact found for run '{run_id}'")

    from quantum_economic_auditor.report.report_generator import AuditReportGenerator
    gen = AuditReportGenerator()
    out_dir = _run_dir(run_id) / "reports"
    report_path = gen.generate(result, output_dir=out_dir)

    if run_id != "latest_artifact":
        try:
            run = _get_run_record(run_id)
            run["report_path"] = str(report_path)
            _upsert_run(run)
        except HTTPException:
            pass

    return {"run_id": run_id, "report_path": str(report_path), "content": report_path.read_text(encoding="utf-8")}


@app.post("/api/runs/{run_id}/report/regenerate")
def regenerate_report(run_id: str) -> dict[str, object]:
    """Force-regenerate the report for a run from its current pipeline artifact."""
    result = _load_run_dashboard_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"No pipeline artifact for run '{run_id}'")

    from quantum_economic_auditor.report.report_generator import AuditReportGenerator
    gen = AuditReportGenerator()
    out_dir = _run_dir(run_id) / "reports"
    report_path = gen.generate(result, output_dir=out_dir)

    try:
        run = _get_run_record(run_id)
        run["report_path"] = str(report_path)
        _upsert_run(run)
    except HTTPException:
        pass

    return {"run_id": run_id, "report_path": str(report_path), "content": report_path.read_text(encoding="utf-8")}


@app.post("/api/runs/{run_id}/poc-run")
def run_poc_now(run_id: str) -> dict[str, object]:
    run = _get_run_record(run_id)
    repository_path = _resolve_run_repository_path(run_id)
    result_payload = _load_run_dashboard_result(run_id)
    hypothesis_ledger = result_payload.get("hypothesis_evidence_ledger", []) if isinstance(result_payload, dict) else []
    if not isinstance(hypothesis_ledger, list) or not hypothesis_ledger:
        hypotheses = result_payload.get("research_hypotheses", []) if isinstance(result_payload, dict) else []
        hypothesis_ledger = [item for item in hypotheses if isinstance(item, dict)] if isinstance(hypotheses, list) else []
    if not hypothesis_ledger:
        raise HTTPException(status_code=400, detail="No hypothesis evidence was recorded for this run")

    env_pairs = _load_repo_env_pairs(repository_path)
    etherscan_keys: list[str] = []
    for key_name in ["ETHERSCAN_API_KEY", "ETHERSCAN_API_KEY_ALT", "ETHERSCAN_API_TOKEN"]:
        value = env_pairs.get(key_name) or os.getenv(key_name)
        if value and value.strip():
            etherscan_keys.append(value.strip())
    for value in re.split(r"[\n,;]+", env_pairs.get("ETHERSCAN_API_KEYS", "")):
        if value and value.strip():
            etherscan_keys.append(value.strip())
    fork_rpc_url, fork_source = _resolve_fork_rpc_for_repo(repository_path)
    chain = str(run.get("chain") or "ethereum")

    with _temporary_env({
        "HALYX_FORK_RPC_URL": fork_rpc_url,
        "HALYX_FORK_CHAIN": chain,
        "HALYX_REQUIRE_VERIFIED_TARGETS": "1",
    }):
        engine = FalsificationExecutionEngine(fork_rpc_url=fork_rpc_url, etherscan_api_keys=etherscan_keys or None)
        fresh_execution = engine.execute(repository_path=repository_path, hypothesis_ledger=hypothesis_ledger, chain=chain)

    if not fresh_execution.executed or not fresh_execution.command:
        raise HTTPException(status_code=400, detail=fresh_execution.reason or "No verified targets were available for a fresh POC run")

    stdout = fresh_execution.stdout_tail or ""
    stderr = fresh_execution.stderr_tail or ""
    fresh_return_code = getattr(fresh_execution, "return_code", getattr(fresh_execution, "returncode", None))
    return_code = int(fresh_return_code if fresh_return_code is not None else 1)
    passed = bool(fresh_execution.passed)
    analysis = _analyze_poc_output(stdout=stdout, stderr=stderr, return_code=return_code)
    poc_verdict = str(analysis.get("verdict") or ("PASS" if passed else "FAIL"))
    lines = [
        f"[poc] run_id={run_id}",
        f"[poc] harness_dir={fresh_execution.harness_dir}",
        f"[poc] command={' '.join(str(part) for part in fresh_execution.command)}",
        f"[poc] fork_rpc_source={fresh_execution.fork_rpc_source or fork_source}",
        f"[poc] return_code={return_code}",
        f"[poc] verdict={poc_verdict}",
        f"[poc] implication={analysis.get('implication')}",
        f"[poc] explanation={analysis.get('explanation')}",
        f"[poc] passed_tests={len(analysis.get('passed_tests', []))}",
        f"[poc] failed_tests={len(analysis.get('failed_tests', []))}",
        "[poc] stdout_tail:",
        *stdout.splitlines()[-120:],
    ]
    if stderr.strip():
        lines.extend(["[poc] stderr_tail:", *stderr.splitlines()[-120:]])

    return {
        "run_id": run_id,
        "repository_path": str(repository_path),
        "harness_dir": str(fresh_execution.harness_dir or ""),
        "command": fresh_execution.command,
        "fork_rpc_source": fresh_execution.fork_rpc_source or fork_source,
        "return_code": return_code,
        "passed": passed,
        "analysis": analysis,
        "stdout_tail": "\n".join(stdout.splitlines()[-120:]),
        "stderr_tail": "\n".join(stderr.splitlines()[-120:]),
        "terminal_text": "\n".join(lines),
    }


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str, delete_source_tree: bool = Query(default=False)) -> dict[str, object]:
    run = _drop_run_record(run_id)
    run_dir = Path(str(run.get("run_dir") or _run_dir(run_id))).expanduser()
    if run_dir.exists() and run_dir.is_dir():
        shutil.rmtree(run_dir)

    deleted_source_tree = False
    if delete_source_tree:
        source_path = Path(str(run.get("repository_path") or "")).expanduser().resolve()
        allowed_root = (Path.home() / ".halyx" / "sources").resolve()
        if not _is_under_root(source_path, allowed_root):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Source deletion is only allowed for repositories fetched under ~/.halyx/sources. "
                    "Run was removed, but source tree was preserved."
                ),
            )
        if source_path.exists() and source_path.is_dir():
            shutil.rmtree(source_path)
            deleted_source_tree = True

    return {
        "run_id": run_id,
        "deleted_run": True,
        "deleted_source_tree": deleted_source_tree,
    }


@app.post("/api/runs/{run_id}/env")
def write_run_env(run_id: str, request: EnvWriteRequest) -> dict[str, object]:
    run = _get_run_record(run_id)
    repository_path = Path(str(run.get("repository_path") or "")).expanduser().resolve()
    if not repository_path.exists() or not repository_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Repository path not found for run '{run_id}'")

    allowed_names = {".env", ".env.local", ".env.deploy", ".env.deploy.local"}
    file_name = request.file_name.strip()
    if file_name not in allowed_names:
        raise HTTPException(status_code=400, detail=f"Unsupported env file name '{file_name}'")

    env_path = (repository_path / file_name).resolve()
    if env_path.parent != repository_path:
        raise HTTPException(status_code=400, detail="Env file must be created in repository root")

    existing = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    lines = existing[:]

    updates: list[tuple[str, str]] = []
    if request.fork_test_rpc_url and request.fork_test_rpc_url.strip():
        updates.append(("FORK_TEST_RPC_URL", request.fork_test_rpc_url.strip()))
    if request.rpc_url and request.rpc_url.strip():
        updates.append(("RPC_URL", request.rpc_url.strip()))
    if request.alchemy_api_key and request.alchemy_api_key.strip():
        updates.append(("ALCHEMY_API_KEY", request.alchemy_api_key.strip()))
    if request.etherscan_api_key and request.etherscan_api_key.strip():
        updates.append(("ETHERSCAN_API_KEY", request.etherscan_api_key.strip()))
    if request.etherscan_api_key_alt and request.etherscan_api_key_alt.strip():
        updates.append(("ETHERSCAN_API_KEY_ALT", request.etherscan_api_key_alt.strip()))

    if not updates:
        raise HTTPException(status_code=400, detail="No env values provided to write")

    for key, value in updates:
        lines = _upsert_env_line(lines, key, value)

    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    _persist_global_explorer_keys(
        etherscan_api_key=request.etherscan_api_key,
        etherscan_api_key_alt=request.etherscan_api_key_alt,
    )
    return {
        "run_id": run_id,
        "repository_path": str(repository_path),
        "env_path": str(env_path),
        "updated_keys": [key for key, _ in updates],
    }


# ── Assistant ─────────────────────────────────────────────────────────────────

class AssistantMessageRequest(BaseModel):
    message: str = Field(..., description="User message or error text to reason about")
    context: str | None = Field(default=None, description="Optional pipeline context such as the failed step or error traceback")
    run_id: str | None = Field(default=None, description="Optional run ID so the assistant can inspect the current run state")
    chain: str = Field(default="ethereum", description="Chain name or chain id used when executing authoritative targets")
    scope: str | None = Field(default=None, description="Optional scope hint for execution")
    output: str | None = Field(default=None, description="Optional output root for acquisition artifacts")
    etherscan_api_key: str | None = Field(default=None, description="Primary Etherscan API key override")
    etherscan_api_key_alt: str | None = Field(default=None, description="Alternate Etherscan API key override")
    auto_execute: bool = Field(default=True, description="When true, authoritative targets are executed immediately")


_ASSISTANT_KNOWLEDGE: list[dict[str, str]] = [
    {
        "trigger": "scope_url",
        "reply": (
            "Scope-URL mode: Halyx will fetch the page, extract every 0x-prefixed address, "
            "and pull each contract's verified source from the block explorer. "
            "Paste the scope page URL directly into the 'Protocol name' field and choose the correct chain."
        ),
    },
    {
        "trigger": "etherscan",
        "reply": (
            "Block explorer fetch failed. Common causes: (1) the contract is not verified on Etherscan, "
            "(2) ETHERSCAN_API_KEY is missing or rate-limited, (3) you are on the wrong chain. "
            "Try setting ETHERSCAN_API_KEY and re-launching, or provide a GitHub repo URL instead."
        ),
    },
    {
        "trigger": "no verified source",
        "reply": (
            "No verified source code was found for this address. "
            "The contract may be unverified. You can manually provide the source by: "
            "(1) cloning from a known GitHub repository and passing that path, "
            "(2) uploading the contract source to the file editor, or "
            "(3) checking if there is a proxy implementation address to try instead."
        ),
    },
    {
        "trigger": "git clone failed",
        "reply": (
            "Git clone failed. Check that the repository is public or that GITHUB_TOKEN is set. "
            "If the repository requires authentication, set the GH_TOKEN environment variable and relaunch."
        ),
    },
    {
        "trigger": "no ethereum contract addresses found",
        "reply": (
            "No contract addresses could be scraped from the scope page. "
            "This happens when addresses are rendered by JavaScript after page load (the agent fetches raw HTML). "
            "Try pasting individual addresses directly into the Protocol name field, or use a GitHub repository URL."
        ),
    },
    {
        "trigger": "no repositories found",
        "reply": (
            "GitHub search returned no matching repositories. "
            "Try using the exact GitHub slug (owner/repo), a scope page URL, or a contract address directly."
        ),
    },
    {
        "trigger": "hypothesis",
        "reply": (
            "A hypothesis is produced when an expected protocol subsystem is absent from the reconstruction. "
            "This is not automatically a vulnerability — the subsystem may be imported from another repository. "
            "Check the 'Hypothesis Lab' tab to see the current stage for each hypothesis and whether a Foundry test was generated."
        ),
    },
    {
        "trigger": "foundry",
        "reply": (
            "Foundry tests require forge to be installed and HALYX_FORK_RPC_URL to be set. "
            "Use the 'Save env for selected run' form on the dashboard to set the fork RPC, then re-run the POC."
        ),
    },
    {
        "trigger": "fork",
        "reply": (
            "Fork execution requires HALYX_FORK_RPC_URL. Set it in the env form on the dashboard. "
            "A public endpoint such as https://rpc.mevblocker.io works for Ethereum mainnet without an API key."
        ),
    },
    {
        "trigger": "survives",
        "reply": (
            "A 'survives' consensus means that at least one Foundry case returned supported_by_execution under deterministic behavioral evidence checks. "
            "It does NOT mean the protocol is safe — it means the tested hypothesis survived the current behavioral test. "
            "Review the hypothesis trace for invariant/economic observations and missing requirements."
        ),
    },
    {
        "trigger": "unknown",
        "reply": (
            "Consensus 'unknown' means no behavioral execution evidence was produced. "
            "Reconstruction succeeded but no Foundry tests ran (missing forge or fork RPC). "
            "Set HALYX_FORK_RPC_URL and ensure forge is available to advance beyond 'unknown'."
        ),
    },
]


def _extract_protocol_query(message: str) -> str | None:
    trimmed = message.strip()

    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            payload = json.loads(trimmed)
            if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                detail = str(payload["detail"])
                match = re.search(r"unable to identify a strict protocol repository for '([^']+)'", detail, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                return _extract_protocol_query(detail)
        except json.JSONDecodeError:
            pass

    quoted_detail = re.search(r'"detail"\s*:\s*"([^"]+)"', message)
    if quoted_detail:
        detail = quoted_detail.group(1)
        match = re.search(r"unable to identify a strict protocol repository for '([^']+)'", detail, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    detail_match = re.search(r"unable to identify a strict protocol repository for '([^']+)'", message, re.IGNORECASE)
    if detail_match:
        return detail_match.group(1).strip()

    if re.search(r"unable to identify a strict protocol repository", message, re.IGNORECASE):
        return None

    address_match = re.search(r"0x[a-fA-F0-9]{40}", message)
    if address_match:
        return address_match.group(0)

    url_match = re.search(r"https?://[^\s]+", message)
    if url_match:
        url = url_match.group(0).strip().rstrip(".,)")
        if "immunefi.com/bug-bounty/" in url:
            match = re.search(r"immunefi\.com/bug-bounty/([^/]+)/?", url)
            if match:
                return match.group(1).replace("-", " ")
        parsed = urllib.parse.urlparse(url)
        path_segments = [segment for segment in parsed.path.split("/") if segment]
        if path_segments:
            tail = path_segments[-1]
            return tail.replace("-", " ")
        return parsed.netloc.replace("www.", "")

    lowered = message.lower()
    if any(token in lowered for token in ("protocol", "immunefi", "cantina", "sherlock", "code4rena", "bug bounty")):
        cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", message)
        tokens = [
            token
            for token in cleaned.split()
            if token.lower()
            not in {
                "protocol",
                "immunefi",
                "cantina",
                "sherlock",
                "code4rena",
                "bug",
                "bounty",
                "is",
                "on",
                "listed",
                "check",
                "detail",
                "unable",
                "identify",
                "strict",
                "repository",
                "search",
                "candidates",
                "top",
                "error",
            }
        ]
        if tokens:
            return " ".join(tokens[:4])

    return None


def _http_probe(url: str, *, timeout_seconds: float = 8.0) -> tuple[bool, int | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "Halyx-Assistant/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return True, int(getattr(response, "status", 200))
    except HTTPError as exc:
        return False, int(exc.code)
    except (URLError, OSError, TimeoutError):
        return False, None


def _check_program_listings(query: str) -> list[dict[str, object]]:
    compact = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    flat = re.sub(r"[^a-z0-9]+", "", query.lower())
    candidates = [candidate for candidate in [compact, flat] if candidate]
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        deduped.append(candidate)
        seen.add(candidate)

    results: list[dict[str, object]] = []
    for slug in deduped[:2]:
        immunefi_url = f"https://immunefi.com/bug-bounty/{slug}/information/"
        ok, code = _http_probe(immunefi_url)
        results.append(
            {
                "program": "immunefi",
                "slug": slug,
                "url": immunefi_url,
                "found": ok,
                "status_code": code,
            }
        )

    cantina_url = f"https://cantina.xyz/competitions?search={urllib.parse.quote(query)}"
    ok, code = _http_probe(cantina_url)
    results.append(
        {
            "program": "cantina",
            "slug": compact,
            "url": cantina_url,
            "found": ok,
            "status_code": code,
        }
    )

    sherlock_url = f"https://audits.sherlock.xyz/contests?search={urllib.parse.quote(query)}"
    ok, code = _http_probe(sherlock_url)
    results.append(
        {
            "program": "sherlock",
            "slug": compact,
            "url": sherlock_url,
            "found": ok,
            "status_code": code,
        }
    )
    return results


def _proactive_protocol_lookup(message: str) -> dict[str, object] | None:
    message = message.strip()
    url_match = re.search(r"https?://[^\s]+", message)
    extracted_url = url_match.group(0).strip().rstrip(".,)") if url_match else None

    if extracted_url and is_scope_url(extracted_url):
        query = _extract_protocol_query(message) or extracted_url
        listing_results = _check_program_listings(query)
        return {
            "query": query,
            "input_kind": "scope_url",
            "input_value": extracted_url,
            "github_candidates": [],
            "program_listings": listing_results,
            "suggested_target": extracted_url,
            "github_error": None,
        }

    address_match = re.search(r"0x[a-fA-F0-9]{40}", message)
    if address_match:
        address = address_match.group(0)
        return {
            "query": address,
            "input_kind": "contract_address",
            "input_value": address,
            "github_candidates": [],
            "program_listings": [],
            "suggested_target": address,
            "github_error": None,
        }

    query = _extract_protocol_query(message)
    if not query or query.lower().strip() in {"detail unable to identify", "unable to identify"}:
        return None

    agent = SourceAcquisitionAgent()
    github_candidates: list[dict[str, object]] = []
    github_error: str | None = None
    try:
        github_candidates = agent.search_github_repositories(query, per_page=20)
    except Exception as exc:
        github_error = str(exc)

    ranked_candidates: list[dict[str, object]] = []
    if github_candidates:
        enriched: list[dict[str, object]] = []
        for candidate in github_candidates:
            full_name = str(candidate.get("full_name") or "").strip()
            if not full_name:
                continue
            structure_score = agent._repository_structure_score(full_name)  # noqa: SLF001
            base_score = agent._score_repository_candidate(candidate, query)  # noqa: SLF001
            total_score = base_score + structure_score
            scored = dict(candidate)
            scored["_score"] = total_score
            scored["_base_score"] = base_score
            scored["_structure_score"] = structure_score
            enriched.append(scored)

        strict = [
            item
            for item in enriched
            if agent._passes_strict_candidate_gate(item, protocol_name=query, structure_score=float(item.get("_structure_score") or 0.0))  # noqa: SLF001
        ]
        source_list = strict if strict else enriched
        ranked_candidates = sorted(source_list, key=lambda item: float(item.get("_score") or 0.0), reverse=True)

    listing_results = _check_program_listings(query)

    normalized_candidates: list[dict[str, object]] = []
    for item in ranked_candidates[:3]:
        normalized_candidates.append(
            {
                "full_name": str(item.get("full_name") or ""),
                "html_url": str(item.get("html_url") or ""),
                "stars": int(item.get("stargazers_count") or 0),
                "description": str(item.get("description") or "").strip(),
                "score": float(item.get("_score") or 0.0),
            }
        )

    suggested_target = normalized_candidates[0]["full_name"] if normalized_candidates else query
    return {
        "query": query,
        "github_candidates": normalized_candidates,
        "program_listings": listing_results,
        "suggested_target": suggested_target,
        "github_error": github_error,
    }


def _extract_suggested_target_from_context(context: str | None) -> str | None:
    if not context:
        return None
    target_match = re.search(r"AGREE:\s*proceed using target\s+'([^']+)'", context, re.IGNORECASE)
    if target_match:
        return target_match.group(1).strip()
    json_target_match = re.search(r'"suggested_target"\s*:\s*"([^"]+)"', context)
    if json_target_match:
        return json_target_match.group(1).strip()
    return None


def _extract_authoritative_target(message: str, context: str | None) -> tuple[str, str] | None:
    trimmed = message.strip()
    lowered = trimmed.lower()

    if lowered == "agree":
        target = _extract_suggested_target_from_context(context)
        if target:
            return target, "agreed_target"
        return None
    if lowered.startswith("disagree"):
        return None

    url_match = re.search(r"https?://[^\s]+", trimmed)
    if url_match:
        target_url = url_match.group(0).strip().rstrip(".,)")
        if is_scope_url(target_url):
            return target_url, "scope_url"
        if is_git_reference(target_url):
            return target_url, "repository_url"

    if is_contract_address(trimmed):
        return trimmed, "contract_address"
    if is_github_reference(trimmed) or is_git_reference(trimmed):
        return trimmed, "repository_reference"
    if is_solidity_source_blob(trimmed):
        return trimmed, "manual_source"

    return None


def _load_acquisition_metadata(repository_path: str) -> dict[str, object]:
    metadata_path = Path(repository_path).expanduser() / ".halyx-acquisition.json"
    if not metadata_path.exists() or not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_operator_status_report(*, target: str, launch_payload: dict[str, object]) -> str:
    dashboard = launch_payload.get("dashboard")
    dash = dashboard if isinstance(dashboard, dict) else {}
    repo_path = str(launch_payload.get("repository_path") or "")
    acquisition_meta = _load_acquisition_metadata(repo_path) if repo_path else {}
    acquisition_report = acquisition_meta.get("acquisition_report") if isinstance(acquisition_meta.get("acquisition_report"), dict) else {}

    methodology = dash.get("methodology") if isinstance(dash.get("methodology"), dict) else {}
    phases = methodology.get("phases") if isinstance(methodology.get("phases"), list) else []
    hypotheses = dash.get("research_hypotheses") if isinstance(dash.get("research_hypotheses"), list) else []
    falsification = dash.get("falsification_execution") if isinstance(dash.get("falsification_execution"), dict) else {}
    cases = falsification.get("cases") if isinstance(falsification.get("cases"), list) else []
    consensus = dash.get("consensus") if isinstance(dash.get("consensus"), dict) else {}
    consensus_class = str(consensus.get("classification") or launch_payload.get("consensus") or "unknown")

    execution_reason = str(falsification.get("reason") or "").strip()
    executed = bool(falsification.get("executed"))
    execution_blocked = (not executed) and (
        "fork rpc" in execution_reason.lower()
        or "halyx_fork_rpc_url" in execution_reason.lower()
        or any(str(case.get("status") or "") == "execution_blocked_toolchain" for case in cases if isinstance(case, dict))
    )

    acquisition_mode = str(acquisition_report.get("mode") or acquisition_meta.get("input_kind") or "unknown")
    source_status = "SUCCESS" if repo_path else "UNKNOWN"
    scope_completeness = "UNKNOWN"
    if acquisition_mode == "scope_url":
        addresses_found = acquisition_meta.get("addresses_found") if isinstance(acquisition_meta.get("addresses_found"), list) else []
        acquired = acquisition_meta.get("acquired") if isinstance(acquisition_meta.get("acquired"), list) else []
        if addresses_found:
            scope_completeness = "COMPLETE" if len(acquired) == len(addresses_found) else "PARTIAL"
            source_status = "SUCCESS" if acquired else "SOURCE_UNAVAILABLE"
    elif acquisition_mode in {"contract_address", "github", "git", "local", "manual_source", "zip", "protocol_name"}:
        contract_count = int((acquisition_report.get("artifacts") or {}).get("contract_count") or 0)
        source_status = "SUCCESS" if contract_count > 0 else "SOURCE_UNAVAILABLE"
        scope_completeness = "COMPLETE" if contract_count > 0 else "PARTIAL"

    lines = [
        "HALYX AUDIT STATUS",
        "",
        f"Target: {target}",
        f"Run ID: {launch_payload.get('run_id')}",
        f"Acquisition: {source_status}",
        f"Acquisition mode: {acquisition_mode}",
        f"Program scope: {scope_completeness}",
        f"Methodology phases: {len(phases)}",
        f"Hypotheses generated: {len(hypotheses)}",
        f"Executable sequences: {len(cases)}",
    ]

    if execution_blocked:
        lines.append("Foundry execution: BLOCKED")
        lines.append(f"Reason: {execution_reason or 'HALYX_FORK_RPC_URL not configured'}")
        lines.append("Behavioral confirmation: NOT AVAILABLE")
        lines.append("Current verdict: EXECUTION_BLOCKED")
    elif executed:
        lines.append("Foundry execution: ATTEMPTED")
        lines.append(f"Current verdict: {consensus_class}")
    else:
        lines.append("Foundry execution: NOT ATTEMPTED")
        if execution_reason:
            lines.append(f"Reason: {execution_reason}")
        lines.append(f"Current verdict: {consensus_class}")

    return "\n".join(lines)


def _assistant_reply(message: str, context: str | None, run_state: dict[str, object] | None) -> tuple[str, dict[str, object] | None]:
    lowered = (message + " " + (context or "")).lower()
    matched: list[str] = []
    for entry in _ASSISTANT_KNOWLEDGE:
        if entry["trigger"] in lowered:
            matched.append(entry["reply"])
    if matched:
        return "\n\n".join(matched), None

    proactive = _proactive_protocol_lookup(message)
    if proactive is not None:
        lines: list[str] = []
        lines.append(f"Protocol discovery query: '{proactive['query']}'")
        input_kind = str(proactive.get("input_kind") or "")
        if input_kind == "scope_url":
            lines.append("Detected input type: scope URL")
            lines.append("Plan: scrape scope page for on-page addresses, then fetch verified source via block explorer using your API key.")
        elif input_kind == "contract_address":
            lines.append("Detected input type: contract address")
            lines.append("Plan: fetch verified source from block explorer on the selected chain using your API key.")
        lines.append("Search results:")

        github_candidates = proactive.get("github_candidates", [])
        if isinstance(github_candidates, list) and github_candidates:
            for index, candidate in enumerate(github_candidates, start=1):
                if not isinstance(candidate, dict):
                    continue
                full_name = str(candidate.get("full_name") or "unknown")
                stars = int(candidate.get("stars") or 0)
                html_url = str(candidate.get("html_url") or "")
                description = str(candidate.get("description") or "")
                lines.append(f"• GitHub {index}: {full_name} (stars: {stars})")
                if html_url:
                    lines.append(f"  URL: {html_url}")
                if description:
                    lines.append(f"  Note: {description[:180]}")
        else:
            lines.append("• GitHub: no high-confidence repository candidate found yet.")
            github_error = str(proactive.get("github_error") or "").strip()
            if github_error:
                lines.append(f"  Error detail: {github_error[:220]}")

        listings = proactive.get("program_listings", [])
        if isinstance(listings, list):
            for item in listings:
                if not isinstance(item, dict):
                    continue
                program = str(item.get("program") or "program")
                url = str(item.get("url") or "")
                found = bool(item.get("found"))
                status = item.get("status_code")
                verdict = "reachable" if found else "not confirmed"
                lines.append(f"• {program.title()} listing check: {verdict} (status: {status})")
                if url:
                    lines.append(f"  URL: {url}")

        suggested_target = str(proactive.get("suggested_target") or proactive.get("query") or "")
        explicit_authority = bool(proactive.get("input_value"))
        if explicit_authority and input_kind in {"scope_url", "contract_address"}:
            lines.append("")
            lines.append(f"Authoritative target provided: '{suggested_target}'.")
            lines.append("The assistant can execute acquisition and audit progression immediately.")
        else:
            lines.append("")
            lines.append("Reply with one of these options:")
            lines.append(f"• AGREE: proceed using target '{suggested_target}'")
            lines.append("• DISAGREE: provide a replacement target (repo slug, scope URL, or contract address)")
        return "\n".join(lines), proactive

    # Generic guidance when no knowledge entry matched.
    lines = [
        "I can run proactive protocol discovery and listing checks for you.",
        "• Paste a scope page URL (e.g. https://audits.sherlock.xyz/contests/...) to extract and fetch all listed contracts.",
        "• Paste a GitHub slug (owner/repo) or a 0x contract address to load source directly.",
        "• Ask: 'Check whether <protocol> is a real protocol and where it is listed' to get ranked results.",
        "• Set ETHERSCAN_API_KEY, HALYX_FORK_RPC_URL, and optionally GITHUB_TOKEN in the env form for full coverage.",
        "• Check the Terminal tab for the exact error from the last pipeline run.",
        "• If a hypothesis shows 'untested', the Foundry harness did not run — provide a fork RPC and relaunch.",
    ]
    if run_state:
        consensus = str((run_state.get("consensus") or {}).get("classification") or "")
        if consensus:
            lines.append(f"• Current run consensus: {consensus}.")
        ledger = run_state.get("hypothesis_evidence_ledger") or []
        if isinstance(ledger, list):
            untested = sum(1 for h in ledger if isinstance(h, dict) and str(h.get("status") or "") == "untested")
            if untested:
                lines.append(f"• {untested} hypothesis/hypotheses are still untested — a fork RPC is needed to execute them.")
    return "\n".join(lines), None


@app.post("/api/assistant/message")
def assistant_message(request: AssistantMessageRequest) -> dict[str, object]:
    run_state: dict[str, object] | None = None
    if request.run_id:
        try:
            run_state = _load_run_dashboard_result(request.run_id)
        except Exception:
            pass
    if run_state is None:
        run_state = _load_latest_result()

    authoritative_target = _extract_authoritative_target(request.message, request.context)
    if request.auto_execute and authoritative_target is not None:
        target_value, target_kind = authoritative_target
        launch_scope = request.scope
        if launch_scope is None and target_kind == "scope_url":
            inferred_scope = _extract_protocol_query(target_value)
            launch_scope = inferred_scope or target_value

        launch_request = LaunchRequest(
            target=target_value,
            scope=launch_scope,
            chain=request.chain,
            output=request.output,
            etherscan_api_key=request.etherscan_api_key,
            etherscan_api_key_alt=request.etherscan_api_key_alt,
        )
        try:
            launch_payload = _execute_launch_request(request=launch_request)
        except HTTPException as exc:
            detail = str(exc.detail)
            blocker_lines = [
                "HALYX AUDIT STATUS",
                "",
                f"Target: {target_value}",
                "Acquisition: BLOCKED",
                f"Reason: {detail}",
                "Current verdict: EXECUTION_BLOCKED" if "fork" in detail.lower() else "Current verdict: ACQUISITION_BLOCKED",
            ]
            return {
                "reply": "\n".join(blocker_lines),
                "run_id": request.run_id,
                "proactive_search": {
                    "query": target_value,
                    "input_kind": target_kind,
                    "suggested_target": target_value,
                    "executed": False,
                    "error": detail,
                },
                "options": [],
            }
        status_report = _build_operator_status_report(target=target_value, launch_payload=launch_payload)
        return {
            "reply": status_report,
            "run_id": launch_payload.get("run_id"),
            "proactive_search": {
                "query": target_value,
                "input_kind": target_kind,
                "suggested_target": target_value,
                "executed": True,
            },
            "options": [],
            "launch": launch_payload,
        }

    reply, proactive = _assistant_reply(request.message, request.context, run_state)
    proactive_kind = str((proactive or {}).get("input_kind") or "") if isinstance(proactive, dict) else ""
    proactive_explicit = bool((proactive or {}).get("input_value")) if isinstance(proactive, dict) else False
    needs_confirmation = bool(proactive) and not (proactive_explicit and proactive_kind in {"scope_url", "contract_address"})
    options = [
        {"label": "AGREE", "description": "Proceed with suggested target"},
        {"label": "DISAGREE", "description": "Reject suggestion and provide an explicit target"},
    ] if needs_confirmation else []
    return {
        "reply": reply,
        "run_id": request.run_id,
        "proactive_search": proactive,
        "options": options,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract")
def extract_stage(path: str) -> ProtocolSpec:
    pipeline = ResearchPipeline(PipelineConfig(protocol_path=path))
    repository = pipeline.extractor.extract(load_repository(path))
    return repository


@app.post("/audit")
def audit_stage(path: str) -> dict[str, str]:
    pipeline = ResearchPipeline(PipelineConfig(protocol_path=path))
    summary = pipeline.run()
    return {"protocol": summary.protocol_name, "report": summary.report_path or ""}
