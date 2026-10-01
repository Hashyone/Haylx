from quantum_economic_auditor.models.protocol import ProtocolSpec
from quantum_economic_auditor.models.constraint import Constraint
from quantum_economic_auditor.compiler.constraint_compiler import compile_protocol_constraints


def test_protocol_spec_is_strongly_typed() -> None:
    spec = ProtocolSpec(
        protocol_name="amm",
        state_variables=[],
        economic_variables=[],
        actions=[],
        state_transitions=[],
        protocol_invariants=[],
        hard_constraints=[],
        soft_constraints=[],
        reward_functions=[],
        penalty_conditions=[],
        oracle_dependencies=[],
        liquidity_sources=[],
        flashloan_sources=[],
        governance_variables=[],
        pricing_models=[],
        debt_models=[],
        share_models=[],
        collateral_models=[],
        risk_parameters=[],
        required_assumptions=[],
    )

    assert spec.protocol_name == "amm"


def test_constraint_compiler_returns_symbolic_constraints() -> None:
    constraints = [
        Constraint(name="constant_product", expression="x * y = k", kind="equality"),
        Constraint(name="liquidity_constraint", expression="x + y >= 0", kind="inequality"),
    ]

    compiled = compile_protocol_constraints(constraints)

    assert len(compiled) == 2
    assert compiled[0].name == "constant_product"
    assert compiled[1].name == "liquidity_constraint"
