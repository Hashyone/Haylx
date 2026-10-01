from __future__ import annotations

from dataclasses import dataclass, field

from quantum_economic_auditor.models.evidence import BehavioralEvidenceContract, BehavioralVerdict


@dataclass(slots=True)
class BehavioralEvidenceGateResult:
    verdict: BehavioralVerdict
    confirmed: bool
    failed_requirements: list[str] = field(default_factory=list)
    observed: dict[str, object] = field(default_factory=dict)
    rationale: str = ""


class BehavioralEvidenceGate:
    """Deterministic truth boundary for behavioral proof claims."""

    def evaluate(
        self,
        contract: BehavioralEvidenceContract,
        *,
        execution_status: str,
        validated_sequence_exists: bool,
        required_actors_exist: bool,
        preconditions_satisfied: bool,
        sequence_executed: bool,
        required_state_transition_occurred: bool,
        invariant_evaluated: bool,
        invariant_violated: bool,
        economic_effect_observed: bool,
        economic_reconciled: bool,
        attributable_to_hypothesis: bool,
        toolchain_blocked: bool,
        reachability_blocked: bool,
        assumption_gap: bool,
        contradiction_observed: bool,
        synthetic_execution: bool = False,
        proof_criteria_satisfied: bool = False,
    ) -> BehavioralEvidenceGateResult:
        failed: list[str] = []
        observed = {
            "execution_status": execution_status,
            "validated_sequence_exists": validated_sequence_exists,
            "required_actors_exist": required_actors_exist,
            "preconditions_satisfied": preconditions_satisfied,
            "sequence_executed": sequence_executed,
            "required_state_transition_occurred": required_state_transition_occurred,
            "invariant_evaluated": invariant_evaluated,
            "invariant_violated": invariant_violated,
            "economic_effect_observed": economic_effect_observed,
            "economic_reconciled": economic_reconciled,
            "attributable_to_hypothesis": attributable_to_hypothesis,
            "proof_criteria_satisfied": proof_criteria_satisfied,
        }

        if toolchain_blocked:
            return BehavioralEvidenceGateResult(
                verdict=BehavioralVerdict.TOOLCHAIN_BLOCKED,
                confirmed=False,
                failed_requirements=["toolchain_blocked"],
                observed=observed,
                rationale="Behavioral execution was blocked by toolchain/compiler constraints.",
            )

        if reachability_blocked or not validated_sequence_exists:
            return BehavioralEvidenceGateResult(
                verdict=BehavioralVerdict.REACHABILITY_BLOCKED,
                confirmed=False,
                failed_requirements=["validated_sequence_exists"],
                observed=observed,
                rationale="No validated attack sequence exists for this hypothesis.",
            )

        if assumption_gap:
            return BehavioralEvidenceGateResult(
                verdict=BehavioralVerdict.ASSUMPTION_GAP,
                confirmed=False,
                failed_requirements=["assumptions_satisfied"],
                observed=observed,
                rationale="Execution depends on unmet assumptions (for example flashloan modeling without reproduction).",
            )

        if synthetic_execution:
            return BehavioralEvidenceGateResult(
                verdict=BehavioralVerdict.SYNTHETIC_EXECUTION,
                confirmed=False,
                failed_requirements=["state_or_economic_observation"],
                observed=observed,
                rationale="Execution was synthetic and did not establish a hypothesis-specific protocol/economic consequence.",
            )

        if contradiction_observed:
            return BehavioralEvidenceGateResult(
                verdict=BehavioralVerdict.FALSIFIED,
                confirmed=False,
                failed_requirements=[],
                observed=observed,
                rationale="Observed execution contradicted the hypothesis requirements.",
            )

        if not contract.invariant_expression:
            return BehavioralEvidenceGateResult(
                verdict=BehavioralVerdict.INVARIANT_NOT_TESTABLE,
                confirmed=False,
                failed_requirements=["invariant_modeled"],
                observed=observed,
                rationale="No concrete executable invariant was modeled for this hypothesis.",
            )

        if not required_actors_exist:
            failed.append("required_actors_exist")
        if contract.preconditions and not preconditions_satisfied:
            failed.append("preconditions_satisfied")
        if not sequence_executed:
            failed.append("sequence_executed")
        if contract.sequence_steps and not required_state_transition_occurred:
            failed.append("required_state_transition_occurred")
        if not invariant_evaluated:
            failed.append("invariant_evaluated")
        if invariant_evaluated and not invariant_violated:
            failed.append("invariant_violated")
        if contract.required_economic_observations and not economic_effect_observed:
            failed.append("economic_effect_observed")
        if contract.required_economic_observations and not economic_reconciled:
            failed.append("economic_reconciled")
        if not proof_criteria_satisfied:
            failed.append("proof_criteria_satisfied")
        if not attributable_to_hypothesis:
            failed.append("attributable_to_hypothesis")

        if failed:
            return BehavioralEvidenceGateResult(
                verdict=BehavioralVerdict.INCONCLUSIVE,
                confirmed=False,
                failed_requirements=failed,
                observed=observed,
                rationale="Behavioral execution is insufficient for confirmation under deterministic evidence requirements.",
            )

        return BehavioralEvidenceGateResult(
            verdict=BehavioralVerdict.BEHAVIORALLY_CONFIRMED,
            confirmed=True,
            failed_requirements=[],
            observed=observed,
            rationale="All deterministic evidence gate requirements were satisfied.",
        )
