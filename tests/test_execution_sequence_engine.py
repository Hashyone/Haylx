from __future__ import annotations

from types import SimpleNamespace

from quantum_economic_auditor.models.eir import EconomicIntermediateRepresentation, EconomicInvariant
from quantum_economic_auditor.semantic.execution_sequence_engine import ExecutionSequenceReconstructionEngine


def _make_subsystem() -> SimpleNamespace:
    transitions = [
        SimpleNamespace(
            from_state="idle",
            to_state="deposited",
            triggering_function="deposit",
            required_permissions=[],
            modified_storage=["assets", "shares"],
            generated_events=["Deposit"],
            equations=["assets += amount", "shares += minted"],
            affected_invariants=["INV-SHARE-RATE"],
        ),
        SimpleNamespace(
            from_state="deposited",
            to_state="borrowed",
            triggering_function="borrowAgainstShares",
            required_permissions=[],
            modified_storage=["debt", "shares"],
            generated_events=["Borrow"],
            equations=["debt += borrowed"],
            affected_invariants=["INV-COLLATERAL"],
        ),
        SimpleNamespace(
            from_state="borrowed",
            to_state="redeemed",
            triggering_function="redeem",
            required_permissions=[],
            modified_storage=["assets", "shares", "debt"],
            generated_events=["Redeem"],
            equations=["shares -= burned"],
            affected_invariants=["INV-SHARE-RATE"],
        ),
    ]
    return SimpleNamespace(
        name="Vault Accounting",
        state_machine=SimpleNamespace(
            states=["idle", "deposited", "borrowed", "redeemed"],
            transitions=transitions,
            state_variables=["assets", "shares", "debt"],
        ),
        state_model=SimpleNamespace(
            state_variables=["assets", "shares", "debt"],
            balances=[],
            reserves=[],
            liabilities=["debt"],
            indexes=[],
            accumulated_values=[],
            cached_values=[],
            protocol_state_vars=[],
            execution_state_vars=[],
        ),
        permission_model=SimpleNamespace(roles=["user"], capabilities=[], permission_edges=[]),
        trust_model=SimpleNamespace(
            external_dependencies=["oracle"],
            oracle_assumptions=["price freshness"],
            governance_assumptions=[],
            timing_assumptions=["snapshot synchronization"],
        ),
        accounting_model=SimpleNamespace(
            update_equations=["assets += amount", "shares += minted", "debt += borrowed"],
            conservation_laws=["assets >= debt"],
            failure_conditions=[],
        ),
        contract_membership=SimpleNamespace(interfaces=["IVault"], supporting_libraries=[]),
        implementation_traces=[SimpleNamespace(functions=["deposit", "borrowAgainstShares", "redeem"], storage_variables=["assets", "shares", "debt"])],
        mathematical_specification=SimpleNamespace(economic_constraints=["assets_ge_debt"], safety_bounds=["share_rate_nonzero"]),
    )


def test_execution_sequence_engine_reconstructs_validated_sequence() -> None:
    engine = ExecutionSequenceReconstructionEngine(minimum_coverage_threshold=0.3)
    subsystem = _make_subsystem()
    report = SimpleNamespace(
        subsystem="Vault Accounting",
        adversarial_hypotheses=[
            SimpleNamespace(
                hypothesis_id="H-VAULT-001",
                attack_vector="stale share redemption",
                attack_description="Redeem against stale exchange rate",
                execution_steps=[
                    "User deposits assets into the vault",
                    "User borrows against inflated share value",
                    "Redemption occurs before synchronization",
                ],
                violated_invariant="INV-SHARE-RATE",
                economic_impact="Value leakage from stale share pricing",
                requires_privilege=False,
            )
        ],
    )
    eir = EconomicIntermediateRepresentation(
        protocol_name="VaultProto",
        invariants=[EconomicInvariant(name="assets_ge_debt", kind="debt_constraint", expression="assets >= debt")],
    )

    result = engine.reconstruct(
        protocol_name="VaultProto",
        eir=eir,
        subsystem_reconstructions=[subsystem],
        investigation_reports=[report],
    )

    assert not result.rejected_sequences
    assert len(result.validated_sequences) == 1
    sequence = result.validated_sequences[0]
    assert sequence.validation.is_valid is True
    assert sequence.validation.simulator_success is True
    assert [step.handler for step in sequence.ordered_steps] == ["deposit", "borrowAgainstShares", "redeem"]
    assert sequence.initial_state == "idle"
    assert sequence.resulting_protocol_state == "redeemed"
    assert sequence.execution_confidence > 0.5


def test_execution_sequence_engine_rejects_hypotheses_below_coverage_threshold() -> None:
    engine = ExecutionSequenceReconstructionEngine(minimum_coverage_threshold=0.8)
    subsystem = SimpleNamespace(
        name="Thin Subsystem",
        state_machine=SimpleNamespace(states=["idle"], transitions=[], state_variables=[]),
        state_model=SimpleNamespace(
            state_variables=[],
            balances=[],
            reserves=[],
            liabilities=[],
            indexes=[],
            accumulated_values=[],
            cached_values=[],
            protocol_state_vars=[],
            execution_state_vars=[],
        ),
        permission_model=SimpleNamespace(roles=[], capabilities=[], permission_edges=[]),
        trust_model=SimpleNamespace(external_dependencies=[], oracle_assumptions=[], governance_assumptions=[], timing_assumptions=[]),
        accounting_model=SimpleNamespace(update_equations=[], conservation_laws=[], failure_conditions=[]),
        contract_membership=SimpleNamespace(interfaces=[], supporting_libraries=[]),
        implementation_traces=[],
        mathematical_specification=SimpleNamespace(economic_constraints=[], safety_bounds=[]),
    )
    report = SimpleNamespace(
        subsystem="Thin Subsystem",
        adversarial_hypotheses=[
            SimpleNamespace(
                hypothesis_id="H-THIN-001",
                attack_vector="abstract manipulation",
                attack_description="No concrete transition path",
                execution_steps=["deposit, manipulate, redeem"],
                violated_invariant="INV-THIN",
                economic_impact="Unknown",
                requires_privilege=False,
            )
        ],
    )
    eir = EconomicIntermediateRepresentation(protocol_name="ThinProto")

    result = engine.reconstruct(
        protocol_name="ThinProto",
        eir=eir,
        subsystem_reconstructions=[subsystem],
        investigation_reports=[report],
    )

    assert not result.validated_sequences
    assert len(result.rejected_sequences) == 1
    assert "below threshold" in result.rejected_sequences[0].reasons[0].lower()