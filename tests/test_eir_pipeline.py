from quantum_economic_auditor.compiler.constraint_compiler import compile_eir_constraints
from quantum_economic_auditor.graph.economic_dependency_graph import build_dependency_graph
from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)


def test_eir_dependency_graph_is_constructed_for_olympus_economics() -> None:
    eir = EconomicIntermediateRepresentation(
        protocol_name="olympus-v3",
        variables=[
            EconomicVariable(name="Backing", category="reserve"),
            EconomicVariable(name="Premium", category="premium"),
            EconomicVariable(name="Capacity", category="capacity"),
            EconomicVariable(name="DeltaB", category="debt"),
            EconomicVariable(name="Supply", category="supply"),
        ],
        actions=[
            EconomicAction(name="Mint", kind="mint"),
            EconomicAction(name="Burn", kind="burn"),
            EconomicAction(name="Redeem", kind="redeem"),
            EconomicAction(name="Bond", kind="bond"),
        ],
        relationships=[
            EconomicRelationship(source="Backing", relation="prices", target="Premium"),
            EconomicRelationship(source="Premium", relation="updates", target="Capacity"),
            EconomicRelationship(source="Capacity", relation="consumes", target="Mint"),
            EconomicRelationship(source="Mint", relation="updates", target="Supply"),
            EconomicRelationship(source="Supply", relation="prices", target="DeltaB"),
        ],
        invariants=[
            EconomicInvariant(name="Collateralization", kind="collateralization", expression="Backing >= DeltaB"),
        ],
        objectives=[
            EconomicObjective(name="Profit", kind="profit", expression="Premium * Mint", weight=1.0),
        ],
    )

    graph = build_dependency_graph(eir)

    assert set(graph.nodes) >= {"Backing", "Premium", "Capacity", "DeltaB", "Supply", "Mint"}
    assert graph.has_edge("Backing", "Premium")
    assert graph.has_edge("Premium", "Capacity")


def test_eir_constraints_are_compiled_into_symbolic_forms() -> None:
    eir = EconomicIntermediateRepresentation(
        protocol_name="olympus-v3",
        variables=[
            EconomicVariable(name="Backing", category="reserve"),
            EconomicVariable(name="DeltaB", category="debt"),
        ],
        invariants=[
            EconomicInvariant(name="Collateralization", kind="collateralization", expression="Backing >= DeltaB"),
        ],
        objectives=[
            EconomicObjective(name="Profit", kind="profit", expression="Backing + DeltaB", weight=1.0),
        ],
    )

    compiled = compile_eir_constraints(eir)

    assert len(compiled) == 2
    assert any(constraint.name == "Collateralization" for constraint in compiled)
    assert any("Backing" in constraint.expression for constraint in compiled)
