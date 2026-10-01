from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ClaimSource(str, Enum):
    CODE = "code"
    DOCUMENTATION = "documentation"
    PRIOR_AUDIT = "prior_audit"
    LLM_INFERENCE = "llm_inference"
    SIMULATION = "simulation"


class EvidencedClaim(BaseModel):
    id: str
    statement: str
    source: ClaimSource
    source_reference: str
    confidence: float = Field(ge=0.0, le=1.0)
    verification_method: str | None = None
    verified: bool = False


class AgentEvidence(BaseModel):
    agent_name: str
    subsystem_id: str | None = None
    claim: EvidencedClaim
    supporting_references: list[str] = Field(default_factory=list)
    confidence: Literal["direct AST match", "indirect reconstruction", "manual trace"] | str


class EvidenceConfidence(str, Enum):
    DIRECT_AST_MATCH = "direct AST match"
    INDIRECT_RECONSTRUCTION = "indirect reconstruction"
    MANUAL_TRACE = "manual trace"


# ── Multi-stage hypothesis evidence ──────────────────────────────────────────

class HypothesisStage(str, Enum):
    ARCHITECTURALLY_PLAUSIBLE = "architecturally_plausible"
    ECONOMICALLY_REACHABLE = "economically_reachable"
    BEHAVIORALLY_EXECUTABLE = "behaviorally_executable"
    INVARIANT_VIOLATED = "invariant_violated"
    FINDING_CONFIRMED = "finding_confirmed"
    REFUTED = "refuted"
    UNTESTED = "untested"


class StageAdvancement(BaseModel):
    stage: HypothesisStage
    advanced: bool
    reason: str
    confidence_delta: float = 0.0


class HypothesisEvidenceObject(BaseModel):
    """Structured evidence record produced for each hypothesis after behavioral testing."""
    hypothesis_id: str
    title: str
    subsystem: str
    current_stage: HypothesisStage = HypothesisStage.UNTESTED
    stage_history: list[StageAdvancement] = Field(default_factory=list)

    # Reconstruction layer
    reconstructed_protocol_state: dict[str, object] = Field(default_factory=dict)
    required_assumptions: list[str] = Field(default_factory=list)

    # Reachability layer
    required_actors: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    executable_sequence: list[dict[str, object]] = Field(default_factory=list)

    # Behavioral execution layer
    expected_invariant: str = ""
    observed_invariant_result: str = ""
    accounting_delta: str = ""
    state_transition: str = ""
    execution_logs: list[str] = Field(default_factory=list)
    foundry_test_reference: str | None = None
    environment: str = ""
    fork_block: int | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    # Economic evidence package
    predicted_values: dict[str, int] = Field(default_factory=dict)
    observed_values: dict[str, int] = Field(default_factory=dict)
    invariant_delta: dict[str, int] = Field(default_factory=dict)
    economic_delta: dict[str, int] = Field(default_factory=dict)
    economic_reconciliation: dict[str, object] = Field(default_factory=dict)
    evidence_strength: dict[str, str] = Field(default_factory=dict)
    missing_evidence: list[str] = Field(default_factory=list)

    # Final verdict
    verdict: str = "untested"
    verdict_basis: str = ""
    final_confidence: float = 0.0


class BehavioralVerdict(str, Enum):
    BEHAVIORALLY_CONFIRMED = "BEHAVIORALLY_CONFIRMED"
    FALSIFIED = "FALSIFIED"
    SYNTHETIC_EXECUTION = "SYNTHETIC_EXECUTION"
    REACHABILITY_BLOCKED = "REACHABILITY_BLOCKED"
    ASSUMPTION_GAP = "ASSUMPTION_GAP"
    INVARIANT_NOT_TESTABLE = "INVARIANT_NOT_TESTABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    TOOLCHAIN_BLOCKED = "TOOLCHAIN_BLOCKED"


class BehavioralEvidence(BaseModel):
    hypothesis_id: str
    execution_status: str
    actor_sequence: list[str] = Field(default_factory=list)
    pre_state: dict[str, object] = Field(default_factory=dict)
    post_state: dict[str, object] = Field(default_factory=dict)
    state_deltas: dict[str, object] = Field(default_factory=dict)
    invariant_checks: list[str] = Field(default_factory=list)
    invariant_violations: list[str] = Field(default_factory=list)
    economic_observations: dict[str, object] = Field(default_factory=dict)

    attacker_balance_before: int | None = None
    attacker_balance_after: int | None = None
    attacker_delta: int | None = None

    protocol_balance_before: int | None = None
    protocol_balance_after: int | None = None
    protocol_delta: int | None = None

    victim_balance_before: int | None = None
    victim_balance_after: int | None = None
    victim_delta: int | None = None

    required_capital_observed: int | None = None
    flashloan_principal_observed: int | None = None
    flashloan_fee_observed: int | None = None
    repayment_observed: int | None = None

    attack_path_completed: bool = False
    assertions_passed: int = 0
    assertions_failed: int = 0
    proof_criteria_satisfied: bool = False


class FlashloanRequirement(BaseModel):
    required: bool = False
    asset: str | None = None
    principal: int | None = None
    max_fee: int | None = None


class SequenceStep(BaseModel):
    index: int
    actor: str
    target: str
    function: str
    arguments: list[str] = Field(default_factory=list)
    expected_state_changes: list[str] = Field(default_factory=list)
    observed_state_changes: list[str] = Field(default_factory=list)
    expected_economic_effect: str | None = None
    observed_economic_effect: str | None = None


class BehavioralEvidenceContract(BaseModel):
    hypothesis_id: str
    target_contracts: list[str] = Field(default_factory=list)
    target_functions: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    sequence_steps: list[SequenceStep] = Field(default_factory=list)
    required_state_variables: list[str] = Field(default_factory=list)
    invariant_ids: list[str] = Field(default_factory=list)
    invariant_expression: str = ""
    expected_pre_state: dict[str, object] = Field(default_factory=dict)
    expected_transition: dict[str, object] = Field(default_factory=dict)
    expected_post_state: dict[str, object] = Field(default_factory=dict)
    required_economic_observations: list[str] = Field(default_factory=list)
    required_balance_observations: list[str] = Field(default_factory=list)
    required_capital_movements: list[str] = Field(default_factory=list)
    required_external_calls: list[str] = Field(default_factory=list)
    required_flashloan: FlashloanRequirement | None = None
    confirmation_requirements: list[str] = Field(default_factory=list)
