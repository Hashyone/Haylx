from __future__ import annotations

import json

from quantum_economic_auditor.semantic.planning_engine import PlanningEngine
from quantum_economic_auditor.semantic.tutor_engine import TutorEngine


class FakeTutorProvider:
    def extract(self, prompt: str) -> dict[str, object]:
        return {
            "output_text": json.dumps(
                {
                    "concept": "Fee Distribution",
                    "subsystem": "Fee Distribution",
                    "protocol_pattern": "AMM",
                    "summary": "Fee distribution appears to be a post-swap accrual and claim path.",
                    "candidate_explanations": ["fees accrue per trade", "LPs and protocol split revenues"],
                    "evidence_targets": ["fee accumulator", "claim function"],
                    "source_materials": ["documentation", "audit report"],
                    "assumptions": ["unverified until matched to source code"],
                    "open_questions": ["Which functions mint or claim fees?"],
                    "confidence": 0.64,
                }
            ),
            "raw_response": prompt,
        }


def test_tutor_engine_parses_remote_research_into_note() -> None:
    engine = TutorEngine(provider=FakeTutorProvider(), enable_remote_research=True)
    note = engine.research(
        concept="Fee Distribution",
        subsystem="Fee Distribution",
        protocol_pattern="AMM",
        repository_facts=["source_root=src", "contract_files=12"],
        expected_guarantees=["fee collection remains conserved"],
        context="AMM subsystem gap",
    )

    assert note.provider == "deepseek"
    assert note.concept == "Fee Distribution"
    assert note.candidate_explanations
    assert note.evidence_targets
    assert note.confidence == 0.64


def test_planning_engine_prefers_tutor_when_expected_subsystems_are_missing() -> None:
    report = PlanningEngine().plan(
        pattern_label="AMM",
        expectation_match_ratio=0.57,
        missing_expected_subsystems=["Fee Distribution", "LP Economics", "Oracle Dependencies"],
        investigation_reports=[
            {
                "subsystem": "Liquidity Accounting",
                "adversarial_hypotheses": [{"attack_vector": "reentrancy during liquidity removal"}],
            }
        ],
        tutor_notes=[],
        historical_learning_signals=["pattern=AMM"],
    )

    assert report.next_action.action == "invoke_tutor"
    assert report.should_invoke_tutor is True
    assert report.uncertainty_score > 0.0
    assert report.candidate_actions