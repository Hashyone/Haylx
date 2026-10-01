from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.semantic.reasoning_trainer import ReasoningTrainingEngine
from quantum_economic_auditor.semantic.tutor_engine import TutorEngine


class CapturingProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def extract(self, prompt: str) -> dict[str, object]:
        self.prompts.append(prompt)
        return {
            "output_text": "",
            "raw_response": prompt,
        }


def test_reasoning_training_engine_persists_and_retrieves_lessons(tmp_path: Path) -> None:
    engine = ReasoningTrainingEngine(tmp_path / "training.jsonl")

    summary = engine.learn_from_run(
        pattern_label="AMM",
        missing_expected_subsystems=["Fee Distribution"],
        investigation_reports=[
            {
                "subsystem": "Fee Distribution",
                "overall_risk_signal": "high",
                "adversarial_hypotheses": [{"id": "a1"}],
            }
        ],
        tutor_notes=[
            {
                "concept": "Fee Distribution",
                "subsystem": "Fee Distribution",
                "verified": False,
                "summary": "pending",
                "evidence_targets": ["fee accumulator"],
            }
        ],
        hypothesis_evidence_ledger=[
            {
                "hypothesis_id": "hyp:fee",
                "subsystem": "Fee Distribution",
                "status": "pending_verification",
                "final_confidence": 0.4,
                "confidence_trajectory": [{"stage": "surfaced"}],
            }
        ],
    )

    assert summary["lessons_persisted"] > 0
    assert Path(summary["knowledge_base_path"]).exists()

    retrieved = engine.retrieve_lessons(pattern_label="AMM", subsystem="Fee Distribution", concept="Fee Distribution", top_k=3)
    assert retrieved
    assert any("Fee Distribution" in lesson.subsystem for lesson in retrieved)


def test_tutor_prompt_includes_prior_lessons() -> None:
    provider = CapturingProvider()
    engine = TutorEngine(provider=provider, enable_remote_research=True)

    engine.research(
        concept="Oracle Dependencies",
        subsystem="Oracle Dependencies",
        protocol_pattern="Lending Protocol",
        repository_facts=["source_root=src"],
        expected_guarantees=["oracle freshness bounded"],
        context="gap",
        prior_lessons=["Use deterministic source checks before accepting oracle assumptions."],
    )

    assert provider.prompts
    assert "Prior training lessons" in provider.prompts[0]
    assert "deterministic source checks" in provider.prompts[0]