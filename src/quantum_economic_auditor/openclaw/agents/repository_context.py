from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantum_economic_auditor.models.evidence import AgentEvidence, ClaimSource, EvidencedClaim
from quantum_economic_auditor.openclaw.orchestrator import SpecialistAgent


@dataclass
class RepositoryContext:
    repository_path: Path
    source_files: list[str] = field(default_factory=list)
    markdown_files: list[str] = field(default_factory=list)
    scope_summary: str = ""
    known_issues: list[str] = field(default_factory=list)


class RepositoryContextAgent(SpecialistAgent):
    """Collect repository context that is scoped to the target program and its known issues."""

    name = "repository_context"

    def collect_repository_context(
        self,
        *,
        repository_path: Path | str,
        program_scope: str | None = None,
        known_issues: list[str] | None = None,
    ) -> RepositoryContext:
        root = Path(repository_path)
        source_files = [str(path) for path in sorted(root.rglob("*.py")) if path.is_file() and "/.git/" not in str(path)]
        markdown_files = [str(path) for path in sorted(root.rglob("*.md")) if path.is_file() and "/.git/" not in str(path)]

        scope_fragments: list[str] = []
        discovered_known_issues: list[str] = list(known_issues or [])

        for markdown_path in markdown_files:
            text = Path(markdown_path).read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            in_scope_section = False
            in_known_issues_section = False

            for line in text.splitlines():
                cleaned_line = line.strip()
                if not cleaned_line:
                    continue

                if cleaned_line.startswith("#"):
                    heading = cleaned_line.lstrip("#").strip().lower()
                    in_scope_section = "scope" in heading
                    in_known_issues_section = "known issue" in heading or "known issues" in heading
                    continue

                if in_known_issues_section:
                    if cleaned_line.startswith("-") or cleaned_line.startswith("*"):
                        discovered_known_issues.append(cleaned_line[1:].strip())
                    elif not cleaned_line.startswith("#"):
                        discovered_known_issues.append(cleaned_line)
                    continue

                if in_scope_section:
                    if cleaned_line.startswith("-") or cleaned_line.startswith("*"):
                        scope_fragments.append(cleaned_line[1:].strip())
                    elif not cleaned_line.startswith("#"):
                        scope_fragments.append(cleaned_line)
                    continue

                if program_scope and program_scope.lower() in cleaned_line.lower() and not scope_fragments:
                    scope_fragments.append(cleaned_line)

        scope_summary = " ".join(scope_fragments).strip() if scope_fragments else (
            f"Repository context scoped to the program area '{program_scope or 'target'}'."
        )

        if not discovered_known_issues:
            discovered_known_issues.append("No explicit known issues were found in repository documentation.")

        return RepositoryContext(
            repository_path=root,
            source_files=source_files,
            markdown_files=markdown_files,
            scope_summary=scope_summary,
            known_issues=discovered_known_issues,
        )

    def run(self, payload: dict[str, Any]) -> list[AgentEvidence]:
        repository_path = payload.get("repository_path")
        program_scope = payload.get("program_scope")
        known_issues = payload.get("known_issues")

        if repository_path is None:
            raise ValueError("repository_path is required")

        context = self.collect_repository_context(
            repository_path=repository_path,
            program_scope=program_scope,
            known_issues=known_issues if isinstance(known_issues, list) else None,
        )

        claim = EvidencedClaim(
            id=f"context-{context.repository_path.name}",
            statement=(
                f"Repository context captured for scope '{program_scope or 'target'}' with {len(context.known_issues)} known issue references."
            ),
            source=ClaimSource.DOCUMENTATION,
            source_reference=str(context.repository_path / "README.md"),
            confidence=0.91,
            verification_method="markdown and source file inspection",
            verified=True,
        )
        return [
            AgentEvidence(
                agent_name=self.name,
                subsystem_id=str(context.repository_path.name),
                claim=claim,
                supporting_references=context.markdown_files + context.source_files,
                confidence="indirect reconstruction",
            )
        ]
