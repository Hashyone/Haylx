from __future__ import annotations

from dataclasses import dataclass, field
import re

from quantum_economic_auditor.models.truth_layer import MathematicalTruthLayer


@dataclass
class ReasoningOutput:
    score: float
    summary: str
    role: str = ""
    artifacts: list[str] = field(default_factory=list)
    verdicts: list[dict[str, object]] = field(default_factory=list)


class ClassicalReasoner:
    """Deterministic verifier that only scores what can be structurally proven."""

    def falsify_hypotheses(self, truth_layer: MathematicalTruthLayer) -> list[dict[str, object]]:
        equations_text = " ".join(
            _flatten_text_chunks(
                [
                    *truth_layer.economic_equations,
                    *truth_layer.expected_canonical_equations,
                    [dossier.get("observed_mathematics", []) for dossier in truth_layer.semantic_dossiers],
                    [dossier.get("canonical_mathematics", []) for dossier in truth_layer.semantic_dossiers],
                ]
            )
        )
        flattened_equations_text = " ".join(_flatten_text_chunks(equations_text)).lower()
        known_issue_text = " ".join(truth_layer.known_issues).lower()
        missing_expected = {item.lower() for item in truth_layer.missing_expected_subsystems}

        verdicts: list[dict[str, object]] = []
        for report in truth_layer.investigation_reports:
            subsystem = str(report.get("subsystem") or "unknown")
            for hypothesis in report.get("adversarial_hypotheses", []):
                attack_vector = str(hypothesis.get("attack_vector") or "unknown")
                violated_invariant = str(hypothesis.get("violated_invariant") or "")
                execution_steps = [str(step) for step in hypothesis.get("execution_steps", [])]

                support_evidence: list[str] = []
                contradiction_evidence: list[str] = []

                invariant_tokens = _tokenize_for_match(violated_invariant)
                attack_tokens = _tokenize_for_match(attack_vector)
                overlap = [token for token in invariant_tokens if token in flattened_equations_text]
                if overlap:
                    support_evidence.append(f"violated invariant terms present in reconstructed equations: {', '.join(overlap[:4])}")

                if any(token in known_issue_text for token in attack_tokens):
                    support_evidence.append("attack family is echoed in known issue context")

                subsystem_lower = subsystem.lower()
                if "oracle" in attack_vector.lower() and "oracle dependencies" in missing_expected:
                    support_evidence.append("oracle subsystem is missing from observed reconstruction")
                if "reentrancy" in attack_vector.lower() and "liquidity" in subsystem_lower:
                    support_evidence.append("liquidity subsystem exposes multi-step mutable flows relevant to reentrancy")
                if "flash loan" in attack_vector.lower() and truth_layer.protocol_pattern_label == "AMM":
                    support_evidence.append("AMM pattern plus swap mathematics makes flash-loan path economically plausible")
                if "role escalation" in attack_vector.lower() and "authority" in subsystem_lower:
                    support_evidence.append("authority subsystem directly governs privileged role transitions")

                if not overlap and not support_evidence:
                    contradiction_evidence.append("current deterministic model does not contain direct invariant or issue evidence for this path")
                if hypothesis.get("requires_privilege") and "authority" not in subsystem_lower and "permission" not in subsystem_lower:
                    contradiction_evidence.append("privileged-path hypothesis does not align with the current subsystem role")

                if support_evidence and not contradiction_evidence:
                    status = "supported_candidate"
                    confidence = 0.8
                elif support_evidence and contradiction_evidence:
                    status = "contested_candidate"
                    confidence = 0.55
                else:
                    status = "disproved_by_current_model"
                    confidence = 0.3

                verdicts.append(
                    {
                        "subsystem": subsystem,
                        "hypothesis_id": hypothesis.get("hypothesis_id"),
                        "attack_vector": attack_vector,
                        "status": status,
                        "confidence": confidence,
                        "support_evidence": support_evidence,
                        "contradiction_evidence": contradiction_evidence,
                        "classical_reason": (
                            "Classical verification found deterministic support for this candidate."
                            if status == "supported_candidate"
                            else "Classical verification found mixed signals for this candidate."
                            if status == "contested_candidate"
                            else "Classical verification could not support this candidate from the current deterministic model."
                        ),
                        "execution_steps": execution_steps,
                    }
                )
        return verdicts

    def reason(self, truth_layer: MathematicalTruthLayer) -> ReasoningOutput:
        equations = truth_layer.economic_equations
        combined = " ".join(equations).lower()
        constraint_markers = [op for op in (">=", "<=", "==", "!=") if op in combined]
        has_formal_constraint_language = any(
            token in truth_layer.optimization_formulation.lower()
            for token in ("constraint", "enforce", "enforcing", "solvency", "safety", "limit", "guard")
        )
        context_text = " ".join(
            [truth_layer.scope_context or "", truth_layer.evidence_summary or "", *(truth_layer.known_issues or [])]
        ).lower()
        issue_keywords = [keyword for keyword in ("oracle", "staleness", "frontrun", "pause", "upgrade", "relayer", "risk", "exploit") if keyword in context_text]
        provable_facts: list[str] = []
        if truth_layer.transition_matrix_ref:
            provable_facts.append("transition matrix present")
        if truth_layer.state_graph_ref:
            provable_facts.append("state graph present")
        if truth_layer.authority_graph_ref:
            provable_facts.append("authority graph present")
        if constraint_markers:
            provable_facts.append(f"{len(constraint_markers)} explicit constraint markers")

        score = 0.15
        score += 0.16 * min(3, len(equations))
        score += 0.12 if has_formal_constraint_language else 0.0
        score += 0.08 * min(4, len(provable_facts))
        score += 0.05 if truth_layer.immutable else 0.0
        if not equations:
            score -= 0.1
        score -= min(0.12, 0.03 * len(issue_keywords))
        score = max(0.05, min(0.95, round(score, 3)))

        issue_context = f" Contextual issues noted: {', '.join(issue_keywords)}." if issue_keywords else ""
        verdicts = self.falsify_hypotheses(truth_layer)
        supported_count = sum(1 for verdict in verdicts if verdict["status"] == "supported_candidate")
        disputed_count = sum(1 for verdict in verdicts if verdict["status"] == "contested_candidate")
        disproved_count = sum(1 for verdict in verdicts if verdict["status"] == "disproved_by_current_model")
        verdict_context = (
            f" Classical falsification reviewed {len(verdicts)} adversarial candidates: "
            f"{supported_count} supported, {disputed_count} contested, {disproved_count} disproved."
            if verdicts
            else ""
        )

        summary = (
            f"Classical proof pass over {truth_layer.subsystem_id}: verified {len(provable_facts)} deterministic signals, "
            f"{len(equations)} equations, and {len(constraint_markers)} explicit constraints. "
            f"This engine reports only provable structure, not hypotheses.{issue_context}{verdict_context}"
        )
        return ReasoningOutput(score=score, summary=summary, role="classical", artifacts=provable_facts, verdicts=verdicts)


class MLReasoner:
    """Pattern learner that produces probabilistic priors from historical-style similarity signals."""

    def reason(self, truth_layer: MathematicalTruthLayer) -> ReasoningOutput:
        pattern_label = truth_layer.protocol_pattern_label or "unknown"
        learned_signals = truth_layer.historical_learning_signals[:]
        if pattern_label != "unknown":
            learned_signals.append(f"protocol family resembles prior {pattern_label} audits")
        if truth_layer.expected_subsystems:
            learned_signals.append(f"{len(truth_layer.expected_subsystems)} expected subsystem priors available")
        if truth_layer.missing_expected_subsystems:
            learned_signals.append(
                f"historically risky gaps: {', '.join(truth_layer.missing_expected_subsystems[:3])}"
            )
        if truth_layer.known_issues:
            learned_signals.append(f"known issue context: {', '.join(truth_layer.known_issues[:2])}")

        score = 0.2
        score += 0.12 if pattern_label != "unknown" else 0.0
        score += 0.1 * min(3, len(truth_layer.expected_subsystems)) / 3.0
        score += 0.12 * truth_layer.expectation_match_ratio
        score += 0.05 * min(4, len(learned_signals))
        score -= min(0.18, 0.05 * len(truth_layer.missing_expected_subsystems))
        score = max(0.05, min(0.95, round(score, 3)))

        summary = (
            f"ML prior over {truth_layer.subsystem_id}: learned pattern context for {pattern_label}, "
            f"{len(learned_signals)} historical similarity signals, expectation match {truth_layer.expectation_match_ratio:.2f}. "
            f"This engine ranks plausibility and resemblance, not proof."
        )
        return ReasoningOutput(score=score, summary=summary, role="ml", artifacts=learned_signals)


class QuantumReasoner:
    """Exploratory engine that searches possibility space for novel hypotheses and sequences."""

    def reason(self, truth_layer: MathematicalTruthLayer) -> ReasoningOutput:
        exploration_paths: list[str] = []
        for report in truth_layer.investigation_reports[:3]:
            subsystem = str(report.get("subsystem") or "unknown")
            for attack in (report.get("adversarial_hypotheses") or [])[:2]:
                vector = str(attack.get("attack_vector") or "unknown-vector")
                exploration_paths.append(f"{subsystem}: explore {vector}")
        for hypothesis in truth_layer.research_hypotheses[:3]:
            title = str(hypothesis.get("title") or "missing hypothesis")
            exploration_paths.append(f"gap-driven hypothesis: {title}")
        for objective in truth_layer.exploration_objectives[:3]:
            exploration_paths.append(f"goal-directed search: {objective}")

        novelty_pressure = len(exploration_paths) + len(truth_layer.missing_expected_subsystems)
        graph_refs = sum(
            1
            for ref in (
                truth_layer.state_graph_ref,
                truth_layer.authority_graph_ref,
                truth_layer.evidence_graph_ref,
                truth_layer.constraint_graph_ref,
            )
            if ref
        )
        score = 0.18
        score += 0.08 * min(5, novelty_pressure)
        score += 0.05 * min(4, graph_refs)
        score += 0.04 * min(4, truth_layer.adversarial_hypothesis_count)
        score += 0.05 * min(3, len(truth_layer.semantic_dossiers))
        score = max(0.05, min(0.95, round(score, 3)))

        summary = (
            f"Quantum exploration over {truth_layer.subsystem_id}: generated {len(exploration_paths)} possibility-space paths from "
            f"graphs, dossiers, and hypotheses. This engine explores what could be true; Classical must later falsify or prove these candidates."
        )
        return ReasoningOutput(score=score, summary=summary, role="quantum", artifacts=exploration_paths)


def _flatten_text_chunks(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_flatten_text_chunks(item))
        return flattened
    return [str(value)]


def _tokenize_for_match(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9_]+", value.lower()) if len(token) >= 4]
