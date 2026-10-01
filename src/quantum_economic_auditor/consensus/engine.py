from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FinalClassification(str, Enum):
    SURVIVES = "survives"           # only when deterministic behavioral confirmation exists
    FALSIFIED = "falsified"         # only when falsification_triggered
    UNKNOWN = "unknown"             # reconstruction only, no behavioral evidence
    INCONCLUSIVE = "inconclusive"   # execution ran but produced no deterministic outcome


@dataclass
class ConsensusResult:
    subsystem_id: str
    hypothesis_id: str
    classical_classification: FinalClassification
    agreement_level: str
    research_priority: float
    confidence: float


class ConsensusEngine:
    """Synthesize Classical truth, ML experience, and Quantum possibility into a consensus decision."""

    def evaluate(
        self,
        *,
        subsystem_id: str,
        hypothesis_id: str,
        classical_classification: FinalClassification,
        ml_prior: float,
        quantum_output: float | None = None,
    ) -> ConsensusResult:
        effective_quantum = quantum_output if quantum_output is not None else ml_prior
        experience_signal = ml_prior
        possibility_signal = effective_quantum
        signal_gap = abs(experience_signal - possibility_signal)

        if possibility_signal >= experience_signal + 0.35:
            agreement_level = "disagreement"
        elif signal_gap >= 0.2:
            agreement_level = "partial_agreement"
        else:
            agreement_level = "strong_agreement"

        truth_anchor = (
            0.85 if classical_classification == FinalClassification.SURVIVES
            else 0.15 if classical_classification == FinalClassification.FALSIFIED
            else 0.5
        )
        research_priority = max(
            0.0,
            min(
                1.0,
                0.45 * possibility_signal
                + 0.25 * experience_signal
                + 0.20 * (1.0 - truth_anchor)
                + 0.10 * signal_gap,
            ),
        )
        confidence = max(
            0.0,
            min(
                1.0,
                0.55 * truth_anchor + 0.25 * experience_signal + 0.20 * (1.0 - signal_gap),
            ),
        )

        return ConsensusResult(
            subsystem_id=subsystem_id,
            hypothesis_id=hypothesis_id,
            classical_classification=classical_classification,
            agreement_level=agreement_level,
            research_priority=research_priority,
            confidence=confidence,
        )
