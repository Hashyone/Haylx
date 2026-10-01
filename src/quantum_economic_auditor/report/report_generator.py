from __future__ import annotations

import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from quantum_economic_auditor.models.state import OptimizationResult


class ReportGenerator:
    """Generate deterministic research artifacts for comparison runs."""

    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def emit_csv(self, results: list[OptimizationResult]) -> Path:
        dataframe = pd.DataFrame([result.model_dump() for result in results])
        output_path = self.output_dir / "comparison.csv"
        dataframe.to_csv(output_path, index=False)
        return output_path

    def emit_json(self, results: list[OptimizationResult]) -> Path:
        output_path = self.output_dir / "comparison.json"
        payload = [result.model_dump() for result in results]
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    def emit_markdown(self, results: list[OptimizationResult]) -> Path:
        output_path = self.output_dir / "comparison.md"
        lines = ["# Optimization Comparison", "", "| Optimizer | Objective Score | Profit | Energy | Iterations |", "| --- | ---: | ---: | ---: | ---: |"]
        for result in results:
            lines.append(
                f"| {result.optimizer_name} | {result.objective_score:.4f} | {result.profit_discovered:.4f} | {result.energy:.4f} | {result.iterations} |"
            )
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output_path


# ── Audit report ──────────────────────────────────────────────────────────────

def _h(level: int, text: str) -> str:
    return f"{'#' * level} {text}"


def _bold(text: str) -> str:
    return f"**{text}**"


def _code(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    sep = " | ".join("---" for _ in headers)
    head = " | ".join(headers)
    body = "\n".join(" | ".join(str(c) for c in row) for row in rows)
    return f"| {head} |\n| {sep} |\n" + "\n".join(f"| {' | '.join(str(c) for c in row)} |" for row in rows)


def _stage_badge(stage: str) -> str:
    badges = {
        "architecturally_plausible": "🔵 Architecturally Plausible",
        "economically_reachable": "🟡 Economically Reachable",
        "behaviorally_executable": "🟠 Behaviorally Executable",
        "invariant_violated": "🔴 Invariant Violated",
        "finding_confirmed": "🚨 Finding Confirmed",
        "refuted": "✅ Refuted",
        "untested": "⚪ Untested",
    }
    return badges.get(stage, stage)


def _verdict_badge(verdict: str) -> str:
    badges = {
        "finding_confirmed": "🚨 FINDING CONFIRMED",
        "falsified": "✅ Refuted by Execution",
        "supported_by_execution": "🟠 Supported (no proof marker)",
        "inconclusive": "🟡 Inconclusive",
        "untested": "⚪ Untested — no behavioral execution",
        "HYPOTHESIS_CONFIRMED": "🚨 HYPOTHESIS CONFIRMED",
        "HYPOTHESIS_FALSIFIED": "✅ HYPOTHESIS FALSIFIED",
        "BEHAVIORAL_EXECUTION_SUCCESS": "🟠 BEHAVIORAL EXECUTION SUCCESS",
        "ECONOMIC_IMPACT_NOT_CONFIRMED": "🟡 ECONOMIC IMPACT NOT CONFIRMED",
        "REACHABILITY_FAILED": "🟡 REACHABILITY FAILED",
        "TEST_INFRASTRUCTURE_FAILURE": "⚫ TEST INFRASTRUCTURE FAILURE",
        "BEHAVIORAL_TEST_FAILED": "🟡 BEHAVIORAL TEST FAILED",
        "BEHAVIORAL_TEST_GENERATED": "🔵 BEHAVIORAL TEST GENERATED",
        "UNTESTED": "⚪ UNTESTED",
        "BEHAVIORALLY_CONFIRMED": "🚨 BEHAVIORALLY CONFIRMED",
        "SYNTHETIC_EXECUTION": "🟡 SYNTHETIC EXECUTION",
        "ASSUMPTION_GAP": "🟡 ASSUMPTION GAP",
        "REACHABILITY_BLOCKED": "🟡 REACHABILITY BLOCKED",
        "TOOLCHAIN_BLOCKED": "⚫ TOOLCHAIN BLOCKED",
        "INVARIANT_NOT_TESTABLE": "🟡 INVARIANT NOT TESTABLE",
        "FALSIFIED": "✅ FALSIFIED",
        "INCONCLUSIVE": "🟡 INCONCLUSIVE",
    }
    return badges.get(verdict, verdict)


def _indent(text: str, spaces: int = 4) -> str:
    return textwrap.indent(text, " " * spaces)


class AuditReportGenerator:
    """
    Produce a complete, evidence-linked audit report from a finished pipeline artifact.

    The report covers:
      - Protocol identity and reconstruction summary
      - State mechanics (subsystems, state machines, accounting)
      - Reachability analysis (coverage, execution sequences)
      - Hypothesis lifecycle (all stages, evidence chain)
      - Exploit path (ordered step-by-step proof)
      - Complete Foundry POC (no stubs — real addresses, selectors, invariant assertions)
      - Known issues and open questions
      - Verdict table
    """

    def generate(self, payload: dict[str, object], output_dir: Path | str | None = None) -> Path:
        out_dir = Path(output_dir) if output_dir else Path("reports")
        out_dir.mkdir(parents=True, exist_ok=True)

        protocol_name = self._protocol_name(payload)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"halyx-report-{_sanitize(protocol_name)}-{timestamp}.md"
        output_path = out_dir / filename

        sections: list[str] = [
            self._header(payload, protocol_name),
            self._protocol_identity(payload),
            self._known_issues(payload),
            self._state_mechanics(payload),
            self._reachability_analysis(payload),
            self._hypothesis_lifecycle(payload),
            self._exploit_paths(payload),
            self._foundry_poc(payload),
            self._verdict_table(payload),
            self._open_questions(payload),
            self._footer(payload),
        ]

        report = "\n\n---\n\n".join(s for s in sections if s.strip())
        output_path.write_text(report, encoding="utf-8")
        return output_path

    # ── Section builders ─────────────────────────────────────────────────────

    def _header(self, payload: dict, protocol_name: str) -> str:
        consensus = str((payload.get("consensus") or {}).get("classification") or "unknown")
        pattern = str((payload.get("protocol_pattern") or {}).get("label") or "unknown")
        confidence = float((payload.get("protocol_pattern") or {}).get("confidence") or 0)
        timestamp = datetime.now(UTC).isoformat()
        return "\n".join([
            _h(1, f"Halyx Audit Report — {protocol_name}"),
            "",
            f"**Generated:** {timestamp}  ",
            f"**Protocol pattern:** {pattern} (confidence {confidence:.0%})  ",
            f"**Pipeline consensus:** `{consensus}`  ",
            f"**Halyx version:** behavioral-proof pipeline v2  ",
        ])

    def _protocol_identity(self, payload: dict) -> str:
        ctx = payload.get("repository_context") or {}
        if not isinstance(ctx, dict):
            ctx = {}
        scope = str(ctx.get("scope_summary") or "Not captured.")
        repo = str(ctx.get("repository_path") or "unknown")
        reconstruction = payload.get("protocol_reconstruction") or {}
        if not isinstance(reconstruction, dict):
            reconstruction = {}
        lines = [
            _h(2, "Protocol Identity"),
            "",
            f"**Repository:** `{repo}`  ",
            f"**Scope summary:** {scope}  ",
            f"**Entities reconstructed:** {reconstruction.get('entity_count', 0)}  ",
            f"**Invariants reconstructed:** {reconstruction.get('invariant_count', 0)}  ",
        ]
        semantics = payload.get("protocol_semantics") or {}
        if isinstance(semantics, dict) and semantics:
            lines += [
                f"**State transitions modeled:** {semantics.get('state_transitions', 0)}  ",
                f"**Permissions modeled:** {semantics.get('permissions', 0)}  ",
                f"**Trust boundaries modeled:** {semantics.get('trust_boundaries', 0)}  ",
                f"**Economic variables:** {semantics.get('economic_variables', 0)}  ",
            ]
        return "\n".join(lines)

    def _known_issues(self, payload: dict) -> str:
        ctx = payload.get("repository_context") or {}
        if not isinstance(ctx, dict):
            return ""
        issues = ctx.get("known_issues") or []
        if not isinstance(issues, list) or not issues:
            return ""
        lines = [_h(2, "Known Issues (from documentation)"), ""]
        for issue in issues:
            lines.append(f"- {issue}")
        return "\n".join(lines)

    def _state_mechanics(self, payload: dict) -> str:
        subsystems = (payload.get("subsystem_plan") or {}).get("reconstructions") or []
        if not isinstance(subsystems, list) or not subsystems:
            return ""
        lines = [_h(2, "State Mechanics"), ""]
        for sub in subsystems:
            if not isinstance(sub, dict):
                continue
            name = str(sub.get("name") or "unknown")
            states = sub.get("state_machine_states") or []
            transitions = sub.get("state_machine_transitions") or []
            accounting = sub.get("accounting_model") or "none"
            invariant_count = len(sub.get("invariants") or [])
            confidence = float(sub.get("confidence") or 0)
            lines += [
                _h(3, name),
                f"- **Accounting model:** {accounting}",
                f"- **States:** {', '.join(str(s) for s in states) or 'none modeled'}",
                f"- **Transitions:** {len(transitions)}",
                f"- **Invariants:** {invariant_count}",
                f"- **Reconstruction confidence:** {confidence:.0%}",
            ]
            invariants = sub.get("invariants") or []
            if isinstance(invariants, list) and invariants:
                lines.append("- **Extracted invariants:**")
                for inv in invariants[:6]:
                    if isinstance(inv, dict):
                        lines.append(f"  - `{inv.get('formal_statement') or inv.get('unique_id') or ''}`")
            impl = sub.get("implementation_traces") or []
            if isinstance(impl, list) and impl:
                fns = []
                for trace in impl[:3]:
                    if isinstance(trace, dict):
                        fns.extend(trace.get("functions") or [])
                if fns:
                    lines.append(f"- **Key functions:** `{', '.join(fns[:8])}`")
        return "\n".join(lines)

    def _reachability_analysis(self, payload: dict) -> str:
        coverage = (payload.get("execution_sequence_coverage") or {}).get("subsystems") or []
        threshold = (payload.get("execution_sequence_coverage") or {}).get("minimum_threshold") or 0
        validated = payload.get("execution_sequences") or []
        rejected = payload.get("rejected_execution_sequences") or []

        lines = [
            _h(2, "Reachability Analysis"),
            "",
            f"**Coverage threshold:** {float(threshold):.0%}  ",
            f"**Validated sequences:** {len(validated)}  ",
            f"**Rejected sequences:** {len(rejected)}  ",
        ]

        if isinstance(coverage, list) and coverage:
            lines += ["", _h(3, "Coverage by Subsystem"), ""]
            rows = []
            for cov in coverage:
                if not isinstance(cov, dict):
                    continue
                meets = "✅" if cov.get("meets_threshold") else "❌"
                rows.append([
                    str(cov.get("subsystem") or ""),
                    f"{float(cov.get('coverage_ratio') or 0):.0%}",
                    str(cov.get("handlers_reconstructed") or 0),
                    str(cov.get("state_variables_modeled") or 0),
                    str(cov.get("reachable_transitions") or 0),
                    meets,
                ])
            if rows:
                lines.append(_table(
                    ["Subsystem", "Coverage", "Handlers", "State Vars", "Transitions", "Meets threshold"],
                    rows,
                ))

        if isinstance(rejected, list) and rejected:
            lines += ["", _h(3, "Rejected Sequences (why they were blocked)"), ""]
            for seq in rejected:
                if not isinstance(seq, dict):
                    continue
                lines.append(f"- **{seq.get('hypothesis_id')}** ({seq.get('subsystem')}): {'; '.join(seq.get('reasons') or [])}")

        if isinstance(validated, list) and validated:
            lines += ["", _h(3, "Validated Execution Sequences"), ""]
            for seq in validated:
                if not isinstance(seq, dict):
                    continue
                steps = seq.get("ordered_steps") or []
                validation = seq.get("validation") or {}
                lines += [
                    _h(4, f"{seq.get('sequence_id')} → {seq.get('subsystem')}"),
                    f"- Hypothesis: `{seq.get('hypothesis_id')}`",
                    f"- Valid: {validation.get('is_valid')} | Completeness: {float((validation or {}).get('completeness_ratio') or 0):.0%}",
                    f"- Economic consequence: {seq.get('economic_consequence') or 'not modeled'}",
                    f"- Violated invariants: {', '.join(seq.get('violated_invariants') or []) or 'none'}",
                ]
                if steps:
                    lines.append("- **Step sequence:**")
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        lines.append(
                            f"  {step.get('index')}. `{step.get('handler')}` "
                            f"({step.get('caller')}) — {step.get('from_state')} → {step.get('to_state')}"
                        )

        return "\n".join(lines)

    def _hypothesis_lifecycle(self, payload: dict) -> str:
        ledger = payload.get("hypothesis_evidence_ledger") or []
        objects = payload.get("hypothesis_evidence_objects") or []
        if not isinstance(ledger, list) or not ledger:
            return ""

        obj_by_id: dict[str, dict] = {
            str(o.get("hypothesis_id") or ""): o
            for o in objects
            if isinstance(o, dict)
        }

        lines = [_h(2, "Hypothesis Lifecycle"), ""]
        for entry in ledger:
            if not isinstance(entry, dict):
                continue
            hid = str(entry.get("hypothesis_id") or "")
            obj = obj_by_id.get(hid, {})
            stage = str(obj.get("current_stage") or "untested")
            verdict = str(obj.get("verdict") or "untested")
            confidence = float(entry.get("final_confidence") or 0)

            lines += [
                _h(3, f"{hid} — {entry.get('title') or hid}"),
                "",
                f"**Stage:** {_stage_badge(stage)}  ",
                f"**Verdict:** {_verdict_badge(verdict)}  ",
                f"**Final confidence:** {confidence:.0%}  ",
                f"**Subsystem:** {entry.get('subsystem') or '—'}  ",
            ]

            # Stage history chain
            history = obj.get("stage_history") or []
            if isinstance(history, list) and history:
                lines += ["", "**Stage advancement chain:**", ""]
                for sh in history:
                    if not isinstance(sh, dict):
                        continue
                    tick = "✅" if sh.get("advanced") else "❌"
                    delta = sh.get("confidence_delta") or 0
                    delta_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
                    lines.append(f"- {tick} `{sh.get('stage')}` ({delta_str}) — {sh.get('reason')}")

            # Proof attempts
            proof = entry.get("proof_attempts") or []
            if isinstance(proof, list) and proof:
                lines += ["", "**Proof attempts:**", ""]
                for attempt in proof:
                    if not isinstance(attempt, dict):
                        continue
                    verified = "✅ verified" if attempt.get("verified") else "⚠️ unverified"
                    lines.append(f"- `{attempt.get('attempt_id')}` ({verified}): {attempt.get('summary') or ''}")
                    targets = attempt.get("evidence_targets") or []
                    if targets:
                        lines.append(f"  - Evidence targets: `{', '.join(str(t) for t in targets[:5])}`")

            # Execution case
            case = entry.get("execution_case") or {}
            if isinstance(case, dict) and case:
                lines += ["", "**Foundry execution case:**", ""]
                lines += [
                    f"- Test: `{case.get('test_name') or 'none'}`",
                    f"- Status: `{case.get('status') or 'untested'}`",
                    f"- Rationale: {case.get('rationale') or '—'}",
                ]
                if case.get("proof_marker"):
                    lines.append(f"- **Diagnostic marker:** `{case['proof_marker']}`")
                if case.get("invariant_assertion"):
                    lines.append(f"- **Invariant assertion:** `{case['invariant_assertion']}`")
                if case.get("proof_summary"):
                    lines.append(f"- **Proof summary:** {case['proof_summary']}")
                assumptions = case.get("assumptions") or []
                if assumptions:
                    lines.append("- **Assumptions:**")
                    for assumption in assumptions[:8]:
                        lines.append(f"  - {assumption}")
                actors = case.get("actors") or []
                if actors:
                    lines.append(f"- **Actors:** `{', '.join(actors)}`")
                for field_name, label in [
                    ("required_capital", "Required capital"),
                    ("flashloan_principal", "Flashloan principal"),
                    ("flashloan_fee", "Flashloan fee"),
                    ("predicted_attacker_profit", "Predicted attacker profit"),
                    ("predicted_protocol_loss", "Predicted protocol loss"),
                    ("predicted_victim_loss", "Predicted victim loss"),
                ]:
                    value = case.get(field_name)
                    if value is not None:
                        lines.append(f"- **{label}:** `{value}`")
                targets = case.get("target_contracts") or []
                if targets:
                    lines.append(f"- **Target contracts:** `{', '.join(targets)}`")
                addrs = case.get("target_addresses") or []
                if addrs:
                    lines.append(f"- **Target addresses:** `{', '.join(addrs)}`")
                fns = case.get("target_functions") or []
                if fns:
                    lines.append(f"- **Target functions:** `{', '.join(fns[:6])}`")
            lines.append("")

        return "\n".join(lines)

    def _exploit_paths(self, payload: dict) -> str:
        objects = payload.get("hypothesis_evidence_objects") or []
        confirmed = [
            o for o in objects
            if isinstance(o, dict) and str(o.get("verdict") or "") in {"BEHAVIORALLY_CONFIRMED"}
        ]
        if not confirmed:
            lines = [
                _h(2, "Exploit Paths"),
                "",
                "> No hypothesis reached BEHAVIORALLY_CONFIRMED in this run.",
                "> Behavioral execution may have occurred, but required deterministic evidence (state transition, invariant violation, and economic reconciliation) was insufficient.",
            ]
            return "\n".join(lines)

        lines = [_h(2, "Exploit Paths"), ""]
        for obj in confirmed:
            hid = str(obj.get("hypothesis_id") or "")
            lines += [
                _h(3, f"Exploit: {hid}"),
                "",
                f"**Subsystem under attack:** {obj.get('subsystem') or '—'}  ",
                f"**Stage reached:** {_stage_badge(str(obj.get('current_stage') or ''))}  ",
                f"**State transition:** `{obj.get('state_transition') or '—'}`  ",
                f"**Economic consequence:** {obj.get('accounting_delta') or 'not captured'}  ",
                f"**Expected invariant:** `{obj.get('expected_invariant') or 'not modeled'}`  ",
                f"**Observed result:** `{obj.get('observed_invariant_result') or '—'}`  ",
            ]

            predicted = obj.get('predicted_values') or {}
            observed = obj.get('observed_values') or {}
            invariant_delta = obj.get('invariant_delta') or {}
            economic_delta = obj.get('economic_delta') or {}
            if any(isinstance(value, dict) and value for value in [predicted, observed, invariant_delta, economic_delta]):
                lines += ["", "**Economic evidence package:**", ""]
                if predicted:
                    lines.append("- **Predicted values:**")
                    for key, value in predicted.items():
                        lines.append(f"  - {self._humanize_key(str(key))}: `{value}`")
                if observed:
                    lines.append("- **Observed values:**")
                    for key, value in observed.items():
                        lines.append(f"  - {self._humanize_key(str(key))}: `{value}`")
                if invariant_delta:
                    lines.append("- **Invariant delta:**")
                    for key, value in invariant_delta.items():
                        lines.append(f"  - {self._humanize_key(str(key))}: `{value}`")
                if economic_delta:
                    lines.append("- **Economic delta:**")
                    for key, value in economic_delta.items():
                        lines.append(f"  - {self._humanize_key(str(key))}: `{value}`")

            limitations = obj.get('limitations') or []
            if limitations:
                lines += ["", "**Limitations:**"]
                for limitation in limitations:
                    lines.append(f"- {limitation}")

            actors = obj.get("required_actors") or []
            permissions = obj.get("required_permissions") or []
            assumptions = obj.get("required_assumptions") or []
            if actors:
                lines.append(f"**Required actors:** {', '.join(actors)}  ")
            if permissions:
                lines.append(f"**Required permissions:** `{', '.join(permissions)}`  ")
            if assumptions:
                lines += ["", "**Required assumptions:**"]
                for a in assumptions:
                    lines.append(f"- {a}")

            steps = obj.get("executable_sequence") or []
            if steps:
                lines += ["", "**Ordered exploit sequence:**", ""]
                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    lines.append(
                        f"{step.get('index', '?')}. **`{step.get('handler') or '?'}`** "
                        f"called by `{step.get('caller') or '?'}` "
                        f"— `{step.get('from_state') or '?'}` → `{step.get('to_state') or '?'}`"
                    )
                    pre = step.get("preconditions") or []
                    post = step.get("postconditions") or []
                    writes = step.get("state_writes") or []
                    if pre:
                        lines.append(f"   - Pre: {'; '.join(pre[:3])}")
                    if post:
                        lines.append(f"   - Post: {'; '.join(post[:3])}")
                    if writes:
                        lines.append(f"   - Writes: `{', '.join(writes)}`")
            lines.append("")

        return "\n".join(lines)

    def _foundry_poc(self, payload: dict) -> str:
        falsification = payload.get("falsification_execution") or {}
        if not isinstance(falsification, dict):
            return ""

        generated_test = str(falsification.get("generated_test_file") or "")
        harness_dir = str(falsification.get("harness_dir") or "")
        mode = str(falsification.get("mode") or "")
        fork_source = str(falsification.get("fork_rpc_source") or "not configured")
        return_code = falsification.get("return_code")
        passed = falsification.get("passed")
        stdout = str(falsification.get("stdout_tail") or "")
        stderr = str(falsification.get("stderr_tail") or "")
        cases = falsification.get("cases") or []

        lines = [_h(2, "Foundry POC"), ""]
        lines += [
            f"**Mode:** `{mode}`  ",
            f"**Fork RPC source:** `{fork_source}`  ",
            f"**Harness directory:** `{harness_dir or 'not generated'}`  ",
            f"**Generated test file:** `{generated_test or 'not generated'}`  ",
            f"**Return code:** `{return_code if return_code is not None else 'not executed'}`  ",
            f"**Passed:** `{passed if passed is not None else 'not executed'}`  ",
        ]

        if not generated_test:
            lines += [
                "",
                "> **The Foundry harness was not generated for this run.**",
                "> To generate a real POC:",
                "> 1. Set `HALYX_FORK_RPC_URL` in the dashboard env form.",
                "> 2. Ensure `forge` is installed (`curl -L https://foundry.paradigm.xyz | bash && foundryup`).",
                "> 3. Re-run the pipeline. The harness will be written to `.halyx/falsification_harness/` inside the repository.",
            ]
            return "\n".join(lines)

        # Embed the generated test source if it exists on disk
        test_source = ""
        if generated_test and Path(generated_test).exists():
            test_source = Path(generated_test).read_text(encoding="utf-8", errors="replace")

        # Per-case breakdown
        if isinstance(cases, list) and cases:
            lines += ["", _h(3, "Test Case Outcomes"), ""]
            for case in cases:
                if not isinstance(case, dict):
                    continue
                status = str(case.get("status") or "")
                hid = str(case.get("hypothesis_id") or "")
                test = str(case.get("test_name") or "")
                proof_marker = case.get("proof_marker") or ""
                invariant = case.get("invariant_assertion") or ""
                steps = case.get("execution_steps") or []

                lines += [
                    _h(4, f"`{test}`"),
                    f"- **Hypothesis:** `{hid}`",
                    f"- **Status:** `{status}`",
                    f"- **Rationale:** {case.get('rationale') or '—'}",
                ]
                if proof_marker:
                    lines.append(f"- **Proof marker:** `{proof_marker}`")
                if invariant:
                    lines.append(f"- **Invariant assertion:** `{invariant}`")
                contracts = case.get("target_contracts") or []
                addresses = case.get("target_addresses") or []
                functions = case.get("target_functions") or []
                violated = case.get("violated_invariants") or []
                if contracts:
                    lines.append(f"- **Target contracts:** `{', '.join(contracts)}`")
                if addresses:
                    lines.append(f"- **Target addresses:** `{', '.join(addresses)}`")
                if functions:
                    lines.append(f"- **Target functions:** `{', '.join(functions[:8])}`")
                if violated:
                    lines.append(f"- **Violated invariants:** `{', '.join(violated)}`")
                if isinstance(steps, list) and steps:
                    lines.append("- **Ordered behavioral steps:**")
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        lines.append(
                            f"  {step.get('index', '?')}. `{step.get('handler') or '?'}` "
                            f"({step.get('caller') or '?'}) "
                            f"`{step.get('from_state') or '?'}` → `{step.get('to_state') or '?'}`"
                        )
                lines.append("")

        # Full test source
        if test_source:
            lines += ["", _h(3, "Generated Foundry Test (verbatim from disk)"), ""]
            lines.append(_code(test_source, "solidity"))

        # Execution log tail
        if stdout.strip():
            lines += ["", _h(3, "Forge stdout (tail)"), ""]
            lines.append(_code(stdout[-3000:], ""))
        if stderr.strip():
            lines += ["", _h(3, "Forge stderr (tail)"), ""]
            lines.append(_code(stderr[-1500:], ""))

        return "\n".join(lines)

    def _verdict_table(self, payload: dict) -> str:
        ledger = payload.get("hypothesis_evidence_ledger") or []
        objects = payload.get("hypothesis_evidence_objects") or []
        if not isinstance(ledger, list) or not ledger:
            return ""

        obj_by_id: dict[str, dict] = {
            str(o.get("hypothesis_id") or ""): o
            for o in objects
            if isinstance(o, dict)
        }

        lines = [_h(2, "Verdict Table"), ""]
        rows = []
        for entry in ledger:
            if not isinstance(entry, dict):
                continue
            hid = str(entry.get("hypothesis_id") or "")
            obj = obj_by_id.get(hid, {})
            stage = str(obj.get("current_stage") or "untested")
            verdict = str(obj.get("verdict") or "untested")
            confidence = float(entry.get("final_confidence") or 0)
            proof = str(((entry.get("execution_case") or {}).get("proof_marker") or "—"))
            rows.append([
                f"`{hid}`",
                str(entry.get("subsystem") or "—"),
                _stage_badge(stage),
                _verdict_badge(verdict),
                f"{confidence:.0%}",
                f"`{proof}`",
            ])
        if rows:
            lines.append(_table(
                ["Hypothesis", "Subsystem", "Stage", "Verdict", "Confidence", "Proof marker"],
                rows,
            ))

        consensus = (payload.get("consensus") or {}).get("classification") or "unknown"
        lines += [
            "",
            f"**Overall pipeline consensus:** `{consensus}`",
            "",
            "> `unknown` — no behavioral execution was completed.",
            "> `inconclusive` — execution ran but produced no deterministic outcome.",
            "> `survives` — at least one hypothesis reached deterministic behavioral confirmation.",
            "> `falsified` — at least one behavioral test produced a falsification trigger.",
        ]
        return "\n".join(lines)

    def _open_questions(self, payload: dict) -> str:
        tutor = payload.get("tutor_research") or []
        if not isinstance(tutor, list) or not tutor:
            return ""
        questions: list[str] = []
        for note in tutor:
            if not isinstance(note, dict):
                continue
            for q in (note.get("open_questions") or []):
                questions.append(str(q))
        if not questions:
            return ""
        lines = [_h(2, "Open Questions"), ""]
        for q in questions[:20]:
            lines.append(f"- {q}")
        return "\n".join(lines)

    def _footer(self, payload: dict) -> str:
        reasoning = payload.get("reasoning") or {}
        if not isinstance(reasoning, dict):
            return ""
        return "\n".join([
            _h(2, "Reasoning Layer Summaries"),
            "",
            f"**Classical:** {reasoning.get('classical_summary') or '—'}  ",
            f"**ML:** {reasoning.get('ml_summary') or '—'}  ",
            f"**Quantum:** {reasoning.get('quantum_summary') or '—'}  ",
        ])

    @staticmethod
    def _humanize_key(key: str) -> str:
        return key.replace("_", " ").strip().capitalize()

    @staticmethod
    def _protocol_name(payload: dict) -> str:
        ctx = payload.get("repository_context") or {}
        if isinstance(ctx, dict):
            repo = str(ctx.get("repository_path") or "")
            if repo:
                return Path(repo).name
        return "protocol"


def _sanitize(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "report"
