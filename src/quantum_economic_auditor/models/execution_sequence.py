from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutionStep(BaseModel):
    index: int
    description: str
    handler: str
    caller: str
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    state_reads: list[str] = Field(default_factory=list)
    state_writes: list[str] = Field(default_factory=list)
    emitted_events: list[str] = Field(default_factory=list)
    trust_boundary: str | None = None
    permissions_required: list[str] = Field(default_factory=list)
    constraint_ids: list[str] = Field(default_factory=list)
    invariant_ids: list[str] = Field(default_factory=list)
    from_state: str | None = None
    to_state: str | None = None


class ExecutionCoverage(BaseModel):
    subsystem: str
    handlers_reconstructed: int = 0
    state_variables_modeled: int = 0
    permissions_modeled: int = 0
    trust_boundaries_modeled: int = 0
    external_integrations_modeled: int = 0
    accounting_paths_modeled: int = 0
    reachable_transitions: int = 0
    coverage_ratio: float = 0.0
    meets_threshold: bool = False


class SequenceValidation(BaseModel):
    is_valid: bool
    reasons: list[str] = Field(default_factory=list)
    simulator_success: bool = False
    completeness_ratio: float = 0.0
    transition_validity_ratio: float = 0.0


class ExecutionSequence(BaseModel):
    sequence_id: str
    hypothesis_id: str
    protocol: str
    subsystem: str
    ordered_steps: list[ExecutionStep] = Field(default_factory=list)
    initial_state: str | None = None
    resulting_protocol_state: str | None = None
    economic_consequence: str = ""
    violated_invariants: list[str] = Field(default_factory=list)
    violated_assumptions: list[str] = Field(default_factory=list)
    reasoning_trace: list[str] = Field(default_factory=list)
    coverage: ExecutionCoverage
    validation: SequenceValidation
    execution_confidence: float = 0.0


class RejectedExecutionSequence(BaseModel):
    sequence_id: str
    hypothesis_id: str
    subsystem: str
    reasons: list[str] = Field(default_factory=list)
    coverage: ExecutionCoverage


class ExecutionSequenceReport(BaseModel):
    validated_sequences: list[ExecutionSequence] = Field(default_factory=list)
    rejected_sequences: list[RejectedExecutionSequence] = Field(default_factory=list)
    coverage_by_subsystem: list[ExecutionCoverage] = Field(default_factory=list)
    minimum_coverage_threshold: float = 0.0
