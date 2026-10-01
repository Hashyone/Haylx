from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PlannedAction:
    action: str
    rationale: str
    expected_information_gain: float
    uncertainty_reduction: float


@dataclass(slots=True)
class PlanningReport:
    next_action: PlannedAction
    candidate_actions: list[PlannedAction] = field(default_factory=list)
    uncertainty_score: float = 0.0
    should_invoke_tutor: bool = False
    should_continue_reconstruction: bool = True
    should_stop: bool = False


class PlanningEngine:
    """Choose the next best audit action from uncertainty and expected information gain."""

    def plan(
        self,
        *,
        pattern_label: str,
        expectation_match_ratio: float,
        missing_expected_subsystems: list[str],
        investigation_reports: list[dict[str, object]],
        tutor_notes: list[dict[str, object]] | None = None,
        historical_learning_signals: list[str] | None = None,
    ) -> PlanningReport:
        tutor_notes = tutor_notes or []
        historical_learning_signals = historical_learning_signals or []
        hypothesis_count = sum(len(report.get("adversarial_hypotheses", [])) for report in investigation_reports)
        research_gap_count = len(missing_expected_subsystems)
        tutor_gap_count = sum(1 for note in tutor_notes if note.get("verified") is False)
        gap_pressure = min(1.0, max(0.0, 1.0 - expectation_match_ratio))
        uncertainty_score = min(
            1.0,
            max(
                0.0,
                round(
                    0.45 * gap_pressure
                    + 0.25 * min(1.0, research_gap_count / 7.0)
                    + 0.20 * min(1.0, hypothesis_count / 8.0)
                    + 0.10 * min(1.0, max(0, tutor_gap_count) / 3.0),
                    3,
                ),
            ),
        )

        candidate_actions = [
            PlannedAction(
                action="invoke_tutor",
                rationale=(
                    f"Missing expected subsystems {missing_expected_subsystems[:3]} suggest an open knowledge gap."
                    if missing_expected_subsystems
                    else f"{pattern_label} would benefit from deeper concept research before broadening falsification."
                ),
                expected_information_gain=min(0.95, 0.45 + 0.35 * gap_pressure + 0.10 * research_gap_count),
                uncertainty_reduction=min(0.95, 0.5 + 0.25 * gap_pressure),
            ),
            PlannedAction(
                action="run_falsification",
                rationale=(
                    f"{hypothesis_count} adversarial hypotheses are already available for direct classical falsification."
                    if hypothesis_count
                    else "No adversarial hypotheses were generated yet, so falsification has limited immediate leverage."
                ),
                expected_information_gain=min(0.9, 0.30 + 0.30 * min(1.0, hypothesis_count / 6.0) + 0.15 * gap_pressure),
                uncertainty_reduction=min(0.9, 0.35 + 0.25 * min(1.0, hypothesis_count / 6.0)),
            ),
            PlannedAction(
                action="continue_reconstruction",
                rationale="Additional repository evidence can still improve subsystem traceability and coverage.",
                expected_information_gain=min(0.8, 0.25 + 0.25 * gap_pressure + 0.10 * len(historical_learning_signals)),
                uncertainty_reduction=min(0.8, 0.20 + 0.20 * gap_pressure),
            ),
            PlannedAction(
                action="compare_snapshots",
                rationale="Comparing against historical runs can reveal whether the gap is new or persistent.",
                expected_information_gain=min(0.7, 0.15 + 0.10 * len(historical_learning_signals)),
                uncertainty_reduction=min(0.7, 0.10 + 0.10 * len(historical_learning_signals)),
            ),
            PlannedAction(
                action="stop",
                rationale="Coverage is sufficient and no dominant uncertainty remains.",
                expected_information_gain=max(0.0, 1.0 - uncertainty_score),
                uncertainty_reduction=max(0.0, 1.0 - uncertainty_score),
            ),
        ]

        next_action = max(candidate_actions, key=lambda item: item.expected_information_gain)
        should_invoke_tutor = next_action.action == "invoke_tutor"
        should_stop = next_action.action == "stop" or uncertainty_score < 0.12
        should_continue_reconstruction = not should_stop and next_action.action != "run_falsification"

        return PlanningReport(
            next_action=next_action,
            candidate_actions=sorted(candidate_actions, key=lambda item: item.expected_information_gain, reverse=True),
            uncertainty_score=uncertainty_score,
            should_invoke_tutor=should_invoke_tutor,
            should_continue_reconstruction=should_continue_reconstruction,
            should_stop=should_stop,
        )