from __future__ import annotations

from pydantic import BaseModel, Field


class MathematicalTruthLayer(BaseModel):
    subsystem_id: str
    transition_matrix_ref: str
    state_graph_ref: str
    authority_graph_ref: str
    constraint_graph_ref: str
    evidence_graph_ref: str | None = None
    optimization_formulation: str
    economic_equations: list[str] = Field(default_factory=list)
    equation_provenance: list[dict[str, object]] = Field(default_factory=list)
    source_facts: list[str] = Field(default_factory=list)
    scope_context: str | None = None
    known_issues: list[str] = Field(default_factory=list)
    variable_names: list[str] = Field(default_factory=list)
    objective_expressions: list[str] = Field(default_factory=list)
    evidence_summary: str | None = None
    compiled_at: str | None = None
    immutable: bool = True
    expected_subsystems: list[str] = Field(default_factory=list)
    expected_canonical_equations: list[str] = Field(default_factory=list)
    expectation_match_ratio: float = 0.0
    missing_expected_subsystems: list[str] = Field(default_factory=list)
    investigation_risk_signals: list[str] = Field(default_factory=list)
    adversarial_hypothesis_count: int = 0
    protocol_pattern_label: str | None = None
    semantic_dossiers: list[dict[str, object]] = Field(default_factory=list)
    investigation_reports: list[dict[str, object]] = Field(default_factory=list)
    research_hypotheses: list[dict[str, object]] = Field(default_factory=list)
    historical_learning_signals: list[str] = Field(default_factory=list)
    exploration_objectives: list[str] = Field(default_factory=list)
    subsystem_reconstructions: list[dict[str, object]] = Field(default_factory=list)
    execution_sequences: list[dict[str, object]] = Field(default_factory=list)
    rejected_execution_sequences: list[dict[str, object]] = Field(default_factory=list)
    execution_sequence_coverage: list[dict[str, object]] = Field(default_factory=list)
    execution_sequence_threshold: float = 0.0
