from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from quantum_economic_auditor.agents.deepseek_provider import DeepSeekProvider, LLMProvider


@dataclass(slots=True)
class TutorResearchNote:
    concept: str
    subsystem: str
    protocol_pattern: str
    summary: str
    candidate_explanations: list[str] = field(default_factory=list)
    evidence_targets: list[str] = field(default_factory=list)
    source_materials: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    verified: bool = False
    provider: str = "heuristic"
    raw_research: str = ""


class TutorEngine:
    """Research unfamiliar concepts for Halyx without asserting truth."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        enable_remote_research: bool | None = None,
    ) -> None:
        self.enable_remote_research = enable_remote_research if enable_remote_research is not None else bool(os.getenv("DEEPSEEK_API_KEY"))
        if provider is not None:
            self.provider = provider
        elif self.enable_remote_research:
            self.provider = DeepSeekProvider()
        else:
            self.provider = None

    def research(
        self,
        *,
        concept: str,
        subsystem: str,
        protocol_pattern: str,
        repository_facts: list[str],
        expected_guarantees: list[str],
        context: str | None = None,
        prior_lessons: list[str] | None = None,
    ) -> TutorResearchNote:
        prior_lessons = prior_lessons or []
        if not self.enable_remote_research:
            return self._fallback_note(
                concept=concept,
                subsystem=subsystem,
                protocol_pattern=protocol_pattern,
                repository_facts=repository_facts,
                expected_guarantees=expected_guarantees,
                context=context,
                prior_lessons=prior_lessons,
            )

        if self.provider is None:
            return self._fallback_note(
                concept=concept,
                subsystem=subsystem,
                protocol_pattern=protocol_pattern,
                repository_facts=repository_facts,
                expected_guarantees=expected_guarantees,
                context=context,
                prior_lessons=prior_lessons,
            )

        prompt = self._build_prompt(
            concept=concept,
            subsystem=subsystem,
            protocol_pattern=protocol_pattern,
            repository_facts=repository_facts,
            expected_guarantees=expected_guarantees,
            context=context,
            prior_lessons=prior_lessons,
        )
        response = self.provider.extract(prompt)
        output_text = str(response.get("output_text") or "")
        if not output_text:
            raw_response = response.get("raw_response")
            output_text = str(getattr(raw_response, "output_text", "") or raw_response or "")

        parsed = self._parse_note(output_text)
        if parsed is not None:
            parsed.provider = "deepseek"
            parsed.raw_research = output_text
            return parsed

        return TutorResearchNote(
            concept=concept,
            subsystem=subsystem,
            protocol_pattern=protocol_pattern,
            summary=output_text or self._fallback_summary(concept, subsystem, protocol_pattern),
            candidate_explanations=[f"{concept} likely describes a subsystem-specific mechanism in {protocol_pattern}"],
            evidence_targets=[f"source code for {subsystem}", "documentation", "prior audit commentary"],
            source_materials=repository_facts[:5],
            assumptions=[f"{concept} is currently unverified"],
            open_questions=[f"Which source artifacts concretely define {concept}?"],
            confidence=0.35,
            verified=False,
            provider="deepseek",
            raw_research=output_text,
        )

    def _build_prompt(
        self,
        *,
        concept: str,
        subsystem: str,
        protocol_pattern: str,
        repository_facts: list[str],
        expected_guarantees: list[str],
        context: str | None,
        prior_lessons: list[str],
    ) -> str:
        return (
            "You are Halyx Tutor. Produce unverified research only. Do not claim truth. "
            "Return JSON with keys: summary, candidate_explanations, evidence_targets, source_materials, assumptions, open_questions, confidence. "
            f"Concept: {concept}. Subsystem: {subsystem}. Protocol pattern: {protocol_pattern}. "
            f"Repository facts: {repository_facts}. Expected guarantees: {expected_guarantees}. Context: {context or 'n/a'}. "
            f"Prior training lessons: {prior_lessons[:6]}. "
            "Focus on how an auditor should understand the concept, not on final verification."
        )

    def _parse_note(self, output_text: str) -> TutorResearchNote | None:
        stripped = output_text.strip()
        if not stripped:
            return None
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        concept = str(payload.get("concept") or payload.get("summary") or "unknown concept")
        return TutorResearchNote(
            concept=concept,
            subsystem=str(payload.get("subsystem") or "unknown"),
            protocol_pattern=str(payload.get("protocol_pattern") or "unknown"),
            summary=str(payload.get("summary") or ""),
            candidate_explanations=[str(item) for item in payload.get("candidate_explanations", []) if item],
            evidence_targets=[str(item) for item in payload.get("evidence_targets", []) if item],
            source_materials=[str(item) for item in payload.get("source_materials", []) if item],
            assumptions=[str(item) for item in payload.get("assumptions", []) if item],
            open_questions=[str(item) for item in payload.get("open_questions", []) if item],
            confidence=float(payload.get("confidence", 0.35)),
            verified=False,
            provider="deepseek",
            raw_research=output_text,
        )

    @staticmethod
    def _fallback_summary(concept: str, subsystem: str, protocol_pattern: str) -> str:
        return f"Research gap identified for {concept} in {subsystem} under {protocol_pattern}; verification required before acceptance."

    def _fallback_note(
        self,
        *,
        concept: str,
        subsystem: str,
        protocol_pattern: str,
        repository_facts: list[str],
        expected_guarantees: list[str],
        context: str | None,
        prior_lessons: list[str],
    ) -> TutorResearchNote:
        return TutorResearchNote(
            concept=concept,
            subsystem=subsystem,
            protocol_pattern=protocol_pattern,
            summary=self._fallback_summary(concept, subsystem, protocol_pattern),
            candidate_explanations=[f"{concept} could map to a missing guarantee in {subsystem}"],
            evidence_targets=expected_guarantees[:3] or [f"{subsystem} source code", "documentation", "historical audits"],
            source_materials=repository_facts[:5] + prior_lessons[:3] + ([context] if context else []),
            assumptions=[f"{concept} has not yet been verified by source evidence"],
            open_questions=[f"What repository artifacts define {concept}?"],
            confidence=0.25,
            verified=False,
            provider="heuristic",
        )