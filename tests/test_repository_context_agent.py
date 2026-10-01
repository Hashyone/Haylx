from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.openclaw.orchestrator import OpenClawOrchestrator
from quantum_economic_auditor.openclaw.agents.repository_context import RepositoryContextAgent


def test_repository_context_agent_is_scope_aware_and_reads_known_issues(tmp_path: Path) -> None:
    repo_root = tmp_path / "program-repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "docs").mkdir(parents=True)
    (repo_root / "src" / "bridge.py").write_text(
        "def bridge_transfer():\n    return 'bridge'\n",
        encoding="utf-8",
    )
    (repo_root / "README.md").write_text(
        "# Program\n\n## Scope\nThis program focuses on bridge transfers and vault accounting.\n\n## Known Issues\n- Bridge relayer can be frontrun.\n- Oracle staleness impacts vault accounting.\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "notes.md").write_text(
        "## Scope\nThe program covers bridge transfers.\n",
        encoding="utf-8",
    )

    agent = RepositoryContextAgent()
    context = agent.collect_repository_context(
        repository_path=repo_root,
        program_scope="bridge",
        known_issues=["legacy oracle bug"],
    )

    assert context.repository_path == repo_root
    assert context.source_files == [str(repo_root / "src" / "bridge.py")]
    assert any(path.endswith("README.md") for path in context.markdown_files)
    assert any("Bridge relayer" in issue for issue in context.known_issues)
    assert "legacy oracle bug" in context.known_issues
    assert "bridge transfers" in context.scope_summary.lower()

    orchestrator = OpenClawOrchestrator()
    orchestrator.register_agent(agent)
    evidence = orchestrator.run_agent("repository_context", {"repository_path": repo_root, "program_scope": "bridge"})

    assert len(evidence) >= 1
    assert any("scope" in item.claim.statement.lower() or "known issue" in item.claim.statement.lower() for item in evidence)
