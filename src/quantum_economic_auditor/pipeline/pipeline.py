from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from quantum_economic_auditor.agents.economic_extractor import StaticEconomicExtractor
from quantum_economic_auditor.compiler.binary_encoder import encode_variable
from quantum_economic_auditor.compiler.constraint_compiler import compile_eir_constraints
from quantum_economic_auditor.compiler.hamiltonian_builder import build_hamiltonian
from quantum_economic_auditor.comparison import ComparisonReport
from quantum_economic_auditor.engine.decision_generator import DecisionVariableGenerator
from quantum_economic_auditor.engine.reachability import ReachabilityEngine
from quantum_economic_auditor.graph.economic_dependency_graph import build_dependency_graph
from quantum_economic_auditor.models.eir import (
    EconomicAction,
    EconomicIntermediateRepresentation,
    EconomicInvariant,
    EconomicObjective,
    EconomicRelationship,
    EconomicVariable,
)
from quantum_economic_auditor.models.objective import ObjectiveSpec
from quantum_economic_auditor.models.protocol import ProtocolSpec
from quantum_economic_auditor.models.state import PipelineRunSummary
from quantum_economic_auditor.models.transition import ProtocolActionChoice, ProtocolState, ProtocolTransitionModel
from quantum_economic_auditor.optimizers.classical_optimizer import ClassicalOptimizer, ClassicalOptimizerConfig
from quantum_economic_auditor.optimizers.quantum_optimizer import QuantumOptimizer, QuantumOptimizerConfig
from quantum_economic_auditor.parser.repository_loader import load_repository
from quantum_economic_auditor.report.report_generator import ReportGenerator


@dataclass
class PipelineConfig:
    protocol_path: str
    objective_spec: ObjectiveSpec | None = None
    classical_iterations: int = 20
    quantum_qubits: int = 4
    quantum_depth: int = 2


class ResearchPipeline:
    """End-to-end deterministic pipeline for protocol-economic optimization research."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.extractor = StaticEconomicExtractor()

    def run(self) -> PipelineRunSummary:
        start = perf_counter()
        repository = load_repository(self.config.protocol_path)
        protocol_spec = self.extractor.extract(repository)
        eir = self._build_eir(protocol_spec)
        self._print_eir(eir)
        self._validate_eir(eir)
        graph = build_dependency_graph(eir)
        compiled_constraints = compile_eir_constraints(eir)
        objective_spec = self.config.objective_spec or ObjectiveSpec()

        action_sequence = self._default_action_sequence(protocol_spec, eir)
        decision_generator = DecisionVariableGenerator(action_names=action_sequence)
        decision_variables = decision_generator.generate_decision_variables()
        transition_model = self._build_transition_model(protocol_spec)
        initial_state = self._build_initial_state()
        reachability_engine = ReachabilityEngine(transition_model)

        encoded = [
            encode_variable(
                name=name,
                value=decision_variables.get(name, self._default_action_amount(name)),
                lower_bound=0.0,
                upper_bound=self._default_upper_bound(name),
                precision=self._default_precision(name),
            )
            for name in action_sequence[:4]
        ]

        definition = {item.name: item.raw_value for item in encoded}
        objective_fn = self._build_reachability_objective_fn(
            transition_model=transition_model,
            reachability_engine=reachability_engine,
            initial_state=initial_state,
            action_sequence=action_sequence,
        )
        classical_optimizer = ClassicalOptimizer(
            ClassicalOptimizerConfig(
                iterations=self.config.classical_iterations,
                optimizer_kind="simulated_annealing",
            )
        )
        quantum_optimizer = QuantumOptimizer(
            QuantumOptimizerConfig(qubits=self.config.quantum_qubits, depth=self.config.quantum_depth)
        )

        classical_result = classical_optimizer.optimize(objective_fn, definition)
        quantum_result = quantum_optimizer.optimize(objective_fn, definition)
        build_hamiltonian(
            objective_spec,
            profit_estimate=classical_result.profit_discovered,
            constraint_penalty=abs(classical_result.constraint_violations),
            gas_estimate=classical_result.execution_time_seconds,
            liquidity_penalty=classical_result.profit_discovered,
            capital_required=classical_result.profit_discovered,
        )

        comparison = ComparisonReport(results=[classical_result, quantum_result])
        report_generator = ReportGenerator(output_dir="reports")
        report_path = report_generator.emit_csv([classical_result, quantum_result])
        report_generator.emit_json([classical_result, quantum_result])
        report_generator.emit_markdown([classical_result, quantum_result])

        _ = compiled_constraints, graph, comparison

        return PipelineRunSummary(
            protocol_name=protocol_spec.protocol_name,
            execution_time_seconds=perf_counter() - start,
            results=[classical_result, quantum_result],
            report_path=str(report_path),
        )

    def _build_eir(self, protocol_spec: ProtocolSpec) -> EconomicIntermediateRepresentation:
        variable_names = [
            *[name for name in protocol_spec.state_variables if name],
            *[name for name in protocol_spec.economic_variables if name],
        ]
        variables = [
            EconomicVariable(name=name, category=self._infer_variable_category(name))
            for name in dict.fromkeys(variable_names)
            if self._is_economic_name(name)
        ]
        actions = [
            EconomicAction(name=name, kind=self._infer_action_kind(name))
            for name in dict.fromkeys(protocol_spec.actions)
            if self._is_economic_action(name)
        ]
        relationships = self._build_relationships(variables)
        invariants = [
            EconomicInvariant(
                name=f"invariant_{index}",
                kind=self._infer_invariant_kind(expression),
                expression=expression,
            )
            for index, expression in enumerate(protocol_spec.protocol_invariants[:4])
            if self._is_algebraizable(expression)
        ]
        objectives = [
            EconomicObjective(
                name="net_protocol_value",
                kind="profit",
                expression="backing + treasury + liquidity + premium + capacity - debt - supply",
                weight=1.0,
            )
        ]
        return EconomicIntermediateRepresentation(
            protocol_name=protocol_spec.protocol_name,
            variables=variables,
            actions=actions,
            relationships=relationships,
            invariants=invariants,
            objectives=objectives,
        )

    def _build_relationships(self, variables: list[EconomicVariable]) -> list[EconomicRelationship]:
        names = {variable.name.lower(): variable.name for variable in variables}
        edges: list[EconomicRelationship] = []

        if "backing" in names and "premium" in names:
            edges.append(EconomicRelationship(source=names["backing"], relation="prices", target=names["premium"]))
        if "premium" in names and "capacity" in names:
            edges.append(EconomicRelationship(source=names["premium"], relation="updates", target=names["capacity"]))
        if "capacity" in names and "bond" in names:
            edges.append(EconomicRelationship(source=names["capacity"], relation="depends_on", target=names["bond"]))
        if "bond" in names and "supply" in names:
            edges.append(EconomicRelationship(source=names["bond"], relation="updates", target=names["supply"]))
        if "supply" in names and "backing" in names:
            edges.append(EconomicRelationship(source=names["supply"], relation="consumes", target=names["backing"]))
        if "oracleprice" in names and "premium" in names:
            edges.append(EconomicRelationship(source=names["oracleprice"], relation="prices", target=names["premium"]))
        if "liquidity" in names and "supply" in names:
            edges.append(EconomicRelationship(source=names["liquidity"], relation="conserves", target=names["supply"]))
        if "treasury" in names and "bond" in names:
            edges.append(EconomicRelationship(source=names["treasury"], relation="depends_on", target=names["bond"]))
        return edges

    def _print_eir(self, eir: EconomicIntermediateRepresentation) -> None:
        print("Economic Variables:")
        for variable in eir.variables:
            print(f"  - {variable.name} [{variable.category}]")
        print("Economic Actions:")
        for action in eir.actions:
            print(f"  - {action.name} [{action.kind}]")
        print("Economic Relationships:")
        for relationship in eir.relationships:
            print(f"  - {relationship.source} {relationship.relation} {relationship.target}")
        print("Protocol Invariants:")
        for invariant in eir.invariants:
            print(f"  - {invariant.name}: {invariant.expression}")
        print("Optimization Objectives:")
        for objective in eir.objectives:
            print(f"  - {objective.name}: {objective.expression}")

    def _validate_eir(self, eir: EconomicIntermediateRepresentation) -> None:
        implementation_leaks = [
            name
            for name in [variable.name for variable in eir.variables] + [action.name for action in eir.actions]
            if any(token in name.lower() for token in self.extractor._implementation_tokens)
        ]
        if implementation_leaks:
            raise ValueError(
                "Economic extraction failure: implementation variables leaked into the EIR: "
                + ", ".join(sorted(set(implementation_leaks)))
            )

    def _build_reachability_objective_fn(
        self,
        transition_model: ProtocolTransitionModel,
        reachability_engine: ReachabilityEngine,
        initial_state: ProtocolState,
        action_sequence: list[str],
    ):
        def objective_fn(decision_state: dict[str, float]) -> float:
            reachability = reachability_engine.validate_sequence(
                initial_state=initial_state,
                actions=action_sequence,
                decision_variables=decision_state,
            )
            if not reachability.reachable or reachability.history is None:
                return -1_000_000.0

            history = reachability.history
            final_state = history.final_state
            profit = history.profit
            objective_value = profit + final_state.backing + final_state.treasury - final_state.debt
            if objective_value < 0:
                return -1_000_000.0
            return objective_value

        return objective_fn

    def _build_transition_model(self, protocol_spec: ProtocolSpec) -> ProtocolTransitionModel:
        action_entries = {}
        for action_name in protocol_spec.actions:
            if "bond" in action_name.lower():
                action_entries["bond_purchase"] = ProtocolActionChoice(
                    name="bond_purchase",
                    amount=self._default_action_amount("bond_purchase"),
                )
            elif "redeem" in action_name.lower():
                action_entries["redeem"] = ProtocolActionChoice(
                    name="redeem",
                    amount=self._default_action_amount("redeem"),
                )
            elif "mint" in action_name.lower():
                action_entries["mint"] = ProtocolActionChoice(
                    name="mint",
                    amount=self._default_action_amount("mint"),
                )
        if not action_entries:
            action_entries = {
                "bond_purchase": ProtocolActionChoice(name="bond_purchase", amount=100.0),
                "redeem": ProtocolActionChoice(name="redeem", amount=50.0),
            }
        return ProtocolTransitionModel(actions=action_entries)

    def _build_initial_state(self) -> ProtocolState:
        return ProtocolState(
            backing=1000.0,
            supply=1000.0,
            treasury=500.0,
            premium=0.2,
            capacity=1000.0,
            collateral_ratio=1.0,
            debt=0.0,
            liquidity=250.0,
            utilization=0.0,
            reserve_balances={"reserve": 500.0},
            oracle_price=1.0,
        )

    def _default_action_sequence(self, protocol_spec: ProtocolSpec, eir: EconomicIntermediateRepresentation) -> list[str]:
        decision_names = [action.name for action in eir.actions if getattr(action, "name", None)]
        if not decision_names:
            decision_names = list(protocol_spec.actions[:2])
        if any("bond" in name.lower() for name in decision_names):
            sequence = ["bond_purchase"]
        else:
            sequence = [decision_names[0]] if decision_names else ["bond_purchase"]
        if any("redeem" in name.lower() for name in decision_names):
            sequence.append("redeem")
        if len(sequence) == 1:
            sequence.append("redeem")
        return sequence

    def _default_action_amount(self, name: str) -> float:
        lower_name = name.lower()
        if "flashloan" in lower_name:
            return 250.0
        if "swap" in lower_name:
            return 100.0
        if "borrow" in lower_name:
            return 50.0
        if "redeem" in lower_name:
            return 50.0
        if "bond" in lower_name:
            return 100.0
        if "deposit" in lower_name:
            return 75.0
        if "withdraw" in lower_name:
            return 25.0
        if "liquidate" in lower_name:
            return 30.0
        return 10.0

    def _default_initial_value(self, name: str) -> float:
        lower_name = name.lower()
        if "premium" in lower_name or "oracle" in lower_name:
            return 200.0
        if "bond" in lower_name or "capacity" in lower_name or "backing" in lower_name:
            return 500.0
        if "supply" in lower_name or "treasury" in lower_name or "liquidity" in lower_name:
            return 1000.0
        return 100.0

    def _default_upper_bound(self, name: str) -> float:
        lower_name = name.lower()
        if "premium" in lower_name or "oracle" in lower_name:
            return 1000.0
        if "bond" in lower_name or "capacity" in lower_name or "backing" in lower_name:
            return 1000000.0
        if "supply" in lower_name or "treasury" in lower_name or "liquidity" in lower_name:
            return 1000000.0
        return 1000.0

    def _default_precision(self, name: str) -> float:
        lower_name = name.lower()
        if "premium" in lower_name or "oracle" in lower_name:
            return 5.0
        if "bond" in lower_name or "capacity" in lower_name or "backing" in lower_name:
            return 50.0
        if "supply" in lower_name or "treasury" in lower_name or "liquidity" in lower_name:
            return 50.0
        return 10.0

    def _infer_variable_category(self, name: str) -> str:
        lower_name = name.lower()
        if "backing" in lower_name:
            return "backing"
        if "premium" in lower_name:
            return "premium"
        if "capacity" in lower_name:
            return "capacity"
        if "debt" in lower_name:
            return "debt"
        if "supply" in lower_name:
            return "supply"
        if "liquidity" in lower_name:
            return "liquidity"
        if "treasury" in lower_name:
            return "reserve"
        if "bond" in lower_name:
            return "reserve"
        if "oracle" in lower_name or "price" in lower_name:
            return "oracle_price"
        return "reserve"

    def _infer_action_kind(self, name: str) -> str:
        lower_name = name.lower()
        if "mint" in lower_name:
            return "mint"
        if "burn" in lower_name:
            return "burn"
        if "redeem" in lower_name:
            return "redeem"
        if "bond" in lower_name:
            return "bond"
        if "swap" in lower_name:
            return "swap"
        if "borrow" in lower_name:
            return "borrow"
        if "repay" in lower_name:
            return "repay"
        if "deposit" in lower_name:
            return "deposit"
        if "withdraw" in lower_name:
            return "withdraw"
        if "liquidate" in lower_name:
            return "liquidate"
        if "flashloan" in lower_name:
            return "flashloan"
        return "swap"

    def _infer_invariant_kind(self, expression: str) -> str:
        lower_expression = expression.lower()
        if "backing" in lower_expression and "delta" in lower_expression:
            return "collateralization"
        if "const" in lower_expression or "product" in lower_expression:
            return "constant_product"
        if "supply" in lower_expression:
            return "supply_limit"
        if "oracle" in lower_expression:
            return "oracle_freshness"
        return "conservation"

    def _is_economic_name(self, name: str) -> bool:
        lower_name = name.lower()
        if not name:
            return False
        if any(token in lower_name for token in self.extractor._implementation_tokens):
            return False
        return any(token in lower_name for token in self.extractor._economic_tokens)

    def _is_economic_action(self, name: str) -> bool:
        lower_name = name.lower()
        if any(token in lower_name for token in self.extractor._implementation_tokens):
            return False
        return any(token in lower_name for token in ("mint", "burn", "borrow", "repay", "deposit", "withdraw", "swap", "redeem", "liquidate", "flashloan", "bond"))

    def _is_algebraizable(self, expression: str) -> bool:
        return any(op in expression for op in (">=", "<=", ">", "<", "==", "!="))
