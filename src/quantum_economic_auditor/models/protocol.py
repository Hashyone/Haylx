from __future__ import annotations

from pydantic import BaseModel, Field


class ProtocolSpec(BaseModel):
    """Structured economic protocol specification emitted by the extractor agent."""

    protocol_name: str
    state_variables: list[str] = Field(default_factory=list)
    economic_variables: list[str] = Field(default_factory=list)
    external_dependencies: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    state_transitions: list[str] = Field(default_factory=list)
    protocol_invariants: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_constraints: list[str] = Field(default_factory=list)
    reward_functions: list[str] = Field(default_factory=list)
    penalty_conditions: list[str] = Field(default_factory=list)
    oracle_dependencies: list[str] = Field(default_factory=list)
    liquidity_sources: list[str] = Field(default_factory=list)
    flashloan_sources: list[str] = Field(default_factory=list)
    governance_variables: list[str] = Field(default_factory=list)
    pricing_models: list[str] = Field(default_factory=list)
    debt_models: list[str] = Field(default_factory=list)
    share_models: list[str] = Field(default_factory=list)
    collateral_models: list[str] = Field(default_factory=list)
    risk_parameters: list[str] = Field(default_factory=list)
    required_assumptions: list[str] = Field(default_factory=list)
