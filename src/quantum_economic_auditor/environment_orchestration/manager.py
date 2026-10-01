from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnvironmentHealthReport:
    protocol_identifier: str
    repository_imported: bool
    dependencies_installed: bool
    compiler_configured: bool
    framework_installed: bool
    build_successful: bool
    tests_compiled: bool
    fork_available: bool
    knowledge_graph_generation_ready: bool
    research_ready: bool
    failure_explanations: list[str]


class EnvironmentOrchestrationManager:
    """Coordinate environment preparation for protocol research."""

    def __init__(self, repository_path: Path) -> None:
        self.repository_path = repository_path

    def evaluate_environment(
        self,
        *,
        dependencies_installed: bool,
        compiler_configured: bool,
        framework_installed: bool,
        build_successful: bool,
        tests_compiled: bool,
        fork_available: bool,
        knowledge_graph_generation_ready: bool,
        protocol_identifier: str | None = None,
    ) -> EnvironmentHealthReport:
        failures: list[str] = []
        if not dependencies_installed:
            failures.append("dependencies missing")
        if not compiler_configured:
            failures.append("compiler not configured")
        if not framework_installed:
            failures.append("framework not installed")
        if not build_successful:
            failures.append("build failed")
        if not tests_compiled:
            failures.append("tests did not compile")
        if not fork_available:
            failures.append("fork not available")
        if not knowledge_graph_generation_ready:
            failures.append("knowledge graph not ready")

        research_ready = not failures
        repository_imported = self.repository_path.exists() or research_ready
        return EnvironmentHealthReport(
            protocol_identifier=protocol_identifier or self.repository_path.name,
            repository_imported=repository_imported,
            dependencies_installed=dependencies_installed,
            compiler_configured=compiler_configured,
            framework_installed=framework_installed,
            build_successful=build_successful,
            tests_compiled=tests_compiled,
            fork_available=fork_available,
            knowledge_graph_generation_ready=knowledge_graph_generation_ready,
            research_ready=research_ready,
            failure_explanations=failures,
        )
