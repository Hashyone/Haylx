from __future__ import annotations

from pydantic import BaseModel, Field

from quantum_economic_auditor.models.transition import ProtocolExecutionHistory, ProtocolState


class FoundryPreparationSpec(BaseModel):
    initial_protocol_state: ProtocolState
    required_balances: dict[str, float] = Field(default_factory=dict)
    required_liquidity: dict[str, float] = Field(default_factory=dict)
    required_oracle_values: dict[str, float] = Field(default_factory=dict)
    required_block_timestamps: dict[str, int] = Field(default_factory=dict)
    required_approvals: dict[str, list[str]] = Field(default_factory=dict)
    required_actors: list[str] = Field(default_factory=list)
    ordered_transaction_sequence: list[str] = Field(default_factory=list)
    expected_intermediate_states: list[ProtocolState] = Field(default_factory=list)
    expected_final_state: ProtocolState
    expected_profit: float = 0.0


class FoundryPreparationEngine:
    """Generate a deterministic Foundry-ready action plan from an execution history."""

    def build_spec(self, history: ProtocolExecutionHistory) -> FoundryPreparationSpec:
        return FoundryPreparationSpec(
            initial_protocol_state=history.initial_state,
            required_balances={"reserve": history.initial_state.reserve_balances.get("reserve", 0.0)},
            required_liquidity={"liquidity": history.initial_state.liquidity},
            required_oracle_values={"oracle_price": history.initial_state.oracle_price},
            required_block_timestamps={"start": 1},
            required_approvals={"actors": ["attacker", "protocol"]},
            required_actors=["attacker", "protocol"],
            ordered_transaction_sequence=[step.action for step in history.steps],
            expected_intermediate_states=[step.state_after for step in history.steps],
            expected_final_state=history.final_state,
            expected_profit=history.profit,
        )
