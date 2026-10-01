from __future__ import annotations

from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)
from quantum_economic_auditor.models.truth_layer import MathematicalTruthLayer
from quantum_economic_auditor.reasoning_engines.engines import ClassicalReasoner, MLReasoner, QuantumReasoner


def test_reasoning_engines_consume_truth_layer_and_emit_scores() -> None:
    truth_layer = MathematicalTruthLayer(
        subsystem_id="bridge",
        transition_matrix_ref="matrix:bridge",
        state_graph_ref="graph:bridge",
        authority_graph_ref="authority:bridge",
        constraint_graph_ref="constraints:bridge",
        optimization_formulation="maximize collateral",
        economic_equations=["debt' = debt + borrow - repay", "collateral' = collateral - borrow"],
        protocol_pattern_label="Bridge",
        expected_subsystems=["Lock / Burn Accounting", "Message Relay"],
        expectation_match_ratio=0.5,
        missing_expected_subsystems=["Replay Protection"],
        semantic_dossiers=[{"subsystem_identity": "Lock / Burn Accounting", "protocol_guarantee": "locked == minted"}],
        investigation_reports=[
            {
                "subsystem": "Lock / Burn Accounting",
                "adversarial_hypotheses": [
                    {"attack_vector": "replay attack"},
                    {"attack_vector": "invalid proof reuse"},
                ],
            }
        ],
        research_hypotheses=[{"title": "Missing Replay Protection", "missing_subsystem": "Replay Protection", "priority": "high"}],
        historical_learning_signals=["bridge exploit prior", "reviewer rejects unproven replay claims"],
        exploration_objectives=["Find a sequence that duplicates a bridge mint without a second lock"],
    )

    classical = ClassicalReasoner().reason(truth_layer)
    ml = MLReasoner().reason(truth_layer)
    quantum = QuantumReasoner().reason(truth_layer)

    assert 0.0 <= classical.score <= 1.0
    assert 0.0 <= ml.score <= 1.0
    assert 0.0 <= quantum.score <= 1.0
    assert classical.summary
    assert ml.summary
    assert quantum.summary
    assert classical.role == "classical"
    assert ml.role == "ml"
    assert quantum.role == "quantum"
    assert "provable structure" in classical.summary.lower()
    assert "historical" in ml.summary.lower() or "pattern" in ml.summary.lower()
    assert "possibility-space" in quantum.summary.lower() or "explores what could be true" in quantum.summary.lower()
    assert classical.artifacts != quantum.artifacts


def test_classical_reasoner_flattens_nested_semantic_dossier_equations() -> None:
    truth_layer = MathematicalTruthLayer(
        subsystem_id="amm",
        transition_matrix_ref="matrix:amm",
        state_graph_ref="graph:amm",
        authority_graph_ref="authority:amm",
        constraint_graph_ref="constraints:amm",
        optimization_formulation="enforce pool solvency",
        economic_equations=["x * y = k"],
        expected_canonical_equations=["reserve_out <= reserve_available"],
        semantic_dossiers=[
            {
                "observed_mathematics": ["fee_accrual(t+1) = fee_accrual(t) + trade_fees"],
                "canonical_mathematics": [["x * y = k"]],
            }
        ],
        investigation_reports=[
            {
                "subsystem": "Swap Mathematics",
                "adversarial_hypotheses": [
                    {
                        "hypothesis_id": "H-1",
                        "attack_vector": "flash loan sandwich",
                        "violated_invariant": "reserve_out <= reserve_available",
                    }
                ],
            }
        ],
    )

    classical = ClassicalReasoner().reason(truth_layer)

    assert classical.verdicts
    assert classical.summary
    assert classical.score > 0.0
