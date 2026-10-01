from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from quantum_economic_auditor.consensus.engine import ConsensusEngine, FinalClassification
from quantum_economic_auditor.methodology.pipeline import ProtocolMethodologyPipeline
from quantum_economic_auditor.models.eir import EconomicIntermediateRepresentation
from quantum_economic_auditor.models.evidence import (
    BehavioralEvidenceContract,
    BehavioralVerdict,
    FlashloanRequirement,
    HypothesisEvidenceObject,
    HypothesisStage,
    SequenceStep,
    StageAdvancement,
)
from quantum_economic_auditor.models.graph import EvidenceEdge, EvidenceEdgeKind, EvidenceGraph, EvidenceNode, EvidenceNodeKind
from quantum_economic_auditor.models.truth_layer import MathematicalTruthLayer
from quantum_economic_auditor.openclaw.agents.repository_context import RepositoryContextAgent
from quantum_economic_auditor.parser.repository_loader import RepositoryModel, load_repository
from quantum_economic_auditor.pipeline.persistence import IntentAwareValidationGate, PipelinePersistence, ValidationResult
from quantum_economic_auditor.reasoning_engines.engines import ClassicalReasoner, MLReasoner, QuantumReasoner
from quantum_economic_auditor.report.report_generator import AuditReportGenerator
from quantum_economic_auditor.semantic.protocol_pattern_engine import (
    ExpectationGraphEngine,
    ExpectedObservedComparator,
    ExpectedProtocolModelRegistry,
    HypothesisGenerator,
    ProtocolPatternRecognitionEngine,
)
from quantum_economic_auditor.semantic.falsification_engine import FalsificationExecutionEngine
from quantum_economic_auditor.semantic.execution_sequence_engine import ExecutionSequenceReconstructionEngine
from quantum_economic_auditor.semantic.reasoning_trainer import ReasoningTrainingEngine
from quantum_economic_auditor.semantic.investigator_engine import (
    InvestigatorEngine,
    serialize_investigation_reports,
)
from quantum_economic_auditor.semantic.quantum_hypothesis_engine import QuantumHypothesisEngine
from quantum_economic_auditor.semantic.behavioral_evidence_gate import BehavioralEvidenceGate
from quantum_economic_auditor.semantic.planning_engine import PlanningEngine, PlanningReport
from quantum_economic_auditor.semantic.protocol_reconstruction import ProtocolReconstructionEngine
from quantum_economic_auditor.semantic.semantics_engine import ProtocolSemanticsEngine
from quantum_economic_auditor.semantic.subsystem_engine import (
    EvidenceReference,
    SubsystemDiscoveryEngine,
    SubsystemReconstruction,
    SubsystemReconstructionEngine,
)
from quantum_economic_auditor.semantic.tutor_engine import TutorEngine, TutorResearchNote
from quantum_economic_auditor.semantic.verification_engine import DeterministicVerificationEngine, VerificationReport


class HalyxOrchestrator:
    """Coordinate repository context gathering, methodology phases, consensus generation, and persistence."""

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.repository_agent = RepositoryContextAgent()
        self.methodology_pipeline = ProtocolMethodologyPipeline()
        self.consensus_engine = ConsensusEngine()
        self.classical_reasoner = ClassicalReasoner()
        self.ml_reasoner = MLReasoner()
        self.quantum_reasoner = QuantumReasoner()
        self.protocol_reconstruction_engine = ProtocolReconstructionEngine()
        self.protocol_semantics_engine = ProtocolSemanticsEngine()
        self.protocol_pattern_engine = ProtocolPatternRecognitionEngine()
        self.expected_model_registry = ExpectedProtocolModelRegistry()
        self.expectation_graph_engine = ExpectationGraphEngine()
        self.expected_observed_comparator = ExpectedObservedComparator()
        self.hypothesis_generator = HypothesisGenerator()
        self.quantum_hypothesis_engine = QuantumHypothesisEngine()
        self.investigator_engine = InvestigatorEngine()
        self.planning_engine = PlanningEngine()
        self.tutor_engine = TutorEngine()
        self.subsystem_discovery_engine = SubsystemDiscoveryEngine()
        self.subsystem_reconstruction_engine = SubsystemReconstructionEngine()
        self.storage_dir = Path(storage_dir or ".")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.training_engine = ReasoningTrainingEngine(self.storage_dir / "halyx_reasoning_lessons.jsonl")
        self.verification_engine = DeterministicVerificationEngine()
        self.falsification_engine = FalsificationExecutionEngine()
        self.execution_sequence_engine = ExecutionSequenceReconstructionEngine()
        self.behavioral_evidence_gate = BehavioralEvidenceGate()

    def _serialize_evidence(self, evidence: list[EvidenceReference] | list[list[EvidenceReference]]) -> list[dict[str, object]]:
        flattened: list[EvidenceReference] = []
        for item in evidence:
            if isinstance(item, list):
                flattened.extend(item)
            else:
                flattened.append(item)
        return [
            {
                "source_type": item.source_type,
                "repository_file": item.repository_file,
                "contract": item.contract,
                "function": item.function,
                "state_variable": item.state_variable,
                "event": item.event,
                "modifier": item.modifier,
                "inheritance": item.inheritance,
                "documentation": item.documentation,
                "audit_reference": item.audit_reference,
                "code_span": item.code_span,
                "confidence": item.confidence,
                "reason": item.reason,
            }
            for item in flattened
        ]

    def _serialize_transition(self, transition: object) -> dict[str, object]:
        if hasattr(transition, "from_state") and hasattr(transition, "to_state"):
            return {
                "from": transition.from_state,
                "to": transition.to_state,
                "triggering_function": transition.triggering_function,
                "required_permissions": transition.required_permissions,
                "modified_storage": transition.modified_storage,
                "generated_events": transition.generated_events,
                "equations": transition.equations,
                "affected_invariants": transition.affected_invariants,
                "evidence": self._serialize_evidence(transition.evidence),
            }
        return {"from": transition.get("from"), "to": transition.get("to")}

    def _build_semantic_dossiers(
        self,
        *,
        subsystem_reconstructions: list[SubsystemReconstruction],
        expected_subsystems: list[str],
    ) -> list[dict[str, object]]:
        expected_labels = expected_subsystems[:]
        dossiers: list[dict[str, object]] = []
        for index, subsystem in enumerate(subsystem_reconstructions):
            guarantee = subsystem.guarantees[0] if subsystem.guarantees else None
            expected_label = expected_labels[index] if index < len(expected_labels) else subsystem.name
            dossier_id = f"dossier:{subsystem.id}:{index}"
            dossiers.append(
                {
                    "dossier_id": dossier_id,
                    "subsystem_identity": subsystem.name,
                    "protocol_guarantee": guarantee.statement if guarantee else f"{subsystem.name} guarantee",
                    "purpose": subsystem.identity.protocol_objective if subsystem.identity else subsystem.description,
                    "expected_implementation": expected_label,
                    "observed_implementation": subsystem.name,
                    "canonical_mathematics": subsystem.mathematical_model.conservation_equations if subsystem.mathematical_model else [],
                    "observed_mathematics": (
                        [*(subsystem.mathematical_model.state_equations if subsystem.mathematical_model else []), *(subsystem.mathematical_model.balance_equations if subsystem.mathematical_model else [])]
                    ),
                    "implementation_traces": [
                        {
                            "functions": trace.functions,
                            "storage_variables": trace.storage_variables,
                            "events": trace.events,
                            "modifiers": trace.modifiers,
                            "call_graph": trace.call_graph,
                        }
                        for trace in subsystem.implementation_traces
                    ],
                    "permission_edges": subsystem.permission_model.permission_edges if subsystem.permission_model else [],
                    "economic_variables": (
                        subsystem.economic_model.collateral + subsystem.economic_model.debt + subsystem.economic_model.liquidity
                        if subsystem.economic_model
                        else []
                    ),
                    "confidence": subsystem.confidence,
                    "completeness": subsystem.completeness_status,
                    "open_questions": subsystem.report.open_questions if subsystem.report else [],
                    "hypotheses": subsystem.report.open_questions if subsystem.report else [],
                    "discovered_invariant_gaps": subsystem.missing_components,
                    "cross_subsystem_dependencies": [
                        {
                            "source": edge.source,
                            "target": edge.target,
                            "relation": edge.relation,
                        }
                        for edge in subsystem.dependency_model.dependency_edges
                    ],
                }
            )
        return dossiers

    @staticmethod
    def _serialize_tutor_note(note: TutorResearchNote) -> dict[str, object]:
        return {
            "concept": note.concept,
            "subsystem": note.subsystem,
            "protocol_pattern": note.protocol_pattern,
            "summary": note.summary,
            "candidate_explanations": note.candidate_explanations,
            "evidence_targets": note.evidence_targets,
            "source_materials": note.source_materials,
            "assumptions": note.assumptions,
            "open_questions": note.open_questions,
            "confidence": note.confidence,
            "verified": note.verified,
            "provider": note.provider,
            "raw_research": note.raw_research,
        }

    @staticmethod
    def _serialize_planning_report(report: PlanningReport) -> dict[str, object]:
        return {
            "uncertainty_score": report.uncertainty_score,
            "should_invoke_tutor": report.should_invoke_tutor,
            "should_continue_reconstruction": report.should_continue_reconstruction,
            "should_stop": report.should_stop,
            "next_action": {
                "action": report.next_action.action,
                "rationale": report.next_action.rationale,
                "expected_information_gain": report.next_action.expected_information_gain,
                "uncertainty_reduction": report.next_action.uncertainty_reduction,
            },
            "candidate_actions": [
                {
                    "action": action.action,
                    "rationale": action.rationale,
                    "expected_information_gain": action.expected_information_gain,
                    "uncertainty_reduction": action.uncertainty_reduction,
                }
                for action in report.candidate_actions
            ],
        }

    @staticmethod
    def _serialize_verification_report(report: VerificationReport) -> dict[str, object]:
        return {
            "concept": report.concept,
            "subsystem": report.subsystem,
            "verified": report.verified,
            "verification_score": report.verification_score,
            "rationale": report.rationale,
            "matched_files": [
                {
                    "file": item.file,
                    "matched_terms": item.matched_terms,
                }
                for item in report.matched_files
            ],
            "missing_terms": report.missing_terms,
        }

    @staticmethod
    def _serialize_falsification_execution(report: object) -> dict[str, object]:
        return {
            "mode": report.mode,
            "generated_test_file": report.generated_test_file,
            "harness_dir": report.harness_dir,
            "command": report.command,
            "fork_rpc_source": getattr(report, "fork_rpc_source", None),
            "executed": report.executed,
            "return_code": report.return_code,
            "passed": report.passed,
            "stdout_tail": report.stdout_tail,
            "stderr_tail": report.stderr_tail,
            "reason": report.reason,
            "cases": [
                {
                    "hypothesis_id": case.hypothesis_id,
                    "test_name": case.test_name,
                    "status": case.status,
                    "rationale": case.rationale,
                    "should_fail": case.should_fail,
                    "execution_sequence_id": getattr(case, "execution_sequence_id", None),
                    "execution_steps": getattr(case, "execution_steps", []),
                    "economic_consequence": getattr(case, "economic_consequence", ""),
                    "violated_invariants": getattr(case, "violated_invariants", []),
                    "target_contracts": case.target_contracts,
                    "target_addresses": case.target_addresses,
                    "target_functions": case.target_functions,
                    "target_invariants": case.target_invariants,
                    "invariant_assertion": getattr(case, "invariant_assertion", None),
                    "proof_marker": getattr(case, "proof_marker", None),
                    "proof_summary": getattr(case, "proof_summary", None),
                    "required_capital": getattr(case, "required_capital", 0),
                    "flashloan_principal": getattr(case, "flashloan_principal", 0),
                    "flashloan_fee": getattr(case, "flashloan_fee", 0),
                    "predicted_attacker_profit": getattr(case, "predicted_attacker_profit", 0),
                    "predicted_protocol_loss": getattr(case, "predicted_protocol_loss", 0),
                    "predicted_victim_loss": getattr(case, "predicted_victim_loss", 0),
                    "assumptions": getattr(case, "assumptions", []),
                    "actors": getattr(case, "actors", []),
                    "sequence_source": getattr(case, "sequence_source", ""),
                    "evidence_contract": getattr(case, "evidence_contract", {}),
                    "observed_values": getattr(case, "observed_values", {}),
                    "evidence_provenance": getattr(case, "evidence_provenance", {}),
                }
                for case in report.cases
            ],
        }

    @staticmethod
    def _serialize_execution_coverage(coverage: object) -> dict[str, object]:
        return {
            "subsystem": coverage.subsystem,
            "handlers_reconstructed": coverage.handlers_reconstructed,
            "state_variables_modeled": coverage.state_variables_modeled,
            "permissions_modeled": coverage.permissions_modeled,
            "trust_boundaries_modeled": coverage.trust_boundaries_modeled,
            "external_integrations_modeled": coverage.external_integrations_modeled,
            "accounting_paths_modeled": coverage.accounting_paths_modeled,
            "reachable_transitions": coverage.reachable_transitions,
            "coverage_ratio": coverage.coverage_ratio,
            "meets_threshold": coverage.meets_threshold,
        }

    @staticmethod
    def _serialize_sequence_validation(validation: object) -> dict[str, object]:
        return {
            "is_valid": validation.is_valid,
            "reasons": validation.reasons,
            "simulator_success": validation.simulator_success,
            "completeness_ratio": validation.completeness_ratio,
            "transition_validity_ratio": validation.transition_validity_ratio,
        }

    def _serialize_execution_sequence(self, sequence: object) -> dict[str, object]:
        return {
            "sequence_id": sequence.sequence_id,
            "hypothesis_id": sequence.hypothesis_id,
            "protocol": sequence.protocol,
            "subsystem": sequence.subsystem,
            "ordered_steps": [
                {
                    "index": step.index,
                    "description": step.description,
                    "handler": step.handler,
                    "caller": step.caller,
                    "preconditions": step.preconditions,
                    "postconditions": step.postconditions,
                    "state_reads": step.state_reads,
                    "state_writes": step.state_writes,
                    "emitted_events": step.emitted_events,
                    "trust_boundary": step.trust_boundary,
                    "permissions_required": step.permissions_required,
                    "constraint_ids": step.constraint_ids,
                    "invariant_ids": step.invariant_ids,
                    "from_state": step.from_state,
                    "to_state": step.to_state,
                }
                for step in sequence.ordered_steps
            ],
            "initial_state": sequence.initial_state,
            "resulting_protocol_state": sequence.resulting_protocol_state,
            "economic_consequence": sequence.economic_consequence,
            "violated_invariants": sequence.violated_invariants,
            "violated_assumptions": sequence.violated_assumptions,
            "reasoning_trace": sequence.reasoning_trace,
            "coverage": self._serialize_execution_coverage(sequence.coverage),
            "validation": self._serialize_sequence_validation(sequence.validation),
            "execution_confidence": sequence.execution_confidence,
        }

    def _build_execution_sequence_ledger(
        self,
        *,
        validated_sequences: list[dict[str, object]],
        rejected_sequences: list[dict[str, object]],
        investigation_reports: list[dict[str, object]],
        tutor_notes: list[TutorResearchNote],
        planning_report: PlanningReport,
        classical_summary: str,
        ml_summary: str,
        quantum_summary: str,
    ) -> list[dict[str, object]]:
        now = datetime.now(UTC).isoformat()
        report_lookup = {
            str(report.get("subsystem") or "").lower(): report
            for report in investigation_reports
            if isinstance(report, dict)
        }
        tutor_lookup = {
            (note.subsystem or note.concept or "").lower(): note
            for note in tutor_notes
        }
        ledger: list[dict[str, object]] = []

        for sequence in validated_sequences:
            subsystem = str(sequence.get("subsystem") or "")
            subsystem_key = subsystem.lower()
            report = report_lookup.get(subsystem_key, {})
            tutor_note = tutor_lookup.get(subsystem_key)
            execution_confidence = float(sequence.get("execution_confidence", 0.0) or 0.0)
            status = "validated_sequence"
            if execution_confidence >= 0.7:
                status = "provisionally_supported"
            elif execution_confidence <= 0.25:
                status = "risk_flagged"

            ledger.append(
                {
                    "hypothesis_id": sequence.get("hypothesis_id"),
                    "title": f"Execution sequence: {subsystem}",
                    "subsystem": subsystem,
                    "status": status,
                    "proof_attempts": [
                        {
                            "attempt_id": f"proof:{sequence.get('hypothesis_id')}:sequence_validation",
                            "source": "execution_sequence_validation",
                            "summary": "Sequence passed handler, transition, and state-model validation.",
                            "verified": bool(((sequence.get("validation") or {}) if isinstance(sequence.get("validation"), dict) else {}).get("is_valid")),
                            "evidence_targets": [step.get("handler") for step in sequence.get("ordered_steps", []) if isinstance(step, dict) and step.get("handler")],
                        }
                    ],
                    "falsification_attempts": [
                        {
                            "attempt_id": f"falsify:{sequence.get('hypothesis_id')}:investigator",
                            "source": "investigator",
                            "risk_signal": report.get("overall_risk_signal") if isinstance(report, dict) else None,
                            "adversarial_hypotheses": report.get("adversarial_hypotheses", []) if isinstance(report, dict) else [],
                            "tasks": report.get("investigation_tasks", []) if isinstance(report, dict) else [],
                        }
                    ],
                    "confidence_trajectory": [
                        {
                            "timestamp": now,
                            "stage": "sequence_validated",
                            "confidence": round(execution_confidence, 3),
                            "delta": round(execution_confidence - 0.35, 3),
                            "reason": "Execution sequence validated against the modeled protocol state machine.",
                        }
                    ],
                    "final_confidence": round(execution_confidence, 3),
                    "verdict_basis": {
                        "planner_action": planning_report.next_action.action,
                        "classical_summary": classical_summary,
                        "ml_summary": ml_summary,
                        "quantum_summary": quantum_summary,
                        "tutor_summary": tutor_note.summary if tutor_note else None,
                    },
                    "execution_sequence": sequence,
                }
            )

        for sequence in rejected_sequences:
            coverage = sequence.get("coverage", {}) if isinstance(sequence.get("coverage"), dict) else {}
            ledger.append(
                {
                    "hypothesis_id": sequence.get("hypothesis_id"),
                    "title": f"Rejected sequence: {sequence.get('subsystem')}",
                    "subsystem": sequence.get("subsystem"),
                    "status": "rejected_before_ranking",
                    "proof_attempts": [],
                    "falsification_attempts": [],
                    "confidence_trajectory": [
                        {
                            "timestamp": now,
                            "stage": "sequence_rejected",
                            "confidence": 0.0,
                            "delta": -0.35,
                            "reason": "; ".join(sequence.get("reasons", [])) or "Sequence validation rejected this path.",
                        }
                    ],
                    "final_confidence": 0.0,
                    "verdict_basis": {
                        "planner_action": planning_report.next_action.action,
                        "classical_summary": classical_summary,
                        "ml_summary": ml_summary,
                        "quantum_summary": quantum_summary,
                    },
                    "execution_sequence": {
                        "sequence_id": sequence.get("sequence_id"),
                        "hypothesis_id": sequence.get("hypothesis_id"),
                        "subsystem": sequence.get("subsystem"),
                        "coverage": coverage,
                        "validation": {
                            "is_valid": False,
                            "reasons": sequence.get("reasons", []),
                            "simulator_success": False,
                            "completeness_ratio": 0.0,
                            "transition_validity_ratio": 0.0,
                        },
                        "ordered_steps": [],
                    },
                }
            )
        return ledger

    def _build_evidence_objects(
        self,
        hypothesis_ledger: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Produce a structured HypothesisEvidenceObject for every ledger entry."""
        objects: list[dict[str, object]] = []
        for item in hypothesis_ledger:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("hypothesis_id") or "")
            execution_case = item.get("execution_case") if isinstance(item.get("execution_case"), dict) else {}
            execution_status = str((execution_case or {}).get("status") or "untested")
            sequence = item.get("execution_sequence") if isinstance(item.get("execution_sequence"), dict) else {}
            steps = list((sequence or {}).get("ordered_steps") or [])
            validation = (sequence or {}).get("validation") if isinstance((sequence or {}).get("validation"), dict) else {}

            evidence_contract_raw = (execution_case or {}).get("evidence_contract") if isinstance((execution_case or {}).get("evidence_contract"), dict) else {}
            if evidence_contract_raw:
                contract = BehavioralEvidenceContract.model_validate(evidence_contract_raw)
            else:
                contract = BehavioralEvidenceContract(
                    hypothesis_id=hypothesis_id,
                    target_contracts=list((execution_case or {}).get("target_contracts") or []),
                    target_functions=list((execution_case or {}).get("target_functions") or []),
                    actors=list((execution_case or {}).get("actors") or []),
                    preconditions=list((execution_case or {}).get("assumptions") or []),
                    sequence_steps=[
                        SequenceStep(
                            index=int(step.get("index") or idx + 1),
                            actor=str(step.get("caller") or "attacker"),
                            target=(str((execution_case or {}).get("target_contracts", ["unknown"])[0]) if (execution_case or {}).get("target_contracts") else "unknown"),
                            function=str(step.get("handler") or ""),
                            arguments=[],
                            expected_state_changes=list(step.get("expected_state_changes") or []),
                            observed_state_changes=list(step.get("observed_state_changes") or []),
                            expected_economic_effect=str(step.get("economic_role") or "") or None,
                            observed_economic_effect=None,
                        )
                        for idx, step in enumerate(steps)
                        if isinstance(step, dict)
                    ],
                    required_state_variables=[],
                    invariant_ids=list((execution_case or {}).get("violated_invariants") or []),
                    invariant_expression=str((execution_case or {}).get("invariant_assertion") or ""),
                    expected_pre_state={},
                    expected_transition={},
                    expected_post_state={},
                    required_economic_observations=[
                        name
                        for name, value in {
                            "attacker_profit": int((execution_case or {}).get("predicted_attacker_profit") or 0),
                            "protocol_loss": int((execution_case or {}).get("predicted_protocol_loss") or 0),
                            "victim_loss": int((execution_case or {}).get("predicted_victim_loss") or 0),
                        }.items()
                        if value > 0
                    ],
                    required_balance_observations=["attacker", "protocol"],
                    required_capital_movements=[
                        name
                        for name, value in {
                            "required_capital": int((execution_case or {}).get("required_capital") or 0),
                            "flashloan_principal": int((execution_case or {}).get("flashloan_principal") or 0),
                            "flashloan_fee": int((execution_case or {}).get("flashloan_fee") or 0),
                        }.items()
                        if value > 0
                    ],
                    required_external_calls=list((execution_case or {}).get("target_functions") or []),
                    required_flashloan=FlashloanRequirement(
                        required=int((execution_case or {}).get("flashloan_principal") or 0) > 0,
                        principal=int((execution_case or {}).get("flashloan_principal") or 0),
                        max_fee=int((execution_case or {}).get("flashloan_fee") or 0),
                    ),
                    confirmation_requirements=[
                        "validated_sequence_exists",
                        "required_actors_exist",
                        "preconditions_satisfied",
                        "sequence_executed",
                        "required_state_transition_occurred",
                        "invariant_evaluated",
                        "invariant_violated",
                        "economic_effect_observed",
                        "economic_reconciled",
                        "attributable_to_hypothesis",
                    ],
                )

            stage_history: list[StageAdvancement] = []

            # Stage 1: reconstruction produced this hypothesis
            stage_history.append(StageAdvancement(
                stage=HypothesisStage.ARCHITECTURALLY_PLAUSIBLE,
                advanced=True,
                reason="Hypothesis generated from expected-vs-observed subsystem gap.",
                confidence_delta=0.0,
            ))

            observed_values = (execution_case or {}).get("observed_values", {}) if isinstance((execution_case or {}).get("observed_values"), dict) else {}

            # Stage 2: execution sequence was reconstructed
            # If execution already produced deterministic proof criteria, treat path reachability as observed.
            proof_from_execution = bool(observed_values.get("proof_criteria_satisfied"))
            sequence_valid = bool((validation or {}).get("is_valid")) or proof_from_execution
            stage_history.append(StageAdvancement(
                stage=HypothesisStage.ECONOMICALLY_REACHABLE,
                advanced=sequence_valid,
                reason=(
                    "Execution sequence passed state-machine validation."
                    if sequence_valid
                    else "; ".join(list((validation or {}).get("reasons") or [])
                                   or ["No validated execution sequence available."])
                ),
                confidence_delta=0.15 if sequence_valid else 0.0,
            ))

            # Stage 3: Foundry test was generated and executed
            executed = execution_status not in {"untested", "execution_blocked_toolchain"}
            stage_history.append(StageAdvancement(
                stage=HypothesisStage.BEHAVIORALLY_EXECUTABLE,
                advanced=executed,
                reason=(
                    f"Foundry case executed with status: {execution_status}."
                    if executed
                    else str((execution_case or {}).get("rationale") or "No behavioral test was generated.")
                ),
                confidence_delta=0.20 if executed else 0.0,
            ))

            contradiction_observed = execution_status in {"execution_behavior_not_observed", "execution_economic_effect_not_observed"}
            provenance = (execution_case or {}).get("evidence_provenance", {}) if isinstance((execution_case or {}).get("evidence_provenance"), dict) else {}
            attributable_to_hypothesis = str(provenance.get("hypothesis_id") or hypothesis_id) == hypothesis_id

            sequence_executed = execution_status not in {"untested", "execution_blocked_toolchain", "execution_unknown"}
            required_state_transition_occurred = bool(observed_values.get("state_transition_occurred"))
            invariant_evaluated = bool(observed_values.get("invariant_evaluated"))
            invariant_violated = bool(observed_values.get("invariant_violated"))

            economic_effect_observed = bool(observed_values.get("economic_effect_observed"))
            economic_reconciled = bool(observed_values.get("economic_reconciled"))

            preconditions_satisfied = bool(observed_values.get("preconditions_satisfied")) or not contract.preconditions
            required_actors_exist = bool(contract.actors)

            if proof_from_execution and not contract.invariant_expression:
                contract.invariant_expression = "proof_criteria_observed"

            gate = self.behavioral_evidence_gate.evaluate(
                contract,
                execution_status=execution_status,
                validated_sequence_exists=sequence_valid,
                required_actors_exist=required_actors_exist,
                preconditions_satisfied=preconditions_satisfied,
                sequence_executed=sequence_executed,
                required_state_transition_occurred=required_state_transition_occurred,
                invariant_evaluated=invariant_evaluated,
                invariant_violated=invariant_violated,
                economic_effect_observed=economic_effect_observed,
                economic_reconciled=economic_reconciled,
                attributable_to_hypothesis=attributable_to_hypothesis,
                toolchain_blocked=execution_status == "execution_blocked_toolchain",
                reachability_blocked=execution_status == "execution_reachability_failed",
                assumption_gap=execution_status == "execution_assumption_gap_flashloan",
                contradiction_observed=contradiction_observed,
                synthetic_execution=execution_status == "execution_inconclusive_synthetic",
                proof_criteria_satisfied=bool(observed_values.get("proof_criteria_satisfied")),
            )

            # Stage 4: invariant was violated (deterministic and observed)
            invariant_broken = gate.observed.get("invariant_violated", False) is True
            stage_history.append(StageAdvancement(
                stage=HypothesisStage.INVARIANT_VIOLATED,
                advanced=invariant_broken,
                reason=(
                    "Behavioral execution produced an observed invariant violation."
                    if invariant_broken
                    else "No invariant violation observed in the current execution."
                ),
                confidence_delta=0.30 if invariant_broken else 0.0,
            ))

            # Stage 5: finding confirmed
            confirmed = gate.verdict == BehavioralVerdict.BEHAVIORALLY_CONFIRMED
            stage_history.append(StageAdvancement(
                stage=HypothesisStage.FINDING_CONFIRMED,
                advanced=confirmed,
                reason=(
                    gate.rationale
                    if confirmed
                    else "Finding is not confirmed by deterministic behavioral evidence requirements."
                ),
                confidence_delta=0.35 if confirmed else 0.0,
            ))

            current_stage = (
                HypothesisStage.FINDING_CONFIRMED if confirmed
                else HypothesisStage.INVARIANT_VIOLATED if invariant_broken
                else HypothesisStage.BEHAVIORALLY_EXECUTABLE if executed
                else HypothesisStage.ECONOMICALLY_REACHABLE if sequence_valid
                else HypothesisStage.ARCHITECTURALLY_PLAUSIBLE
            )
            verdict = gate.verdict.value

            required_capital = int((execution_case or {}).get("required_capital") or 0)
            flashloan_principal = int((execution_case or {}).get("flashloan_principal") or 0)
            flashloan_fee = int((execution_case or {}).get("flashloan_fee") or 0)
            predicted_attacker_profit = int((execution_case or {}).get("predicted_attacker_profit") or 0)
            predicted_protocol_loss = int((execution_case or {}).get("predicted_protocol_loss") or 0)
            predicted_victim_loss = int((execution_case or {}).get("predicted_victim_loss") or 0)

            limitations: list[str] = []
            if execution_status == "execution_assumption_gap_flashloan":
                limitations.append("Flashloan mechanism was not reproduced; scenario remains an economic capital assumption.")
            if execution_status in {"execution_inconclusive_synthetic", "execution_economic_impact_not_confirmed"}:
                limitations.append("Post-state economic impact was not confirmed by measured deltas.")
            if execution_status == "execution_behavior_not_observed":
                limitations.append("Behavioral sequence executed but did not produce the expected state transition.")
            if execution_status == "execution_inconclusive_reconciliation":
                limitations.append("Economic accounting signals were not reconcilable across protocol/attacker ledgers.")

            evidence_strength = {
                "execution": "OBSERVED" if bool(gate.observed.get("sequence_executed")) else "UNRESOLVED",
                "reachability": "OBSERVED" if bool(gate.observed.get("validated_sequence_exists")) else "NOT_OBSERVED",
                "behavioral": "OBSERVED" if bool(gate.observed.get("required_state_transition_occurred")) else "NOT_OBSERVED",
                "invariant": "OBSERVED" if bool(gate.observed.get("invariant_violated")) else ("NOT_OBSERVED" if bool(gate.observed.get("invariant_evaluated")) else "UNRESOLVED"),
                "economic": "OBSERVED" if bool(gate.observed.get("economic_effect_observed")) else "NOT_OBSERVED",
                "reconciliation": "OBSERVED" if bool(gate.observed.get("economic_reconciled")) else "NOT_OBSERVED",
                "proof_criteria": "OBSERVED" if bool(gate.observed.get("proof_criteria_satisfied")) else "NOT_OBSERVED",
            }
            missing_evidence = [key for key, value in evidence_strength.items() if value in {"NOT_OBSERVED", "UNRESOLVED"}]

            evidence_obj = HypothesisEvidenceObject(
                hypothesis_id=hypothesis_id,
                title=str(item.get("title") or ""),
                subsystem=str(item.get("subsystem") or ""),
                current_stage=current_stage,
                stage_history=stage_history,
                reconstructed_protocol_state={
                    "initial_state": (sequence or {}).get("initial_state"),
                    "resulting_state": (sequence or {}).get("resulting_protocol_state"),
                },
                required_assumptions=list((sequence or {}).get("violated_assumptions") or []),
                required_actors=list({str(step.get("caller") or "") for step in steps if isinstance(step, dict) and step.get("caller")}),
                required_permissions=list({p for step in steps if isinstance(step, dict) for p in (step.get("permissions_required") or [])}),
                executable_sequence=steps,
                expected_invariant=str((execution_case or {}).get("invariant_assertion") or ""),
                observed_invariant_result=execution_status,
                accounting_delta=str((execution_case or {}).get("economic_consequence") or ""),
                state_transition=f"{(sequence or {}).get('initial_state')} -> {(sequence or {}).get('resulting_protocol_state')}",
                execution_logs=[
                    str(step)
                    for step in list((execution_case or {}).get("execution_steps") or [])[:8]
                ],
                foundry_test_reference=str((execution_case or {}).get("test_name") or "") or None,
                environment="foundry_fork",
                fork_block=None,
                assumptions=list((execution_case or {}).get("assumptions") or []),
                limitations=limitations,
                predicted_values={
                    "required_capital": required_capital,
                    "flashloan_principal": flashloan_principal,
                    "flashloan_fee": flashloan_fee,
                    "predicted_attacker_profit": predicted_attacker_profit,
                    "predicted_protocol_loss": predicted_protocol_loss,
                    "predicted_victim_loss": predicted_victim_loss,
                },
                observed_values={
                    "execution_steps_exercised": len(list((execution_case or {}).get("execution_steps") or [])),
                    "attack_path_completed": bool(observed_values.get("attack_path_completed")),
                    "state_transition_occurred": bool(gate.observed.get("required_state_transition_occurred")),
                    "invariant_evaluated": bool(gate.observed.get("invariant_evaluated")),
                    "invariant_violated": bool(gate.observed.get("invariant_violated")),
                    "economic_effect_observed": bool(gate.observed.get("economic_effect_observed")),
                    "economic_reconciled": bool(gate.observed.get("economic_reconciled")),
                    "proof_criteria_satisfied": bool(gate.observed.get("proof_criteria_satisfied")),
                    "attributable_to_hypothesis": bool(gate.observed.get("attributable_to_hypothesis")),
                    "observed_attacker_profit": int(observed_values.get("observed_attacker_profit") or 0),
                    "required_capital_observed": int(observed_values.get("required_capital_observed") or 0),
                    "flashloan_principal_observed": int(observed_values.get("flashloan_principal_observed") or 0),
                    "flashloan_fee_observed": int(observed_values.get("flashloan_fee_observed") or 0),
                    "attacker_net_pnl": int(observed_values.get("attacker_net_pnl") or 0),
                    "protocol_direct_token_loss": int(observed_values.get("protocol_direct_token_loss") or 0),
                    "protocol_liveness_loss": bool(observed_values.get("protocol_liveness_loss")),
                    "user_access_impairment_score": int(observed_values.get("user_access_impairment_score") or 0),
                },
                invariant_delta={
                    "violated_invariant_count": len(list((execution_case or {}).get("violated_invariants") or [])),
                },
                economic_delta={
                    "observed_attacker_profit": int(observed_values.get("observed_attacker_profit") or 0),
                    "predicted_attacker_profit": predicted_attacker_profit,
                    "profit_difference": int(observed_values.get("observed_attacker_profit") or 0) - predicted_attacker_profit,
                    "predicted_protocol_loss": predicted_protocol_loss,
                    "predicted_victim_loss": predicted_victim_loss,
                    "attacker_net_pnl": int(observed_values.get("attacker_net_pnl") or 0),
                    "protocol_direct_token_loss": int(observed_values.get("protocol_direct_token_loss") or 0),
                    "protocol_liveness_loss": bool(observed_values.get("protocol_liveness_loss")),
                    "user_access_impairment_score": int(observed_values.get("user_access_impairment_score") or 0),
                },
                economic_reconciliation={
                    "status": evidence_strength.get("reconciliation"),
                    "rationale": gate.rationale,
                },
                evidence_strength=evidence_strength,
                missing_evidence=list(dict.fromkeys([*missing_evidence, *gate.failed_requirements])),
                verdict=verdict,
                verdict_basis=gate.rationale,
                final_confidence=float(item.get("final_confidence") or 0.0),
            )
            objects.append(evidence_obj.model_dump())
        return objects

    @staticmethod
    def _merge_execution_sequences(
        *,
        hypothesis_ledger: list[dict[str, object]],
        validated_sequences: list[dict[str, object]],
        rejected_sequences: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        by_hypothesis: dict[str, dict[str, object]] = {
            str(item.get("hypothesis_id") or ""): item
            for item in hypothesis_ledger
            if isinstance(item, dict)
        }

        for sequence in validated_sequences:
            if not isinstance(sequence, dict):
                continue
            hypothesis_id = str(sequence.get("hypothesis_id") or "")
            target = by_hypothesis.get(hypothesis_id)
            if not target:
                continue
            target["execution_sequence"] = sequence
            validation = sequence.get("validation") if isinstance(sequence.get("validation"), dict) else {}
            if bool(validation.get("is_valid")):
                target["status"] = "sequence_validated"
            else:
                target["status"] = "sequence_rejected"

        for sequence in rejected_sequences:
            if not isinstance(sequence, dict):
                continue
            hypothesis_id = str(sequence.get("hypothesis_id") or "")
            target = by_hypothesis.get(hypothesis_id)
            if not target:
                continue
            target["execution_sequence"] = {
                "sequence_id": sequence.get("sequence_id"),
                "hypothesis_id": sequence.get("hypothesis_id"),
                "subsystem": sequence.get("subsystem"),
                "coverage": sequence.get("coverage", {}),
                "validation": {
                    "is_valid": False,
                    "reasons": sequence.get("reasons", []),
                    "simulator_success": False,
                    "completeness_ratio": 0.0,
                    "transition_validity_ratio": 0.0,
                },
                "ordered_steps": [],
            }
            target["status"] = "sequence_rejected"

        for item in hypothesis_ledger:
            if not isinstance(item, dict):
                continue
            has_sequence = bool(item.get("execution_sequence"))
            has_case = bool(item.get("execution_case"))
            if not has_sequence and not has_case and str(item.get("status") or "") in {"", "unresolved", "pending_verification", "tested", "provisionally_supported", "risk_flagged"}:
                item["status"] = "untested"
        return hypothesis_ledger

    @staticmethod
    def _merge_falsification_case_statuses(
        *,
        hypothesis_ledger: list[dict[str, object]],
        execution_cases: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        by_hypothesis: dict[str, dict[str, object]] = {
            str(item.get("hypothesis_id") or ""): item
            for item in hypothesis_ledger
            if isinstance(item, dict)
        }
        for case in execution_cases:
            if not isinstance(case, dict):
                continue
            hypothesis_id = str(case.get("hypothesis_id") or "")
            target = by_hypothesis.get(hypothesis_id)
            if not target:
                continue

            execution_status = str(case.get("status") or "execution_unknown")
            target["execution_case"] = {
                "test_name": case.get("test_name"),
                "status": execution_status,
                "rationale": case.get("rationale"),
                "should_fail": case.get("should_fail"),
                "execution_sequence_id": case.get("execution_sequence_id"),
                "execution_steps": case.get("execution_steps", []),
                "economic_consequence": case.get("economic_consequence", ""),
                "violated_invariants": case.get("violated_invariants", []),
                "target_contracts": case.get("target_contracts", []),
                "target_addresses": case.get("target_addresses", []),
                "target_functions": case.get("target_functions", []),
                "target_invariants": case.get("target_invariants", []),
                "invariant_assertion": case.get("invariant_assertion"),
                "proof_marker": case.get("proof_marker"),
                "proof_summary": case.get("proof_summary"),
                "required_capital": case.get("required_capital", 0),
                "flashloan_principal": case.get("flashloan_principal", 0),
                "flashloan_fee": case.get("flashloan_fee", 0),
                "predicted_attacker_profit": case.get("predicted_attacker_profit", 0),
                "predicted_protocol_loss": case.get("predicted_protocol_loss", 0),
                "predicted_victim_loss": case.get("predicted_victim_loss", 0),
                "assumptions": case.get("assumptions", []),
                "actors": case.get("actors", []),
                "sequence_source": case.get("sequence_source", ""),
                "evidence_contract": case.get("evidence_contract", {}),
                "observed_values": case.get("observed_values", {}),
                "evidence_provenance": case.get("evidence_provenance", {}),
            }

            if execution_status in {"supported_by_execution"}:
                target["status"] = "supported"
            elif execution_status == "falsification_triggered":
                target["status"] = "disproved"
            elif execution_status == "execution_blocked_toolchain":
                target["status"] = "execution_blocked"
            elif execution_status in {
                "execution_assumption_gap_flashloan",
                "execution_reachability_failed",
                "execution_economic_impact_not_confirmed",
                "execution_inconclusive_synthetic",
                "execution_behavior_not_observed",
                "execution_economic_effect_not_observed",
                "execution_inconclusive_reconciliation",
                "execution_invariant_not_testable",
            }:
                target["status"] = "inconclusive"
            elif execution_status == "execution_proof_criteria_satisfied":
                target["status"] = "supported"
            elif execution_status == "execution_unknown":
                target["status"] = target.get("status", "unresolved")

        for item in hypothesis_ledger:
            if not isinstance(item, dict):
                continue
            if "execution_case" not in item:
                item["execution_case"] = {
                    "status": "untested",
                    "rationale": "No Foundry case was generated for this hypothesis yet.",
                    "test_name": None,
                    "should_fail": False,
                    "execution_sequence_id": None,
                    "execution_steps": [],
                    "economic_consequence": "",
                    "violated_invariants": [],
                    "target_contracts": [],
                    "target_addresses": [],
                    "target_functions": [],
                    "target_invariants": [],
                    "invariant_assertion": None,
                    "proof_marker": None,
                    "proof_summary": None,
                    "required_capital": 0,
                    "flashloan_principal": 0,
                    "flashloan_fee": 0,
                    "predicted_attacker_profit": 0,
                    "predicted_protocol_loss": 0,
                    "predicted_victim_loss": 0,
                    "assumptions": [],
                    "actors": [],
                    "sequence_source": "",
                    "evidence_contract": {},
                    "observed_values": {},
                    "evidence_provenance": {},
                }
            if item.get("status") in {None, "", "unresolved", "tests"} and str((item.get("execution_case") or {}).get("status") or "") == "untested":
                item["status"] = "untested"
        return hypothesis_ledger

    @staticmethod
    def _build_hypothesis_evidence_ledger(
        *,
        hypotheses: list[dict[str, object]],
        investigation_reports: list[dict[str, object]],
        tutor_notes: list[TutorResearchNote],
        missing_expected_subsystems: list[str],
        planning_report: PlanningReport,
        classical_summary: str,
        ml_summary: str,
        quantum_summary: str,
    ) -> list[dict[str, object]]:
        now = datetime.now(UTC).isoformat()
        missing = {item.lower() for item in missing_expected_subsystems}
        tutor_lookup = {
            (note.subsystem or note.concept or "").lower(): note
            for note in tutor_notes
        }
        ledger: list[dict[str, object]] = []

        for hypothesis in hypotheses:
            if not isinstance(hypothesis, dict):
                continue

            subsystem = str(hypothesis.get("missing_subsystem") or "")
            subsystem_key = subsystem.lower()
            linked_report = next(
                (
                    report
                    for report in investigation_reports
                    if isinstance(report, dict) and subsystem_key and subsystem_key in str(report.get("subsystem") or "").lower()
                ),
                None,
            )
            linked_tutor = tutor_lookup.get(subsystem_key)

            confidence_events: list[dict[str, object]] = []
            running_confidence = 0.35

            confidence_events.append(
                {
                    "timestamp": now,
                    "stage": "surfaced",
                    "confidence": round(running_confidence, 3),
                    "delta": 0.0,
                    "reason": "Hypothesis surfaced from expected-vs-observed subsystem mismatch.",
                }
            )

            if linked_report:
                risk_signal = str(linked_report.get("overall_risk_signal") or "").lower()
                if "low" in risk_signal:
                    delta = 0.12
                elif "high" in risk_signal or "critical" in risk_signal:
                    delta = -0.15
                else:
                    delta = -0.05
                running_confidence = max(0.0, min(1.0, running_confidence + delta))
                confidence_events.append(
                    {
                        "timestamp": now,
                        "stage": "falsification_attempt",
                        "confidence": round(running_confidence, 3),
                        "delta": round(delta, 3),
                        "reason": f"Adversarial investigation risk signal: {risk_signal or 'unknown'}.",
                    }
                )

            if linked_tutor:
                delta = 0.08 if linked_tutor.verified else 0.03
                running_confidence = max(0.0, min(1.0, running_confidence + delta))
                confidence_events.append(
                    {
                        "timestamp": now,
                        "stage": "proof_attempt",
                        "confidence": round(running_confidence, 3),
                        "delta": round(delta, 3),
                        "reason": (
                            "Tutor research was verified against repository evidence."
                            if linked_tutor.verified
                            else "Tutor supplied candidate evidence pending verification."
                        ),
                    }
                )

            status = "unresolved"
            if running_confidence >= 0.7 and subsystem_key not in missing:
                status = "provisionally_supported"
            elif running_confidence <= 0.25:
                status = "risk_flagged"
            elif linked_tutor and not linked_tutor.verified:
                status = "pending_verification"
            elif linked_report:
                status = "tested"

            ledger.append(
                {
                    "hypothesis_id": hypothesis.get("hypothesis_id"),
                    "title": hypothesis.get("title"),
                    "subsystem": subsystem,
                    "pattern_label": hypothesis.get("pattern_label"),
                    "threat_vectors": hypothesis.get("threat_vectors", []),
                    "evidence_needed": hypothesis.get("evidence_needed", []),
                    "required_actors": hypothesis.get("required_actors", []),
                    "required_assumptions": hypothesis.get("required_assumptions", []),
                    "expected_attack_sequence": hypothesis.get("expected_attack_sequence", []),
                    "expected_state_transition": hypothesis.get("expected_state_transition", ""),
                    "required_capital": hypothesis.get("required_capital", 0),
                    "flashloan_principal": hypothesis.get("flashloan_principal", 0),
                    "flashloan_fee": hypothesis.get("flashloan_fee", 0),
                    "predicted_attacker_profit": hypothesis.get("predicted_attacker_profit", 0),
                    "predicted_protocol_loss": hypothesis.get("predicted_protocol_loss", 0),
                    "predicted_victim_loss": hypothesis.get("predicted_victim_loss", 0),
                    "economic_consequence": hypothesis.get("economic_consequence", ""),
                    "status": status,
                    "proof_attempts": [
                        {
                            "attempt_id": f"proof:{hypothesis.get('hypothesis_id')}:tutor",
                            "source": "tutor_research",
                            "summary": linked_tutor.summary if linked_tutor else "No tutor evidence acquired yet.",
                            "verified": linked_tutor.verified if linked_tutor else False,
                            "evidence_targets": linked_tutor.evidence_targets if linked_tutor else [],
                        }
                    ],
                    "falsification_attempts": [
                        {
                            "attempt_id": f"falsify:{hypothesis.get('hypothesis_id')}:investigator",
                            "source": "investigator",
                            "risk_signal": (linked_report or {}).get("overall_risk_signal"),
                            "adversarial_hypotheses": (linked_report or {}).get("adversarial_hypotheses", []),
                            "tasks": (linked_report or {}).get("investigation_tasks", []),
                        }
                    ],
                    "confidence_trajectory": confidence_events,
                    "final_confidence": round(running_confidence, 3),
                    "verdict_basis": {
                        "planner_action": planning_report.next_action.action,
                        "classical_summary": classical_summary,
                        "ml_summary": ml_summary,
                        "quantum_summary": quantum_summary,
                    },
                }
            )

        return ledger

    def run(
        self,
        *,
        repository_path: Path | str,
        eir: EconomicIntermediateRepresentation,
        program_scope: str | None = None,
    ) -> dict[str, object]:
        repository_context = self.repository_agent.collect_repository_context(
            repository_path=repository_path,
            program_scope=program_scope,
            known_issues=None,
        )

        methodology_report = self.methodology_pipeline.run(
            eir=eir,
            repository_context=repository_context,
        )

        reconstruction = self.protocol_reconstruction_engine.reconstruct(repository_path=repository_path)
        semantics = self.protocol_semantics_engine.reconstruct(repository_path=repository_path)
        pattern_result = self.protocol_pattern_engine.classify(
            repository_path=repository_path,
            repository_context=repository_context,
            eir=eir,
        )
        expected_model = self.expected_model_registry.get(pattern_result.pattern_id)
        expectation_graph = self.expectation_graph_engine.build(expected_model)
        subsystem_plan = self.subsystem_discovery_engine.discover(
            repository_path=repository_path,
            protocol_pattern=pattern_result.pattern_id,
        )
        subsystem_reconstructions = self.subsystem_reconstruction_engine.reconstruct(repository_path=repository_path, audit_plan=subsystem_plan)
        expected_observed = self.expected_observed_comparator.compare(
            expected_model=expected_model,
            observed_subsystems=[item.name for item in subsystem_reconstructions.subsystems],
        )
        research_hypotheses = self.hypothesis_generator.generate(
            comparison=expected_observed,
            pattern_label=pattern_result.label,
            pattern_id=pattern_result.pattern_id,
        )
        repository_model = load_repository(str(repository_path))
        quantum_hypotheses = self.quantum_hypothesis_engine.generate(
            repository_model=repository_model,
            pattern_label=pattern_result.label,
            pattern_id=pattern_result.pattern_id,
            existing_hypothesis_ids=[hypothesis.hypothesis_id for hypothesis in research_hypotheses],
        )
        if quantum_hypotheses:
            research_hypotheses = [*research_hypotheses, *quantum_hypotheses]
        source_facts = [
            f"source_root={repository_model.root / 'src' if (repository_model.root / 'src').exists() else repository_model.root}",
            f"contract_files={len(repository_model.contract_files)}",
            f"interfaces={','.join(repository_model.interfaces[:5]) or 'none'}",
            f"inherited_contracts={','.join(repository_model.inherited_contracts[:5]) or 'none'}",
        ]
        evidence_graph = EvidenceGraph(
            nodes=[
                EvidenceNode(
                    id=f"evidence:{eir.protocol_name}:scope",
                    kind=EvidenceNodeKind.EVIDENCE,
                    label="Repository scope",
                    evidence_type="scope",
                    metadata={"scope": repository_context.scope_summary or "unknown"},
                ),
                EvidenceNode(
                    id=f"evidence:{eir.protocol_name}:invariants",
                    kind=EvidenceNodeKind.CLAIM,
                    label="Protocol invariants",
                    evidence_type="invariant",
                    metadata={"invariants": [invariant.expression for invariant in eir.invariants]},
                ),
            ],
            edges=[
                EvidenceEdge(
                    source=f"evidence:{eir.protocol_name}:scope",
                    target=f"evidence:{eir.protocol_name}:invariants",
                    kind=EvidenceEdgeKind.SUPPORTS,
                    metadata={"phase": "phase4"},
                )
            ],
        )

        for subsystem in subsystem_reconstructions.subsystems:
            for trace_index, trace in enumerate(subsystem.implementation_traces):
                trace_node_id = f"evidence:{subsystem.name.lower()}:trace:{trace_index}"
                evidence_graph.nodes.append(
                    EvidenceNode(
                        id=trace_node_id,
                        kind=EvidenceNodeKind.EVIDENCE,
                        label=f"{subsystem.name} implementation trace {trace_index + 1}",
                        evidence_type="implementation_trace",
                        metadata={
                            "subsystem": subsystem.name,
                            "equation": trace.equation,
                            "functions": trace.functions,
                            "modifiers": trace.modifiers,
                            "interfaces": trace.interfaces,
                            "events": trace.events,
                        },
                    )
                )
                evidence_graph.edges.append(
                    EvidenceEdge(
                        source=f"evidence:{eir.protocol_name}:scope",
                        target=trace_node_id,
                        kind=EvidenceEdgeKind.SUPPORTS,
                        metadata={"subsystem": subsystem.name, "role": "implementation_trace"},
                    )
                )
                evidence_graph.edges.append(
                    EvidenceEdge(
                        source=trace_node_id,
                        target=f"evidence:{eir.protocol_name}:invariants",
                        kind=EvidenceEdgeKind.REINFORCES,
                        metadata={"subsystem": subsystem.name, "role": "trace_invariant_support"},
                    )
                )
        equation_provenance: list[dict[str, object]] = []
        for item in subsystem_reconstructions.subsystems:
            for equation in [*(item.mathematical_model.state_equations if item.mathematical_model else []), *(item.mathematical_model.conservation_equations if item.mathematical_model else []), *(item.mathematical_model.balance_equations if item.mathematical_model else [])]:
                equation_provenance.append(
                    {
                        "expression": equation,
                        "subsystem": item.name,
                        "evidence": self._serialize_evidence(item.mathematical_model.evidence if item.mathematical_model else []),
                    }
                )

        semantic_dossiers = self._build_semantic_dossiers(
            subsystem_reconstructions=subsystem_reconstructions.subsystems,
            expected_subsystems=expected_model.expected_subsystems,
        )
        investigation_reports = self.investigator_engine.investigate_all(
            subsystem_dossiers=semantic_dossiers,
        )
        serialized_investigations = serialize_investigation_reports(investigation_reports)

        historical_learning_signals = [
            f"pattern={pattern_result.label}",
            f"expected_subsystems={len(expected_model.expected_subsystems)}",
            f"missing_expected={len(expected_observed.missing_expected)}",
            *(f"issue:{issue}" for issue in repository_context.known_issues[:3]),
        ]
        exploration_objectives = [
            *(
                f"Find a sequence that invalidates {hypothesis.missing_subsystem} within {pattern_result.label}"
                for hypothesis in research_hypotheses[:2]
            ),
            f"Find any path where net protocol accounting remains balanced but user value is redistributed in {eir.protocol_name}",
        ]

        initial_planning = self.planning_engine.plan(
            pattern_label=pattern_result.label,
            expectation_match_ratio=expected_observed.match_ratio,
            missing_expected_subsystems=expected_observed.missing_expected,
            investigation_reports=serialized_investigations,
            tutor_notes=[],
            historical_learning_signals=historical_learning_signals,
        )
        tutor_notes: list[TutorResearchNote] = []
        lessons_used: dict[str, list[str]] = {}
        if initial_planning.should_invoke_tutor:
            for missing_subsystem in expected_observed.missing_expected[:3]:
                prior_lessons = self.training_engine.retrieve_lessons(
                    pattern_label=pattern_result.label,
                    subsystem=missing_subsystem,
                    concept=missing_subsystem,
                    top_k=5,
                )
                lessons_used[missing_subsystem] = [lesson.insight for lesson in prior_lessons]
                tutor_notes.append(
                    self.tutor_engine.research(
                        concept=missing_subsystem,
                        subsystem=missing_subsystem,
                        protocol_pattern=pattern_result.label,
                        repository_facts=source_facts,
                        expected_guarantees=expected_model.canonical_math,
                        context=repository_context.scope_summary,
                        prior_lessons=[lesson.insight for lesson in prior_lessons],
                    )
                )

        verification_reports: list[VerificationReport] = []
        for note in tutor_notes:
            verification = self.verification_engine.verify_tutor_note(
                note=note,
                repository_model=repository_model,
                expected_guarantees=expected_model.canonical_math,
            )
            verification_reports.append(verification)
            note.verified = verification.verified
            note.confidence = round(max(note.confidence, min(0.95, verification.verification_score)), 3)
            if not verification.verified and verification.missing_terms:
                note.open_questions = [
                    *note.open_questions,
                    f"Verification missing terms: {', '.join(verification.missing_terms[:6])}",
                ]

        planning_report = self.planning_engine.plan(
            pattern_label=pattern_result.label,
            expectation_match_ratio=expected_observed.match_ratio,
            missing_expected_subsystems=expected_observed.missing_expected,
            investigation_reports=serialized_investigations,
            tutor_notes=[{
                "concept": note.concept,
                "verified": note.verified,
                "summary": note.summary,
            } for note in tutor_notes],
            historical_learning_signals=historical_learning_signals,
        )

        execution_sequence_report = self.execution_sequence_engine.reconstruct(
            protocol_name=eir.protocol_name,
            eir=eir,
            subsystem_reconstructions=subsystem_reconstructions.subsystems,
            investigation_reports=investigation_reports,
        )
        serialized_execution_sequences = [
            self._serialize_execution_sequence(sequence)
            for sequence in execution_sequence_report.validated_sequences
        ]
        serialized_rejected_execution_sequences = [
            {
                "sequence_id": item.sequence_id,
                "hypothesis_id": item.hypothesis_id,
                "subsystem": item.subsystem,
                "reasons": item.reasons,
                "coverage": self._serialize_execution_coverage(item.coverage),
            }
            for item in execution_sequence_report.rejected_sequences
        ]
        serialized_execution_coverage = [
            self._serialize_execution_coverage(item)
            for item in execution_sequence_report.coverage_by_subsystem
        ]

        truth_layer = MathematicalTruthLayer(
            subsystem_id=repository_path.name if isinstance(repository_path, Path) else str(repository_path),
            transition_matrix_ref=f"matrix:{eir.protocol_name}",
            state_graph_ref=f"graph:{eir.protocol_name}",
            authority_graph_ref=f"authority:{eir.protocol_name}",
            constraint_graph_ref=f"constraints:{eir.protocol_name}",
            evidence_graph_ref=f"evidence:{eir.protocol_name}",
            optimization_formulation="maximize protocol health while preserving solvency and operational safety",
            economic_equations=[invariant.expression for invariant in eir.invariants] + [reconstructed.expression for reconstructed in reconstruction.invariants],
            equation_provenance=equation_provenance,
            source_facts=source_facts,
            scope_context=repository_context.scope_summary,
            known_issues=repository_context.known_issues,
            variable_names=[variable.name for variable in eir.variables] + [entity.name for entity in reconstruction.entities if entity.kind in {"state_variable", "economic_variable"}],
            objective_expressions=[objective.expression for objective in eir.objectives] + [f"preserve {entity.name}" for entity in reconstruction.entities if entity.kind in {"contract", "actor"}],
            evidence_summary=(
                f"Repository context for {eir.protocol_name} with {len(repository_context.markdown_files)} markdown files "
                f"and {len(repository_context.source_files)} source files"
            ),
            expected_subsystems=expected_model.expected_subsystems,
            expected_canonical_equations=expected_model.canonical_math,
            expectation_match_ratio=expected_observed.match_ratio,
            missing_expected_subsystems=expected_observed.missing_expected,
            investigation_risk_signals=[report.overall_risk_signal for report in investigation_reports],
            adversarial_hypothesis_count=sum(len(report.adversarial_hypotheses) for report in investigation_reports),
            protocol_pattern_label=pattern_result.label,
            semantic_dossiers=semantic_dossiers,
            investigation_reports=serialized_investigations,
            research_hypotheses=[
                {
                    "hypothesis_id": h.hypothesis_id,
                    "title": h.title,
                    "missing_subsystem": h.missing_subsystem,
                    "priority": h.priority,
                }
                for h in research_hypotheses
            ],
            historical_learning_signals=historical_learning_signals,
            exploration_objectives=exploration_objectives,
            subsystem_reconstructions=[
                {
                    "id": item.id,
                    "name": item.name,
                    "state_machine_states": item.state_machine.states,
                    "state_machine_transitions": [self._serialize_transition(transition) for transition in item.state_machine.transitions],
                    "accounting_model": item.accounting_model.name if item.accounting_model else None,
                    "permission_model_roles": item.permission_model.roles if item.permission_model else [],
                    "invariant_count": len(item.invariants),
                    "confidence": item.confidence,
                    "dependencies": [
                        {"source": edge.source, "target": edge.target, "relation": edge.relation, "semantic_role": edge.semantic_role}
                        for edge in item.dependency_model.dependency_edges
                    ],
                    "economic_model": {
                        "assets_entering": item.economic_model.assets_entering if item.economic_model else [],
                        "assets_leaving": item.economic_model.assets_leaving if item.economic_model else [],
                        "value_conservation": item.economic_model.value_conservation if item.economic_model else [],
                        "participant_incentives": item.economic_model.participant_incentives if item.economic_model else [],
                        "capital_flow": item.economic_model.capital_flow if item.economic_model else [],
                        "economic_assumptions": item.economic_model.economic_assumptions if item.economic_model else [],
                        "failure_scenarios": item.economic_model.failure_scenarios if item.economic_model else [],
                    } if item.economic_model else None,
                    "trust_assumptions": {
                        "assumptions": item.trust_model.assumptions,
                        "failure_assumptions": item.trust_model.failure_assumptions,
                        "safety_assumptions": item.trust_model.safety_assumptions,
                    },
                    "evidence": self._serialize_evidence(
                        [*item.identity.evidence, *item.contract_membership.evidence, *item.state_model.evidence] if item.identity and item.contract_membership and item.state_model else []
                    ),
                    "guarantees": [
                        {
                            "id": guarantee.id,
                            "statement": guarantee.statement,
                            "rationale": guarantee.rationale,
                            "threat_model": guarantee.threat_model,
                        }
                        for guarantee in item.guarantees
                    ],
                    "mathematical_specification": {
                        "goal": item.mathematical_specification.goal if item.mathematical_specification else None,
                        "assets": item.mathematical_specification.assets if item.mathematical_specification else [],
                        "liabilities": item.mathematical_specification.liabilities if item.mathematical_specification else [],
                        "accounting_equations": item.mathematical_specification.accounting_equations if item.mathematical_specification else [],
                        "conservation_equations": item.mathematical_specification.conservation_equations if item.mathematical_specification else [],
                        "economic_constraints": item.mathematical_specification.economic_constraints if item.mathematical_specification else [],
                        "safety_bounds": item.mathematical_specification.safety_bounds if item.mathematical_specification else [],
                        "permission_constraints": item.mathematical_specification.permission_constraints if item.mathematical_specification else [],
                    } if item.mathematical_specification else None,
                    "implementation_traces": [
                        {
                            "equation": trace.equation,
                            "storage_variables": trace.storage_variables,
                            "functions": trace.functions,
                            "entrypoints": trace.entrypoints,
                            "internal_calls": trace.internal_calls,
                            "modifiers": trace.modifiers,
                            "constants": trace.constants,
                            "errors": trace.errors,
                            "structs": trace.structs,
                            "enums": trace.enums,
                            "interfaces": trace.interfaces,
                            "libraries": trace.libraries,
                            "events": trace.events,
                            "tests": trace.tests,
                            "call_graph": trace.call_graph,
                        }
                        for trace in item.implementation_traces
                    ],
                    "evidence_quality": item.evidence_quality,
                    "completeness_status": item.completeness_status,
                    "missing_components": item.missing_components,
                }
                for item in subsystem_reconstructions.subsystems
            ],
            execution_sequences=serialized_execution_sequences,
            rejected_execution_sequences=serialized_rejected_execution_sequences,
            execution_sequence_coverage=serialized_execution_coverage,
            execution_sequence_threshold=execution_sequence_report.minimum_coverage_threshold,
        )
        classical_output = self.classical_reasoner.reason(truth_layer)
        ml_output = self.ml_reasoner.reason(truth_layer)
        quantum_output = self.quantum_reasoner.reason(truth_layer)

        serialized_research_hypotheses = [
            {
                "hypothesis_id": h.hypothesis_id,
                "title": h.title,
                "rationale": h.rationale,
                "missing_subsystem": h.missing_subsystem,
                "pattern_label": h.pattern_label,
                "expected_guarantees": h.expected_guarantees,
                "canonical_math": h.canonical_math,
                "threat_vectors": h.threat_vectors,
                "priority": h.priority,
                "evidence_needed": h.evidence_needed,
                "required_actors": h.required_actors,
                "required_assumptions": h.required_assumptions,
                "expected_attack_sequence": h.expected_attack_sequence,
                "expected_state_transition": h.expected_state_transition,
                "required_capital": h.required_capital,
                "flashloan_principal": h.flashloan_principal,
                "flashloan_fee": h.flashloan_fee,
                "predicted_attacker_profit": h.predicted_attacker_profit,
                "predicted_protocol_loss": h.predicted_protocol_loss,
                "predicted_victim_loss": h.predicted_victim_loss,
                "economic_consequence": h.economic_consequence,
            }
            for h in research_hypotheses
        ]

        hypothesis_evidence_ledger = self._build_hypothesis_evidence_ledger(
            hypotheses=serialized_research_hypotheses,
            investigation_reports=serialized_investigations,
            tutor_notes=tutor_notes,
            missing_expected_subsystems=expected_observed.missing_expected,
            planning_report=planning_report,
            classical_summary=classical_output.summary,
            ml_summary=ml_output.summary,
            quantum_summary=quantum_output.summary,
        )
        hypothesis_evidence_ledger = self._merge_execution_sequences(
            hypothesis_ledger=hypothesis_evidence_ledger,
            validated_sequences=serialized_execution_sequences,
            rejected_sequences=serialized_rejected_execution_sequences,
        )

        # Feed the full ledger so every hypothesis—not just those with valid sequences—gets a Foundry case.
        falsification_execution = self.falsification_engine.execute(
            repository_path=Path(repository_path),
            hypothesis_ledger=hypothesis_evidence_ledger,
        )
        serialized_falsification_execution = self._serialize_falsification_execution(falsification_execution)
        hypothesis_evidence_ledger = self._merge_falsification_case_statuses(
            hypothesis_ledger=hypothesis_evidence_ledger,
            execution_cases=serialized_falsification_execution.get("cases", []),
        )

        hypothesis_evidence_objects = self._build_evidence_objects(hypothesis_evidence_ledger)

        training_summary = self.training_engine.learn_from_run(
            pattern_label=pattern_result.label,
            missing_expected_subsystems=expected_observed.missing_expected,
            investigation_reports=serialized_investigations,
            tutor_notes=[self._serialize_tutor_note(note) for note in tutor_notes],
            hypothesis_evidence_ledger=hypothesis_evidence_ledger,
        )

        # Consensus only upgrades when deterministic behavioral confirmation exists.
        confirmed_cases = [
            item for item in hypothesis_evidence_objects
            if isinstance(item, dict)
            and str(item.get("verdict") or "") == "BEHAVIORALLY_CONFIRMED"
        ]
        falsified_cases = [
            item for item in hypothesis_evidence_ledger
            if isinstance(item, dict)
            and str((item.get("execution_case") or {}).get("status") or "") == "falsification_triggered"
        ]
        if falsified_cases and not confirmed_cases:
            consensus_classification = FinalClassification.FALSIFIED
        elif confirmed_cases:
            consensus_classification = FinalClassification.SURVIVES
        elif serialized_falsification_execution.get("executed") and serialized_falsification_execution.get("cases"):
            consensus_classification = FinalClassification.INCONCLUSIVE
        else:
            consensus_classification = FinalClassification.UNKNOWN
        consensus = self.consensus_engine.evaluate(
            subsystem_id=truth_layer.subsystem_id,
            hypothesis_id=f"{eir.protocol_name}-hypothesis",
            classical_classification=consensus_classification,
            ml_prior=ml_output.score,
            quantum_output=quantum_output.score,
        )

        payload = {
            "repository_context": {
                "repository_path": str(repository_context.repository_path),
                "scope_summary": repository_context.scope_summary,
                "known_issues": repository_context.known_issues,
            },
            "methodology": {
                "phase_count": methodology_report.phase_count,
                "overall_status": methodology_report.overall_status,
                "phases": [
                    {"name": phase.name, "status": phase.status.value, "summary": phase.summary}
                    for phase in methodology_report.phases
                ],
            },
            "evidence_graph": {
                "node_count": len(evidence_graph.nodes),
                "edge_count": len(evidence_graph.edges),
            },
            "protocol_pattern": {
                "pattern_id": pattern_result.pattern_id,
                "label": pattern_result.label,
                "confidence": pattern_result.confidence,
                "evidence": [
                    {"source": item.source, "detail": item.detail, "weight": item.weight}
                    for item in pattern_result.evidence
                ],
            },
            "expected_protocol_model": {
                "pattern_id": expected_model.pattern_id,
                "pattern_label": expected_model.pattern_label,
                "expected_subsystems": expected_model.expected_subsystems,
                "canonical_math": expected_model.canonical_math,
            },
            "expectation_graph": {
                "node_count": len(expectation_graph.nodes),
                "edge_count": len(expectation_graph.edges),
                "nodes": [
                    {"id": node.id, "kind": node.kind.value, "label": node.label}
                    for node in expectation_graph.nodes
                ],
                "edges": [
                    {"source": edge.source, "target": edge.target, "kind": edge.kind.value}
                    for edge in expectation_graph.edges
                ],
            },
            "expected_vs_observed": {
                "expected": expected_observed.expected,
                "observed": expected_observed.observed,
                "missing_expected": expected_observed.missing_expected,
                "unexpected_observed": expected_observed.unexpected_observed,
                "match_ratio": expected_observed.match_ratio,
                "gaps": [
                    {
                        "expected_subsystem": gap.expected_subsystem,
                        "status": gap.status,
                        "matched_observed_subsystem": gap.matched_observed_subsystem,
                    }
                    for gap in expected_observed.gaps
                ],
            },
            "protocol_reconstruction": {
                "entity_count": len(reconstruction.entities),
                "invariant_count": len(reconstruction.invariants),
                "graph_nodes": len(reconstruction.protocol_graph.nodes),
                "graph_edges": len(reconstruction.protocol_graph.edges),
            },
            "protocol_semantics": {
                "entity_count": len(semantics.entities),
                "accounting_systems": len(semantics.accounting_systems),
                "economic_variables": len(semantics.economic_variables),
                "state_transitions": len(semantics.state_transitions),
                "permissions": len(semantics.permissions),
                "trust_boundaries": len(semantics.trust_boundaries),
                "invariants": len(semantics.invariants),
                "graph_nodes": len(semantics.semantic_graph.nodes),
                "graph_edges": len(semantics.semantic_graph.edges),
            },
            "subsystem_plan": {
                "subsystems": [
                    {
                        "id": subsystem.id,
                        "name": subsystem.name,
                        "priority_score": subsystem.priority_score,
                        "economic_criticality": subsystem.economic_criticality,
                        "freshness_score": subsystem.freshness_score,
                    }
                    for subsystem in subsystem_plan.ordered_queue
                ],
                "reconstructions": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "identity": {
                            "name": item.identity.name if item.identity else item.name,
                            "architectural_responsibility": item.identity.architectural_responsibility if item.identity else "",
                            "business_objective": item.identity.business_objective if item.identity else "",
                            "protocol_objective": item.identity.protocol_objective if item.identity else "",
                        } if item.identity else None,
                        "contract_membership": {
                            "primary_contracts": item.contract_membership.primary_contracts if item.contract_membership else [],
                            "supporting_libraries": item.contract_membership.supporting_libraries if item.contract_membership else [],
                            "interfaces": item.contract_membership.interfaces if item.contract_membership else [],
                            "inherited_contracts": item.contract_membership.inherited_contracts if item.contract_membership else [],
                            "upgrade_components": item.contract_membership.upgrade_components if item.contract_membership else [],
                            "proxy_relationships": item.contract_membership.proxy_relationships if item.contract_membership else [],
                            "justifications": item.contract_membership.justifications if item.contract_membership else [],
                        } if item.contract_membership else None,
                        "state_model": {
                            "state_variables": item.state_model.state_variables if item.state_model else [],
                            "storage_ownership": item.state_model.storage_ownership if item.state_model else [],
                            "balances": item.state_model.balances if item.state_model else [],
                            "reserves": item.state_model.reserves if item.state_model else [],
                            "liabilities": item.state_model.liabilities if item.state_model else [],
                            "indexes": item.state_model.indexes if item.state_model else [],
                            "accumulated_values": item.state_model.accumulated_values if item.state_model else [],
                            "cached_values": item.state_model.cached_values if item.state_model else [],
                            "protocol_state_vars": item.state_model.protocol_state_vars if item.state_model else [],
                            "execution_state_vars": item.state_model.execution_state_vars if item.state_model else [],
                        } if item.state_model else None,
                        "state_machine_states": item.state_machine.states,
                        "state_machine_transitions": [self._serialize_transition(transition) for transition in item.state_machine.transitions],
                        "accounting_model": item.accounting_model.name if item.accounting_model else None,
                        "permission_model": {
                            "roles": item.permission_model.roles if item.permission_model else [],
                            "permission_edges": item.permission_model.permission_edges if item.permission_model else [],
                        } if item.permission_model else None,
                        "trust_model": {
                            "oracle_assumptions": item.trust_model.oracle_assumptions if item.trust_model else [],
                            "governance_assumptions": item.trust_model.governance_assumptions if item.trust_model else [],
                            "external_dependencies": item.trust_model.external_dependencies if item.trust_model else [],
                        },
                        "mathematical_model": {
                            "state_equations": item.mathematical_model.state_equations if item.mathematical_model else [],
                            "conservation_equations": item.mathematical_model.conservation_equations if item.mathematical_model else [],
                            "balance_equations": item.mathematical_model.balance_equations if item.mathematical_model else [],
                            "capacity_equations": item.mathematical_model.capacity_equations if item.mathematical_model else [],
                            "evidence": self._serialize_evidence(item.mathematical_model.evidence if item.mathematical_model else []),
                        } if item.mathematical_model else None,
                        "invariants": [
                            {
                                "unique_id": invariant.unique_id,
                                "formal_statement": invariant.formal_statement,
                                "mathematical_formulation": invariant.mathematical_formulation,
                                "economic_interpretation": invariant.economic_interpretation,
                                "confidence": invariant.confidence,
                                "protected_variables": invariant.protected_variables,
                                "evidence": self._serialize_evidence(invariant.evidence),
                            }
                            for invariant in item.invariants
                        ],
                        "evidence": self._serialize_evidence(
                            [
                                *(item.identity.evidence if item.identity else []),
                                *(item.contract_membership.evidence if item.contract_membership else []),
                                *(item.state_model.evidence if item.state_model else []),
                                *(item.accounting_model.evidence if item.accounting_model else []),
                                *(item.permission_model.evidence if item.permission_model else []),
                                *(item.mathematical_model.evidence if item.mathematical_model else []),
                                *[edge.evidence for edge in item.dependency_model.dependency_edges],
                                *[invariant.evidence for invariant in item.invariants],
                            ]
                        ),
                        "guarantees": [
                            {
                                "id": guarantee.id,
                                "name": guarantee.name,
                                "statement": guarantee.statement,
                                "rationale": guarantee.rationale,
                                "threat_model": guarantee.threat_model,
                            }
                            for guarantee in item.guarantees
                        ],
                        "implementation_traces": [
                            {
                                "equation": trace.equation,
                                "storage_variables": trace.storage_variables,
                                "functions": trace.functions,
                                "entrypoints": trace.entrypoints,
                                "internal_calls": trace.internal_calls,
                                "modifiers": trace.modifiers,
                                "constants": trace.constants,
                                "errors": trace.errors,
                                "structs": trace.structs,
                                "enums": trace.enums,
                                "interfaces": trace.interfaces,
                                "libraries": trace.libraries,
                                "events": trace.events,
                                "tests": trace.tests,
                                "call_graph": trace.call_graph,
                            }
                            for trace in item.implementation_traces
                        ],
                        "evidence_quality": item.evidence_quality,
                        "completeness_status": item.completeness_status,
                        "missing_components": item.missing_components,
                        "report": {
                            "purpose": item.report.purpose if item.report else "",
                            "contracts": item.report.contracts if item.report else [],
                            "state_machine": item.report.state_machine if item.report else [],
                            "accounting_model": item.report.accounting_model if item.report else [],
                            "trust_model": item.report.trust_model if item.report else [],
                            "permission_model": item.report.permission_model if item.report else [],
                            "economic_model": item.report.economic_model if item.report else [],
                            "mathematical_model": item.report.mathematical_model if item.report else [],
                            "extracted_invariants": item.report.extracted_invariants if item.report else [],
                            "evidence": item.report.evidence if item.report else [],
                            "confidence": item.report.confidence if item.report else item.confidence,
                            "unknowns": item.report.unknowns if item.report else [],
                            "open_questions": item.report.open_questions if item.report else [],
                        } if item.report else None,
                        "confidence": item.confidence,
                    }
                    for item in subsystem_reconstructions.subsystems
                ],
            },
            "consensus": {
                "classification": consensus.classical_classification.value,
                "research_priority": consensus.research_priority,
            },
            "semantic_dossiers": semantic_dossiers,
            "investigation_reports": serialized_investigations,
            "research_hypotheses": [
                hypothesis
                for hypothesis in serialized_research_hypotheses
            ],
            "execution_sequences": serialized_execution_sequences,
            "rejected_execution_sequences": serialized_rejected_execution_sequences,
            "execution_sequence_coverage": {
                "minimum_threshold": execution_sequence_report.minimum_coverage_threshold,
                "subsystems": serialized_execution_coverage,
            },
            "hypothesis_evidence_ledger": hypothesis_evidence_ledger,
            "hypothesis_evidence_objects": hypothesis_evidence_objects,
            "tutor_research": [self._serialize_tutor_note(note) for note in tutor_notes],
            "verification_reports": [self._serialize_verification_report(report) for report in verification_reports],
            "planning": self._serialize_planning_report(planning_report),
            "falsification_execution": serialized_falsification_execution,
            "training": {
                **training_summary,
                "lessons_used": lessons_used,
            },
            "reasoning": {
                "classical": classical_output.score,
                "ml": ml_output.score,
                "quantum": quantum_output.score,
                "classical_summary": classical_output.summary,
                "ml_summary": ml_output.summary,
                "quantum_summary": quantum_output.summary,
                "classical_artifacts": classical_output.artifacts,
                "ml_artifacts": ml_output.artifacts,
                "quantum_artifacts": quantum_output.artifacts,
            },
        }
        persistence_path = self.storage_dir / "halyx_pipeline_result.json"
        persistence = PipelinePersistence(path=persistence_path)
        persistence.write(payload)

        report_generator = AuditReportGenerator()
        report_path = report_generator.generate(payload, output_dir=self.storage_dir / "reports")

        issues: list[str] = []
        if not repository_context.markdown_files:
            issues.append("No markdown context was captured")
        if methodology_report.phase_count < 3:
            issues.append("Methodology report did not include the expected phases")

        validation_gate = IntentAwareValidationGate()
        validation = validation_gate.evaluate(
            evidence_text=(
                f"{repository_context.scope_summary} {repository_context.known_issues} {truth_layer.evidence_summary or ''}"
            ),
            invariants=[invariant.expression for invariant in eir.invariants],
            known_issues=repository_context.known_issues,
        )
        issues.extend(validation.issues)
        validation.is_valid = not issues

        return {
            "repository_context": repository_context,
            "methodology": methodology_report,
            "consensus": consensus,
            "planning": planning_report,
            "tutor_research": tutor_notes,
            "training": training_summary,
            "persistence": persistence_path,
            "report_path": report_path,
            "validation": validation,
            "research_hypotheses": serialized_research_hypotheses,
            "execution_sequences": serialized_execution_sequences,
            "rejected_execution_sequences": serialized_rejected_execution_sequences,
            "hypothesis_evidence_ledger": hypothesis_evidence_ledger,
            "hypothesis_evidence_objects": hypothesis_evidence_objects,
            "falsification_execution": serialized_falsification_execution,
            "payload": payload,
        }
