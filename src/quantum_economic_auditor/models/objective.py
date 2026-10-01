from __future__ import annotations

from pydantic import BaseModel, Field


class ObjectiveWeight(BaseModel):
    profit: float = 1.0
    gas: float = 0.1
    capital_required: float = 0.2
    flashloan_size: float = 0.2
    transaction_count: float = 0.05


class ObjectiveSpec(BaseModel):
    """Objective specification for the optimization engine."""

    primary_objective: str = "maximize_protocol_value_extraction"
    secondary_objectives: list[str] = Field(default_factory=list)
    weights: ObjectiveWeight = Field(default_factory=ObjectiveWeight)


class OptimizationCandidate(BaseModel):
    """One ranked candidate strategy produced by the optimizer."""

    transaction_sequence: list[str] = Field(default_factory=list)
    expected_profit: float = 0.0
    constraint_satisfaction: float = 0.0
    capital_required: float = 0.0
    estimated_gas: float = 0.0
    protocol_assumptions: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
