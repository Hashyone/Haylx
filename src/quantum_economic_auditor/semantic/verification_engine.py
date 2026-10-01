from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from quantum_economic_auditor.parser.repository_loader import RepositoryModel
from quantum_economic_auditor.semantic.tutor_engine import TutorResearchNote


@dataclass(slots=True)
class VerificationMatch:
    file: str
    matched_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationReport:
    concept: str
    subsystem: str
    verified: bool
    verification_score: float
    rationale: str
    matched_files: list[VerificationMatch] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)


class DeterministicVerificationEngine:
    """Deterministically validate tutor notes against repository source code evidence."""

    def verify_tutor_note(
        self,
        *,
        note: TutorResearchNote,
        repository_model: RepositoryModel,
        expected_guarantees: list[str],
    ) -> VerificationReport:
        terms = self._build_terms(note=note, expected_guarantees=expected_guarantees)
        if not terms:
            return VerificationReport(
                concept=note.concept,
                subsystem=note.subsystem,
                verified=False,
                verification_score=0.0,
                rationale="No deterministic terms were available for verification.",
                matched_files=[],
                missing_terms=[],
            )

        match_map: dict[str, set[str]] = {}
        matched_terms: set[str] = set()

        for file_path in self._iter_source_files(repository_model):
            text = file_path.read_text(encoding="utf-8", errors="ignore").lower()
            relative = str(file_path.relative_to(repository_model.root))
            local_hits = {term for term in terms if term in text or term in relative.lower()}
            if local_hits:
                match_map[relative] = local_hits
                matched_terms.update(local_hits)

        matched_ratio = len(matched_terms) / max(1, len(terms))
        file_coverage = min(1.0, len(match_map) / 5.0)
        score = round(0.65 * matched_ratio + 0.35 * file_coverage, 3)
        verified = score >= 0.55 and len(match_map) >= 1 and len(matched_terms) >= 2
        missing_terms = sorted(term for term in terms if term not in matched_terms)

        rationale = (
            f"Matched {len(matched_terms)}/{len(terms)} deterministic terms across {len(match_map)} files."
            if verified
            else f"Insufficient deterministic evidence: matched {len(matched_terms)}/{len(terms)} terms across {len(match_map)} files."
        )

        return VerificationReport(
            concept=note.concept,
            subsystem=note.subsystem,
            verified=verified,
            verification_score=score,
            rationale=rationale,
            matched_files=[
                VerificationMatch(file=path, matched_terms=sorted(items))
                for path, items in sorted(match_map.items())
            ],
            missing_terms=missing_terms,
        )

    def _iter_source_files(self, repository_model: RepositoryModel) -> list[Path]:
        if repository_model.contract_files:
            return repository_model.contract_files

        source_root = repository_model.root / "src"
        root = source_root if source_root.exists() else repository_model.root
        allowed_extensions = {".sol", ".rs", ".ts", ".tsx", ".js", ".jsx", ".py", ".move", ".cairo", ".md"}
        excluded_segments = {".git", "node_modules", "dependencies", "cache", "dist", "build", "out"}
        files: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(segment in excluded_segments for segment in path.parts):
                continue
            if path.suffix.lower() not in allowed_extensions:
                continue
            files.append(path)
            if len(files) >= 600:
                break
        return files

    def _build_terms(self, *, note: TutorResearchNote, expected_guarantees: list[str]) -> list[str]:
        focused_corpus = [
            note.concept,
            note.subsystem,
            *note.evidence_targets,
            *expected_guarantees,
        ]
        contextual_corpus = [
            note.summary,
            *note.candidate_explanations,
        ]
        tokens: set[str] = set()
        for item in focused_corpus:
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", str(item).lower()):
                if token in {"the", "and", "for", "with", "that", "this", "from", "under", "into", "while", "before"}:
                    continue
                tokens.add(token)
        for item in contextual_corpus:
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{4,}", str(item).lower()):
                if token in {
                    "should",
                    "would",
                    "could",
                    "validated",
                    "pathway",
                    "accrue",
                    "accrues",
                    "through",
                    "across",
                    "using",
                    "where",
                    "which",
                    "their",
                }:
                    continue
                tokens.add(token)
        return sorted(tokens)