from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class EncodedVariable(BaseModel):
    name: str
    raw_value: float
    encoded_bits: list[int] = Field(default_factory=list)
    gray_encoded_bits: list[int] = Field(default_factory=list)
    lower_bound: float = 0.0
    upper_bound: float = 1.0


class OptimizationResult(BaseModel):
    optimizer_name: str
    objective_score: float = 0.0
    profit_discovered: float = 0.0
    constraint_violations: int = 0
    energy: float = 0.0
    convergence: float = 0.0
    iterations: int = 0
    execution_time_seconds: float = 0.0
    memory_usage_mb: float = 0.0
    variables: dict[str, Any] = Field(default_factory=dict)


@dataclass
class PipelineRunSummary:
    protocol_name: str
    execution_time_seconds: float = 0.0
    results: list[OptimizationResult] = field(default_factory=list)
    report_path: str | None = None
