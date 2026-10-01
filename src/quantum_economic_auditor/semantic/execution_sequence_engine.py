from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from quantum_economic_auditor.models.eir import EconomicIntermediateRepresentation
from quantum_economic_auditor.models.execution_sequence import (
    ExecutionCoverage,
    ExecutionSequence,
    ExecutionSequenceReport,
    ExecutionStep,
    RejectedExecutionSequence,
    SequenceValidation,
)


@dataclass(slots=True)
class _TransitionCandidate:
    from_state: str | None
    to_state: str | None
    handler: str
    permissions: list[str]
    modified_storage: list[str]
    events: list[str]
    invariants: list[str]
    equations: list[str]


class ExecutionSequenceReconstructionEngine:
    """Reconstruct deterministic execution paths from subsystem state machines."""

    def __init__(self, *, minimum_coverage_threshold: float = 0.35) -> None:
        self.minimum_coverage_threshold = minimum_coverage_threshold

    def reconstruct(
        self,
        *,
        protocol_name: str,
        eir: EconomicIntermediateRepresentation,
        subsystem_reconstructions: list[object],
        investigation_reports: list[object],
    ) -> ExecutionSequenceReport:
        subsystem_by_name = {
            str(getattr(subsystem, "name", "") or "").lower(): subsystem
            for subsystem in subsystem_reconstructions
        }
        coverage_by_subsystem = [self._build_coverage(subsystem) for subsystem in subsystem_reconstructions]
        coverage_lookup = {coverage.subsystem.lower(): coverage for coverage in coverage_by_subsystem}

        validated_sequences: list[ExecutionSequence] = []
        rejected_sequences: list[RejectedExecutionSequence] = []
        for report in investigation_reports:
            subsystem_name = str(getattr(report, "subsystem", "") or "")
            subsystem = subsystem_by_name.get(subsystem_name.lower())
            coverage = coverage_lookup.get(subsystem_name.lower(), ExecutionCoverage(subsystem=subsystem_name))
            adversarial_hypotheses = list(getattr(report, "adversarial_hypotheses", []) or [])
            for hypothesis in adversarial_hypotheses:
                sequence_id = f"seq:{self._sanitize(getattr(hypothesis, 'hypothesis_id', 'unknown'))}"
                if subsystem is None:
                    rejected_sequences.append(
                        RejectedExecutionSequence(
                            sequence_id=sequence_id,
                            hypothesis_id=str(getattr(hypothesis, "hypothesis_id", "unknown")),
                            subsystem=subsystem_name or "unknown",
                            reasons=["No subsystem reconstruction matched the hypothesis subsystem."],
                            coverage=coverage,
                        )
                    )
                    continue
                if not coverage.meets_threshold:
                    rejected_sequences.append(
                        RejectedExecutionSequence(
                            sequence_id=sequence_id,
                            hypothesis_id=str(getattr(hypothesis, "hypothesis_id", "unknown")),
                            subsystem=subsystem_name,
                            reasons=[
                                (
                                    "Execution coverage below threshold: "
                                    f"{coverage.coverage_ratio:.2f} < {self.minimum_coverage_threshold:.2f}."
                                )
                            ],
                            coverage=coverage,
                        )
                    )
                    continue

                sequence = self._build_sequence(
                    protocol_name=protocol_name,
                    eir=eir,
                    subsystem=subsystem,
                    coverage=coverage,
                    hypothesis=hypothesis,
                )
                if sequence.validation.is_valid:
                    validated_sequences.append(sequence)
                else:
                    rejected_sequences.append(
                        RejectedExecutionSequence(
                            sequence_id=sequence.sequence_id,
                            hypothesis_id=sequence.hypothesis_id,
                            subsystem=sequence.subsystem,
                            reasons=sequence.validation.reasons,
                            coverage=sequence.coverage,
                        )
                    )

        return ExecutionSequenceReport(
            validated_sequences=validated_sequences,
            rejected_sequences=rejected_sequences,
            coverage_by_subsystem=coverage_by_subsystem,
            minimum_coverage_threshold=self.minimum_coverage_threshold,
        )

    def _build_coverage(self, subsystem: object) -> ExecutionCoverage:
        transitions = list(getattr(getattr(subsystem, "state_machine", None), "transitions", []) or [])
        state_machine = getattr(subsystem, "state_machine", None)
        state_model = getattr(subsystem, "state_model", None)
        permission_model = getattr(subsystem, "permission_model", None)
        trust_model = getattr(subsystem, "trust_model", None)
        accounting_model = getattr(subsystem, "accounting_model", None)
        contract_membership = getattr(subsystem, "contract_membership", None)
        implementation_traces = list(getattr(subsystem, "implementation_traces", []) or [])

        handlers = {
            str(getattr(transition, "triggering_function", "") or "")
            for transition in transitions
            if getattr(transition, "triggering_function", None)
        }
        handlers.update(
            function
            for trace in implementation_traces
            for function in list(getattr(trace, "functions", []) or [])
            if function
        )

        state_variables = set(getattr(state_machine, "state_variables", []) or [])
        if state_model is not None:
            for field_name in (
                "state_variables",
                "balances",
                "reserves",
                "liabilities",
                "indexes",
                "accumulated_values",
                "cached_values",
                "protocol_state_vars",
                "execution_state_vars",
            ):
                state_variables.update(list(getattr(state_model, field_name, []) or []))
        state_variables.update(
            variable
            for trace in implementation_traces
            for variable in list(getattr(trace, "storage_variables", []) or [])
            if variable
        )

        permissions_count = len(set(
            list(getattr(permission_model, "roles", []) or [])
            + list(getattr(permission_model, "capabilities", []) or [])
            + [str(edge.get("capability") or edge.get("target") or "") for edge in list(getattr(permission_model, "permission_edges", []) or []) if isinstance(edge, dict)]
        ))
        trust_boundaries_count = len(set(
            list(getattr(trust_model, "external_dependencies", []) or [])
            + list(getattr(trust_model, "oracle_assumptions", []) or [])
            + list(getattr(trust_model, "governance_assumptions", []) or [])
            + list(getattr(trust_model, "timing_assumptions", []) or [])
        ))
        external_integrations_count = len(set(
            list(getattr(contract_membership, "interfaces", []) or [])
            + list(getattr(contract_membership, "supporting_libraries", []) or [])
            + list(getattr(trust_model, "external_dependencies", []) or [])
        ))
        accounting_paths_count = len(set(
            list(getattr(accounting_model, "update_equations", []) or [])
            + list(getattr(accounting_model, "conservation_laws", []) or [])
            + list(getattr(accounting_model, "failure_conditions", []) or [])
        ))
        reachable_transitions = len(transitions)

        ratio = round(
            (
                min(1.0, len(handlers) / 3.0)
                + min(1.0, len(state_variables) / 6.0)
                + min(1.0, permissions_count / 2.0)
                + min(1.0, trust_boundaries_count / 2.0)
                + min(1.0, external_integrations_count / 2.0)
                + min(1.0, accounting_paths_count / 2.0)
                + min(1.0, reachable_transitions / 3.0)
            )
            / 7.0,
            3,
        )
        return ExecutionCoverage(
            subsystem=str(getattr(subsystem, "name", "") or "unknown"),
            handlers_reconstructed=len(handlers),
            state_variables_modeled=len(state_variables),
            permissions_modeled=permissions_count,
            trust_boundaries_modeled=trust_boundaries_count,
            external_integrations_modeled=external_integrations_count,
            accounting_paths_modeled=accounting_paths_count,
            reachable_transitions=reachable_transitions,
            coverage_ratio=ratio,
            meets_threshold=ratio >= self.minimum_coverage_threshold,
        )

    def _build_sequence(
        self,
        *,
        protocol_name: str,
        eir: EconomicIntermediateRepresentation,
        subsystem: object,
        coverage: ExecutionCoverage,
        hypothesis: object,
    ) -> ExecutionSequence:
        transitions = [self._transition_candidate(item) for item in list(getattr(getattr(subsystem, "state_machine", None), "transitions", []) or [])]
        state_machine = getattr(subsystem, "state_machine", None)
        sequence_id = f"seq:{self._sanitize(getattr(hypothesis, 'hypothesis_id', 'unknown'))}"
        step_texts = [str(step) for step in list(getattr(hypothesis, "execution_steps", []) or [])]
        invariants = [str(getattr(hypothesis, "violated_invariant", "") or "")] if getattr(hypothesis, "violated_invariant", None) else []
        state_variables = self._known_state_variables(subsystem)
        permissions = set(getattr(getattr(subsystem, "permission_model", None), "roles", []) or [])
        trust_boundaries = self._trust_boundaries(subsystem)
        constraint_ids = self._constraint_ids(subsystem, eir)

        steps: list[ExecutionStep] = []
        reasons: list[str] = []
        current_state: str | None = None
        for index, step_text in enumerate(step_texts, start=1):
            transition = self._match_transition(step_text=step_text, transitions=transitions, current_state=current_state)
            if transition is None:
                reasons.append(f"No legal state-machine transition matched step {index}: {step_text}.")
                continue
            caller = "privileged_actor" if getattr(hypothesis, "requires_privilege", False) and transition.permissions else "external_user"
            writes = [item for item in transition.modified_storage if item in state_variables]
            if self._step_requires_state_update(step_text) and not writes:
                reasons.append(f"Step {index} implies state mutation but no modeled writes were found: {step_text}.")
            steps.append(
                ExecutionStep(
                    index=index,
                    description=step_text,
                    handler=transition.handler,
                    caller=caller,
                    preconditions=[
                        f"state == {transition.from_state}" if transition.from_state else "reachable entry state",
                        *([f"permission: {item}" for item in transition.permissions] if transition.permissions else []),
                    ],
                    postconditions=[
                        f"state == {transition.to_state}" if transition.to_state else "state advanced",
                        *([f"writes: {', '.join(writes)}"] if writes else []),
                    ],
                    state_reads=[item for item in transition.modified_storage[:3] if item in state_variables],
                    state_writes=writes,
                    emitted_events=transition.events,
                    trust_boundary=trust_boundaries[0] if trust_boundaries else None,
                    permissions_required=transition.permissions,
                    constraint_ids=constraint_ids,
                    invariant_ids=invariants or transition.invariants,
                    from_state=transition.from_state,
                    to_state=transition.to_state,
                )
            )
            current_state = transition.to_state

        validation = self._validate_sequence(
            subsystem=subsystem,
            hypothesis=hypothesis,
            steps=steps,
            state_variables=state_variables,
            permissions=permissions,
            reasons=reasons,
        )
        confidence = self._execution_confidence(coverage=coverage, validation=validation)
        return ExecutionSequence(
            sequence_id=sequence_id,
            hypothesis_id=str(getattr(hypothesis, "hypothesis_id", "unknown")),
            protocol=protocol_name,
            subsystem=str(getattr(subsystem, "name", "unknown")),
            ordered_steps=steps,
            initial_state=steps[0].from_state if steps else None,
            resulting_protocol_state=steps[-1].to_state if steps else None,
            economic_consequence=str(getattr(hypothesis, "economic_impact", "") or ""),
            violated_invariants=invariants,
            violated_assumptions=self._violated_assumptions(subsystem, hypothesis),
            reasoning_trace=[
                f"protocol={protocol_name}",
                f"subsystem={getattr(subsystem, 'name', 'unknown')}",
                f"coverage_ratio={coverage.coverage_ratio:.2f}",
                f"step_count={len(steps)}",
            ],
            coverage=coverage,
            validation=validation,
            execution_confidence=confidence,
        )

    def _validate_sequence(
        self,
        *,
        subsystem: object,
        hypothesis: object,
        steps: list[ExecutionStep],
        state_variables: set[str],
        permissions: set[str],
        reasons: list[str],
    ) -> SequenceValidation:
        validation_reasons = reasons[:]
        state_machine = getattr(subsystem, "state_machine", None)
        known_states = set(list(getattr(state_machine, "states", []) or []))
        if not steps:
            validation_reasons.append("Hypothesis could not be reconstructed into any executable steps.")

        valid_transition_count = 0
        expected_state = steps[0].from_state if steps else None
        for step in steps:
            if not step.handler:
                validation_reasons.append(f"Step {step.index} is missing a handler.")
            if any(item not in state_variables for item in [*step.state_reads, *step.state_writes]):
                validation_reasons.append(f"Step {step.index} references unknown state variables.")
            if step.from_state and step.from_state not in known_states:
                validation_reasons.append(f"Step {step.index} starts from unknown state '{step.from_state}'.")
            if step.to_state and step.to_state not in known_states:
                validation_reasons.append(f"Step {step.index} transitions to unknown state '{step.to_state}'.")
            if expected_state is not None and step.from_state != expected_state:
                validation_reasons.append(
                    f"Step {step.index} is unreachable: expected from_state '{expected_state}', got '{step.from_state}'."
                )
            else:
                valid_transition_count += 1
            expected_state = step.to_state
            if step.permissions_required and step.caller == "external_user" and getattr(hypothesis, "requires_privilege", False):
                validation_reasons.append(f"Step {step.index} requires privileged permissions but caller is external_user.")
            if any(permission not in permissions for permission in step.permissions_required):
                validation_reasons.append(f"Step {step.index} requires permissions not present in the modeled permission set.")

        simulator_success = not validation_reasons and bool(steps)
        completeness_ratio = round(valid_transition_count / max(1, len(steps)), 3)
        transition_validity_ratio = round(valid_transition_count / max(1, len(steps)), 3)
        return SequenceValidation(
            is_valid=not validation_reasons and simulator_success,
            reasons=validation_reasons,
            simulator_success=simulator_success,
            completeness_ratio=completeness_ratio,
            transition_validity_ratio=transition_validity_ratio,
        )

    def _execution_confidence(self, *, coverage: ExecutionCoverage, validation: SequenceValidation) -> float:
        score = (
            coverage.coverage_ratio * 0.3
            + validation.completeness_ratio * 0.25
            + validation.transition_validity_ratio * 0.25
            + (1.0 if validation.simulator_success else 0.0) * 0.2
        )
        return round(min(0.99, max(0.0, score)), 3)

    def _known_state_variables(self, subsystem: object) -> set[str]:
        state_machine = getattr(subsystem, "state_machine", None)
        state_model = getattr(subsystem, "state_model", None)
        implementation_traces = list(getattr(subsystem, "implementation_traces", []) or [])
        values = set(list(getattr(state_machine, "state_variables", []) or []))
        if state_model is not None:
            for field_name in (
                "state_variables",
                "balances",
                "reserves",
                "liabilities",
                "indexes",
                "accumulated_values",
                "cached_values",
                "protocol_state_vars",
                "execution_state_vars",
            ):
                values.update(list(getattr(state_model, field_name, []) or []))
        for trace in implementation_traces:
            values.update(list(getattr(trace, "storage_variables", []) or []))
        return {str(item) for item in values if item}

    def _trust_boundaries(self, subsystem: object) -> list[str]:
        trust_model = getattr(subsystem, "trust_model", None)
        if trust_model is None:
            return []
        values = (
            list(getattr(trust_model, "external_dependencies", []) or [])
            + list(getattr(trust_model, "oracle_assumptions", []) or [])
            + list(getattr(trust_model, "governance_assumptions", []) or [])
            + list(getattr(trust_model, "timing_assumptions", []) or [])
        )
        return [str(item) for item in values if item]

    def _constraint_ids(self, subsystem: object, eir: EconomicIntermediateRepresentation) -> list[str]:
        mathematical_spec = getattr(subsystem, "mathematical_specification", None)
        constraints = list(getattr(mathematical_spec, "economic_constraints", []) or [])
        constraints.extend(list(getattr(mathematical_spec, "safety_bounds", []) or []))
        if not constraints:
            constraints.extend(invariant.name for invariant in eir.invariants[:3])
        return [self._sanitize(constraint) for constraint in constraints[:4] if constraint]

    def _violated_assumptions(self, subsystem: object, hypothesis: object) -> list[str]:
        trust_boundaries = self._trust_boundaries(subsystem)
        attack_text = " ".join(
            [
                str(getattr(hypothesis, "attack_vector", "") or ""),
                str(getattr(hypothesis, "attack_description", "") or ""),
                *[str(step) for step in list(getattr(hypothesis, "execution_steps", []) or [])],
            ]
        ).lower()
        return [item for item in trust_boundaries if any(token in attack_text for token in self._tokenize(item))][:4]

    def _match_transition(
        self,
        *,
        step_text: str,
        transitions: list[_TransitionCandidate],
        current_state: str | None,
    ) -> _TransitionCandidate | None:
        step_tokens = set(self._expand_action_aliases(self._tokenize(step_text)))
        ranked: list[tuple[int, _TransitionCandidate]] = []
        for transition in transitions:
            if current_state is not None and transition.from_state not in {None, current_state}:
                continue
            haystack = " ".join(
                [
                    transition.handler,
                    *(transition.modified_storage or []),
                    *(transition.events or []),
                    *(transition.invariants or []),
                    *(transition.equations or []),
                    transition.from_state or "",
                    transition.to_state or "",
                ]
            ).lower()
            transition_tokens = set(self._expand_action_aliases(self._tokenize(haystack)))
            score = len(step_tokens & transition_tokens)
            if transition.handler and transition.handler.lower() in step_text.lower():
                score += 3
            if current_state is None and transition.from_state:
                score += 1
            ranked.append((score, transition))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if ranked and ranked[0][0] > 0:
            return ranked[0][1]
        if current_state is None and transitions:
            return transitions[0]
        return None

    def _transition_candidate(self, transition: object) -> _TransitionCandidate:
        return _TransitionCandidate(
            from_state=getattr(transition, "from_state", None),
            to_state=getattr(transition, "to_state", None),
            handler=str(getattr(transition, "triggering_function", "") or ""),
            permissions=list(getattr(transition, "required_permissions", []) or []),
            modified_storage=list(getattr(transition, "modified_storage", []) or []),
            events=list(getattr(transition, "generated_events", []) or []),
            invariants=list(getattr(transition, "affected_invariants", []) or []),
            equations=list(getattr(transition, "equations", []) or []),
        )

    @staticmethod
    def _step_requires_state_update(step_text: str) -> bool:
        lowered = step_text.lower()
        return any(token in lowered for token in ("deposit", "mint", "burn", "borrow", "redeem", "withdraw", "update", "sync", "swap"))

    @staticmethod
    def _sanitize(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower() or "unknown"

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        return [token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", value.lower()) if token]

    @staticmethod
    def _expand_action_aliases(tokens: list[str]) -> list[str]:
        aliases: dict[str, tuple[str, ...]] = {
            "deposit": ("deposit", "deposits", "deposited"),
            "redeem": ("redeem", "redeems", "redeemed", "redemption"),
            "borrow": ("borrow", "borrows", "borrowed", "borrowing"),
            "withdraw": ("withdraw", "withdrawal", "withdraws", "withdrawing"),
            "mint": ("mint", "mints", "minted", "minting"),
            "burn": ("burn", "burns", "burned", "burning"),
            "swap": ("swap", "swaps", "swapped", "swapping"),
            "sync": ("sync", "synchronization", "synchronize", "synchronized"),
        }
        expanded = set(tokens)
        for token in tokens:
            for canonical, variants in aliases.items():
                if token == canonical or token in variants or token.startswith(canonical):
                    expanded.add(canonical)
                    expanded.update(variants)
        return list(expanded)
