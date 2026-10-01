from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class ProtocolState(BaseModel):
    backing: float = 0.0
    supply: float = 0.0
    treasury: float = 0.0
    premium: float = 0.0
    capacity: float = 0.0
    collateral_ratio: float = 0.0
    debt: float = 0.0
    liquidity: float = 0.0
    utilization: float = 0.0
    reserve_balances: dict[str, float] = Field(default_factory=dict)
    oracle_price: float = 0.0


class ProtocolActionChoice(BaseModel):
    name: str
    amount: float = 0.0
    preconditions: list[str] = Field(default_factory=list)
    economic_effects: dict[str, Any] = Field(default_factory=dict)


class TransitionStep(BaseModel):
    action: str
    decision_variable: float = 0.0
    state_before: ProtocolState
    state_after: ProtocolState
    reachable: bool = True
    rejected_preconditions: list[str] = Field(default_factory=list)
    satisfied_preconditions: list[str] = Field(default_factory=list)
    invariant_checks: list[str] = Field(default_factory=list)


class ProtocolExecutionHistory(BaseModel):
    initial_state: ProtocolState
    steps: list[TransitionStep] = Field(default_factory=list)
    final_state: ProtocolState
    explanation: str = ""
    profit: float = 0.0
    constraint_status: str = "unknown"


class ProtocolTransitionModel(BaseModel):
    actions: dict[str, ProtocolActionChoice] = Field(default_factory=dict)

    def simulate_sequence(
        self,
        initial_state: ProtocolState,
        actions: list[str],
        decision_variables: dict[str, float],
    ) -> ProtocolExecutionHistory:
        current_state = initial_state.model_copy(deep=True)
        steps: list[TransitionStep] = []
        explanation_lines: list[str] = []
        profit = 0.0

        for action_name in actions:
            action = self.actions[action_name]
            amount = float(decision_variables.get(action_name, action.amount))
            before = current_state.model_copy(deep=True)
            rejected: list[str] = []
            satisfied: list[str] = []

            if amount < 0:
                rejected.append("amount must be non-negative")

            if action_name == "bond_purchase":
                if current_state.treasury < amount:
                    rejected.append("treasury must cover bond purchase amount")
                if current_state.capacity < amount:
                    rejected.append("capacity must cover bond purchase amount")
                if current_state.supply < 0:
                    rejected.append("supply must be non-negative")
                if not rejected:
                    satisfied.extend(["treasury check", "capacity check", "non-negative supply"])
                    current_state.supply += amount
                    current_state.treasury -= amount
                    current_state.backing += amount
                    current_state.capacity -= amount
                    profit += amount
                    explanation_lines.append(f"{action_name} increased supply and treasury-backed capacity")
            elif action_name == "redeem":
                if current_state.backing < amount:
                    rejected.append("backing must cover redeem amount")
                if current_state.supply < amount:
                    rejected.append("supply must cover redeem amount")
                if not rejected:
                    satisfied.extend(["backing check", "supply check"])
                    current_state.supply -= amount
                    current_state.backing -= amount
                    current_state.treasury += amount
                    profit -= amount
                    explanation_lines.append(f"{action_name} reduced supply and released treasury backing")
            else:
                rejected.append(f"unsupported action: {action_name}")

            after = current_state.model_copy(deep=True)
            steps.append(
                TransitionStep(
                    action=action_name,
                    decision_variable=amount,
                    state_before=before,
                    state_after=after,
                    reachable=not rejected,
                    rejected_preconditions=rejected,
                    satisfied_preconditions=satisfied,
                    invariant_checks=["backing >= 0", "supply >= 0"] if not rejected else ["invariant check rejected"],
                )
            )

        return ProtocolExecutionHistory(
            initial_state=initial_state,
            steps=steps,
            final_state=current_state,
            explanation="; ".join(explanation_lines) or "No economic transition explanation available.",
            profit=profit,
            constraint_status="reachable" if all(step.reachable for step in steps) else "rejected",
        )


@dataclass
class ReachabilityResult:
    reachable: bool
    rejections: list[str] = field(default_factory=list)
    history: ProtocolExecutionHistory | None = None


class ReachabilityEngine:
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
