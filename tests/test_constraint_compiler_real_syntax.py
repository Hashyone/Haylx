from quantum_economic_auditor.compiler.constraint_compiler import compile_protocol_constraints
from quantum_economic_auditor.models.constraint import Constraint


def test_constraint_compiler_accepts_solidity_style_guard_clauses() -> None:
    compiled = compile_protocol_constraints(
        [
            Constraint(name="sender_guard", expression="msg.sender != address(0)", kind="inequality"),
            Constraint(name="value_cap", expression="msg.value <= 1000", kind="inequality"),
        ]
    )

    assert len(compiled) == 2
    assert compiled[0].name == "sender_guard"
    assert compiled[1].name == "value_cap"


def test_constraint_compiler_accepts_dotted_property_access() -> None:
    compiled = compile_protocol_constraints(
        [
            Constraint(
                name="minimum_deposit_guard",
                expression="assetConfiguration.minimumDeposit >= 0",
                kind="inequality",
            )
        ]
    )

    assert len(compiled) == 1
    assert "minimumDeposit" in compiled[0].expression
