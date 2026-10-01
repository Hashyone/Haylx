from __future__ import annotations

from quantum_economic_auditor.semantic.protocol_pattern_engine import ExpectationComparison, HypothesisGenerator


def test_hypothesis_generator_adds_numeric_economic_targets_for_amm() -> None:
    generator = HypothesisGenerator()
    comparison = ExpectationComparison(
        expected=["Swap Mathematics", "Fee Distribution"],
        observed=["Swap Mathematics"],
        missing_expected=["Fee Distribution"],
        unexpected_observed=[],
        match_ratio=0.5,
    )

    hypotheses = generator.generate(comparison=comparison, pattern_label="AMM", pattern_id="amm")

    assert len(hypotheses) == 1
    hypothesis = hypotheses[0]
    assert hypothesis.expected_guarantees == ["Protocol and LP fees are correctly apportioned and claimable without double-counting."]
    assert hypothesis.required_actors[:2] == ["attacker", "lp"]
    assert hypothesis.required_capital > 0
    assert hypothesis.flashloan_principal == 0
    assert hypothesis.flashloan_fee == 0
    assert hypothesis.predicted_attacker_profit > 0
    assert hypothesis.predicted_protocol_loss >= hypothesis.predicted_attacker_profit
    assert hypothesis.expected_attack_sequence[0] == "acquire capital"
    assert "post-state" in hypothesis.expected_state_transition
    assert "Pool reserve loss" in hypothesis.economic_consequence


def test_hypothesis_generator_uses_permission_actor_model_without_flashloan() -> None:
    generator = HypothesisGenerator()
    comparison = ExpectationComparison(
        expected=["Governance", "Permission System"],
        observed=[],
        missing_expected=["Authority Model"],
        unexpected_observed=[],
        match_ratio=0.0,
    )

    hypotheses = generator.generate(comparison=comparison, pattern_label="AMM", pattern_id="amm")

    hypothesis = hypotheses[0]
    assert "attacker" in hypothesis.required_actors
    assert "admin" in hypothesis.required_actors or "governance" in hypothesis.required_actors
    assert any("Caller permissions" in item for item in hypothesis.required_assumptions)
    assert hypothesis.required_capital == 0
    assert hypothesis.flashloan_principal == 0
    assert hypothesis.flashloan_fee == 0
    assert hypothesis.predicted_attacker_profit == 0
    assert hypothesis.predicted_protocol_loss == 0
    assert hypothesis.predicted_victim_loss == 0


def test_hypothesis_generator_infers_flashloan_targets_for_oracle_risk() -> None:
    generator = HypothesisGenerator()
    comparison = ExpectationComparison(
        expected=["Oracle Dependencies"],
        observed=[],
        missing_expected=["Oracle Dependencies"],
        unexpected_observed=[],
        match_ratio=0.0,
    )

    hypotheses = generator.generate(comparison=comparison, pattern_label="AMM", pattern_id="amm")

    hypothesis = hypotheses[0]
    assert "oracle" in hypothesis.required_actors
    assert any("Oracle price" in item for item in hypothesis.required_assumptions)
    assert any(step == "acquire capital" for step in hypothesis.expected_attack_sequence)
    assert hypothesis.required_capital > 0
    assert hypothesis.flashloan_principal > 0
    assert hypothesis.flashloan_fee > 0
    assert hypothesis.predicted_attacker_profit > 0