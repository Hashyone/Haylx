from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(slots=True)
class ReasoningLesson:
    lesson_id: str
    timestamp: str
    pattern_label: str
    subsystem: str
    lesson_type: str
    insight: str
    evidence: list[str]
    confidence_delta: float
    tags: list[str]


class ReasoningTrainingEngine:
    """Persist and retrieve reusable reasoning lessons across protocol runs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def retrieve_lessons(
        self,
        *,
        pattern_label: str,
        subsystem: str | None = None,
        concept: str | None = None,
        top_k: int = 5,
    ) -> list[ReasoningLesson]:
        lessons = self._load_lessons()
        target_tokens = set(self._tokenize(" ".join([pattern_label, subsystem or "", concept or ""])))
        ranked = sorted(
            lessons,
            key=lambda lesson: self._score_lesson(lesson, pattern_label=pattern_label, target_tokens=target_tokens),
            reverse=True,
        )
        return ranked[:top_k]

    def learn_from_run(
        self,
        *,
        pattern_label: str,
        missing_expected_subsystems: list[str],
        investigation_reports: list[dict[str, object]],
        tutor_notes: list[dict[str, object]],
        hypothesis_evidence_ledger: list[dict[str, object]],
    ) -> dict[str, object]:
        lessons = self._load_lessons()
        existing_ids = {lesson.lesson_id for lesson in lessons}
        generated: list[ReasoningLesson] = []
        now = datetime.now(UTC).isoformat()

        for subsystem in missing_expected_subsystems:
            insight = f"{subsystem} repeatedly appears as a missing expected subsystem; prioritize deterministic extraction paths first."
            generated.append(
                self._build_lesson(
                    timestamp=now,
                    pattern_label=pattern_label,
                    subsystem=subsystem,
                    lesson_type="gap_recurrence",
                    insight=insight,
                    evidence=["expected_vs_observed.missing_expected"],
                    confidence_delta=-0.10,
                    tags=["gap", "coverage", "priority"],
                )
            )

        for report in investigation_reports:
            if not isinstance(report, dict):
                continue
            subsystem = str(report.get("subsystem") or "unknown")
            risk_signal = str(report.get("overall_risk_signal") or "unknown")
            adversarial_count = len(report.get("adversarial_hypotheses", []))
            generated.append(
                self._build_lesson(
                    timestamp=now,
                    pattern_label=pattern_label,
                    subsystem=subsystem,
                    lesson_type="adversarial_signal",
                    insight=(
                        f"Investigator reports risk signal '{risk_signal}' with {adversarial_count} adversarial hypotheses; "
                        "convert strongest hypotheses into executable falsification tests."
                    ),
                    evidence=["investigation_reports.overall_risk_signal", "investigation_reports.adversarial_hypotheses"],
                    confidence_delta=-0.05,
                    tags=["adversarial", "falsification"],
                )
            )

        for note in tutor_notes:
            if not isinstance(note, dict):
                continue
            concept = str(note.get("concept") or note.get("subsystem") or "unknown concept")
            verified = bool(note.get("verified"))
            generated.append(
                self._build_lesson(
                    timestamp=now,
                    pattern_label=pattern_label,
                    subsystem=str(note.get("subsystem") or concept),
                    lesson_type="tutor_research",
                    insight=(
                        f"Tutor guidance for {concept} was verified; promote this as a reusable reasoning pattern."
                        if verified
                        else f"Tutor guidance for {concept} remains unverified; require source-level checks before promoting confidence."
                    ),
                    evidence=["tutor_research.summary", "tutor_research.evidence_targets"],
                    confidence_delta=0.08 if verified else 0.03,
                    tags=["tutor", "verification"],
                )
            )

        for item in hypothesis_evidence_ledger:
            if not isinstance(item, dict):
                continue
            subsystem = str(item.get("subsystem") or "unknown")
            final_confidence = float(item.get("final_confidence", 0.0))
            status = str(item.get("status") or "unknown")
            generated.append(
                self._build_lesson(
                    timestamp=now,
                    pattern_label=pattern_label,
                    subsystem=subsystem,
                    lesson_type="hypothesis_outcome",
                    insight=(
                        f"Hypothesis status for {subsystem}: {status} at confidence {final_confidence:.2f}; "
                        "use confidence trajectory to prioritize the next proof/disprove experiment."
                    ),
                    evidence=["hypothesis_evidence_ledger.status", "hypothesis_evidence_ledger.confidence_trajectory"],
                    confidence_delta=final_confidence - 0.35,
                    tags=["hypothesis", "trajectory"],
                )
            )

        deduped: list[ReasoningLesson] = []
        for lesson in generated:
            if lesson.lesson_id in existing_ids:
                continue
            existing_ids.add(lesson.lesson_id)
            deduped.append(lesson)

        if deduped:
            with self.path.open("a", encoding="utf-8") as handle:
                for lesson in deduped:
                    handle.write(json.dumps(asdict(lesson), sort_keys=True) + "\n")

        return {
            "lessons_generated": len(generated),
            "lessons_persisted": len(deduped),
            "knowledge_base_path": str(self.path),
        }

    def _build_lesson(
        self,
        *,
        timestamp: str,
        pattern_label: str,
        subsystem: str,
        lesson_type: str,
        insight: str,
        evidence: list[str],
        confidence_delta: float,
        tags: list[str],
    ) -> ReasoningLesson:
        fingerprint = "|".join([pattern_label.strip().lower(), subsystem.strip().lower(), lesson_type.strip().lower(), insight.strip().lower()])
        lesson_id = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]
        return ReasoningLesson(
            lesson_id=lesson_id,
            timestamp=timestamp,
            pattern_label=pattern_label,
            subsystem=subsystem,
            lesson_type=lesson_type,
            insight=insight,
            evidence=evidence,
            confidence_delta=round(confidence_delta, 3),
            tags=tags,
        )

    def _load_lessons(self) -> list[ReasoningLesson]:
        if not self.path.exists():
            return []
        lessons: list[ReasoningLesson] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            try:
                lessons.append(
                    ReasoningLesson(
                        lesson_id=str(payload.get("lesson_id") or ""),
                        timestamp=str(payload.get("timestamp") or ""),
                        pattern_label=str(payload.get("pattern_label") or "unknown"),
                        subsystem=str(payload.get("subsystem") or "unknown"),
                        lesson_type=str(payload.get("lesson_type") or "unknown"),
                        insight=str(payload.get("insight") or ""),
                        evidence=[str(item) for item in payload.get("evidence", []) if item],
                        confidence_delta=float(payload.get("confidence_delta", 0.0)),
                        tags=[str(item) for item in payload.get("tags", []) if item],
                    )
                )
            except (TypeError, ValueError):
                continue
        return lessons

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
        return [token for token in cleaned.split() if token]

    def _score_lesson(self, lesson: ReasoningLesson, *, pattern_label: str, target_tokens: set[str]) -> float:
        score = 0.0
        if lesson.pattern_label.lower() == pattern_label.lower():
            score += 2.0
        lesson_tokens = set(self._tokenize(" ".join([lesson.subsystem, lesson.insight, " ".join(lesson.tags)])))
        overlap = len(target_tokens & lesson_tokens)
        score += overlap
        score += max(-1.0, min(1.0, lesson.confidence_delta))
        return score