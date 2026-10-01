from __future__ import annotations

from quantum_economic_auditor.models.evidence import BehavioralEvidenceContract, BehavioralVerdict
from quantum_economic_auditor.semantic.behavioral_evidence_gate import BehavioralEvidenceGate


def _contract(*, with_invariant: bool = True) -> BehavioralEvidenceContract:
    return BehavioralEvidenceContract(
        hypothesis_id="H-TEST-001",
        target_contracts=["Vault"],
        target_functions=["flashLoan(address,uint256)"],
        actors=["attacker", "protocol"],
        preconditions=["liquidity exists"],
        sequence_steps=[
            {
                "index": 1,
                "actor": "attacker",
                "target": "Vault",
                "function": "flashLoan",
            }
        ],
        invariant_expression=("reserve_after >= reserve_before" if with_invariant else ""),
        required_economic_observations=["attacker_profit"],
    )


def _evaluate(
    gate: BehavioralEvidenceGate,
    contract: BehavioralEvidenceContract,
    **overrides: bool | str,
) -> BehavioralVerdict:
    baseline = {
        "execution_status": "supported_by_execution",
        "validated_sequence_exists": True,
        "required_actors_exist": True,
        "preconditions_satisfied": True,
        "sequence_executed": True,
        "required_state_transition_occurred": True,
        "invariant_evaluated": True,
        "invariant_violated": True,
        "economic_effect_observed": True,
        "economic_reconciled": True,
        "attributable_to_hypothesis": True,
        "toolchain_blocked": False,
        "reachability_blocked": False,
        "assumption_gap": False,
        "contradiction_observed": False,
        "synthetic_execution": False,
        "proof_criteria_satisfied": True,
    }
    baseline.update(overrides)
    result = gate.evaluate(contract, **baseline)
    return result.verdict


def test_case_1_generic_success_is_not_confirmed() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(
        gate,
        _contract(),
        required_state_transition_occurred=False,
        invariant_violated=False,
        economic_effect_observed=False,
        economic_reconciled=False,
        proof_criteria_satisfied=False,
    )
    assert verdict == BehavioralVerdict.INCONCLUSIVE


def test_case_2_marker_only_is_not_confirmed() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(
        gate,
        _contract(),
        execution_status="supported_by_execution",
        required_state_transition_occurred=False,
        invariant_violated=False,
        economic_effect_observed=False,
        economic_reconciled=False,
        proof_criteria_satisfied=False,
    )
    assert verdict == BehavioralVerdict.INCONCLUSIVE


def test_case_3_predicted_profit_without_observed_profit_is_not_confirmed() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(
        gate,
        _contract(),
        economic_effect_observed=False,
        economic_reconciled=False,
        proof_criteria_satisfied=False,
    )
    assert verdict == BehavioralVerdict.INCONCLUSIVE


def test_case_4_state_change_without_invariant_violation_is_not_confirmed() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(gate, _contract(), invariant_violated=False, proof_criteria_satisfied=False)
    assert verdict == BehavioralVerdict.INCONCLUSIVE


def test_case_5_invariant_violated_but_repayment_fails_is_not_confirmed() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(
        gate,
        _contract(),
        invariant_violated=True,
        economic_effect_observed=True,
        economic_reconciled=False,
        proof_criteria_satisfied=False,
    )
    assert verdict == BehavioralVerdict.INCONCLUSIVE


def test_case_6_complete_deterministic_evidence_confirms_exploit() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(gate, _contract())
    assert verdict == BehavioralVerdict.BEHAVIORALLY_CONFIRMED


def test_case_7_missing_sequence_is_reachability_blocked() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(gate, _contract(), validated_sequence_exists=False)
    assert verdict == BehavioralVerdict.REACHABILITY_BLOCKED


def test_case_8_toolchain_failure_is_toolchain_blocked() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(gate, _contract(), toolchain_blocked=True)
    assert verdict == BehavioralVerdict.TOOLCHAIN_BLOCKED


def test_case_9_synthetic_execution_is_distinct_verdict() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(
        gate,
        _contract(),
        synthetic_execution=True,
        required_state_transition_occurred=False,
        invariant_violated=False,
        economic_effect_observed=False,
        economic_reconciled=False,
        proof_criteria_satisfied=False,
    )
    assert verdict == BehavioralVerdict.SYNTHETIC_EXECUTION


def test_case_10_deterministic_contradiction_is_falsified() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(gate, _contract(), contradiction_observed=True)
    assert verdict == BehavioralVerdict.FALSIFIED


def test_invariant_not_testable_verdict_when_missing_invariant_model() -> None:
    gate = BehavioralEvidenceGate()
    verdict = _evaluate(gate, _contract(with_invariant=False), invariant_evaluated=False, invariant_violated=False)
    assert verdict == BehavioralVerdict.INVARIANT_NOT_TESTABLE
