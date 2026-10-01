from __future__ import annotations

from quantum_economic_auditor.models.transition import ProtocolTransitionModel, ProtocolState, ReachabilityResult


class ReachabilityEngine:
    """Deterministic reachability engine for action-sequence planning."""

    def __init__(self, transition_model: ProtocolTransitionModel) -> None:
        self.transition_model = transition_model

    def validate_sequence(
        self,
        initial_state: ProtocolState,
        actions: list[str],
        decision_variables: dict[str, float],
    ) -> ReachabilityResult:
        history = self.transition_model.simulate_sequence(
            initial_state=initial_state,
            actions=actions,
            decision_variables=decision_variables,
        )
        rejections: list[str] = []
        for step in history.steps:
            rejections.extend(step.rejected_preconditions)
        return ReachabilityResult(
            reachable=history.constraint_status == "reachable",
            rejections=rejections,
            history=history,
        )
