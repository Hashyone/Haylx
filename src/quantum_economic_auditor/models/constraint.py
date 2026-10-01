from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConstraintType = Literal["equality", "inequality", "objective", "penalty"]


class Constraint(BaseModel):
    """A protocol rule represented as a typed, deterministic symbolic expression."""

    name: str
    expression: str
    kind: ConstraintType = Field(default="inequality")
    description: str | None = None
    weight: float = 1.0


class CompiledConstraint(BaseModel):
    """A compiled symbolic representation suitable for deterministic optimization."""

    name: str
    expression: str
    kind: ConstraintType = Field(default="inequality")
    symbol_map: dict[str, float] = Field(default_factory=dict)
