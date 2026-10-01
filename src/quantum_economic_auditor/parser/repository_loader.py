from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXCLUDED_SEGMENTS = {
    ".git",
    "dependencies",
    "node_modules",
    "cache",
    "build",
    "dist",
    "out",
    "test",
    "tests",
    "lib",
}


@dataclass
class RepositoryModel:
    """Minimal repository abstraction for the research framework."""

    root: Path
    contract_files: list[Path]
    interfaces: list[str]
    inherited_contracts: list[str]


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_SEGMENTS for part in path.parts)


def _protocol_source_root(root: Path) -> Path:
    src_root = root / "src"
    return src_root if src_root.exists() else root


def load_repository(path: str) -> RepositoryModel:
    """Load a repository snapshot into a project model.

    This stage intentionally remains lightweight and deterministic so it can be tested
    without requiring an external network call or Solidity toolchain.
    """

    root = Path(path)
    source_root = _protocol_source_root(root)
    contract_files = sorted(
        file_path
        for file_path in source_root.rglob("*.sol")
        if file_path.is_file() and not _is_excluded(file_path)
    )
    interfaces: list[str] = []
    inherited_contracts: list[str] = []

    for file_path in contract_files:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if "interface" in text:
            interfaces.append(file_path.stem)
        if "contract" in text and " is " in text:
            inherited_contracts.append(file_path.stem)

    return RepositoryModel(
        root=root,
        contract_files=contract_files,
        interfaces=sorted(set(interfaces)),
        inherited_contracts=sorted(set(inherited_contracts)),
    )
