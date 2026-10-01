from __future__ import annotations

from collections.abc import Iterable


class DecisionVariableGenerator:
    """Generate attacker-choice decision variables from the protocol action vocabulary."""

    _sequence_priority = (
        "flashloan",
        "swap",
        "bond_purchase",
        "redeem",
        "repay_flashloan",
    )

    def __init__(self, action_names: Iterable[str] | None = None) -> None:
        self.action_names = list(action_names or [])

    def generate_action_sequence(self) -> list[str]:
        ordered: list[str] = []
        for keyword in self._sequence_priority:
            for action_name in self.action_names:
                if keyword in action_name.lower() and action_name not in ordered:
                    ordered.append(action_name)
        for action_name in self.action_names:
            if action_name not in ordered:
                ordered.append(action_name)
        return ordered

    def generate_decision_variables(self) -> dict[str, float]:
        defaults = {
            "flashloan": 250.0,
            "swap": 100.0,
            "borrow": 50.0,
            "redeem": 50.0,
            "bond_purchase": 100.0,
            "deposit": 75.0,
            "withdraw": 25.0,
            "liquidate": 30.0,
            "repay_flashloan": 250.0,
        }
        decision_variables: dict[str, float] = {}
        for action_name in self.action_names:
            lowered = action_name.lower()
            decision_variables[action_name] = defaults.get(lowered, 10.0)
        return decision_variables
