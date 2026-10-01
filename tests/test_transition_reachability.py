from quantum_economic_auditor.engine.reachability import ReachabilityEngine
from quantum_economic_auditor.models.transition import (
    ProtocolActionChoice,
    ProtocolState,
    ProtocolTransitionModel,
    TransitionStep,
)


def test_protocol_transition_model_produces_reachable_execution_history() -> None:
    initial_state = ProtocolState(
        backing=1000.0,
        supply=1000.0,
        treasury=500.0,
        premium=0.2,
        capacity=1000.0,
        collateral_ratio=1.0,
        debt=0.0,
        liquidity=200.0,
        utilization=0.0,
        reserve_balances={"reserve": 500.0},
        oracle_price=1.0,
    )
    transition_model = ProtocolTransitionModel(
        actions={
            "bond_purchase": ProtocolActionChoice(name="bond_purchase", amount=100.0),
            "redeem": ProtocolActionChoice(name="redeem", amount=50.0),
        }
    )

    history = transition_model.simulate_sequence(
        initial_state=initial_state,
        actions=["bond_purchase", "redeem"],
        decision_variables={"bond_purchase": 100.0, "redeem": 50.0},
    )

    assert len(history.steps) >= 2
    assert history.final_state.supply > initial_state.supply
    assert history.explanation


def test_reachability_engine_rejects_unreachable_candidate() -> None:
    initial_state = ProtocolState(
        backing=1000.0,
        supply=1000.0,
        treasury=10.0,
        premium=0.2,
        capacity=1000.0,
        collateral_ratio=1.0,
        debt=0.0,
        liquidity=200.0,
        utilization=0.0,
        reserve_balances={"reserve": 10.0},
        oracle_price=1.0,
    )
    transition_model = ProtocolTransitionModel(actions={"bond_purchase": ProtocolActionChoice(name="bond_purchase", amount=100.0)})
    engine = ReachabilityEngine(transition_model)

    result = engine.validate_sequence(
        initial_state=initial_state,
        actions=["bond_purchase"],
        decision_variables={"bond_purchase": 100.0},
    )

    assert result.reachable is False
    assert result.rejections
