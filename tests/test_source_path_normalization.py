from __future__ import annotations

from pathlib import Path

from quantum_economic_auditor.source_acquisition.agent import _write_sources


def test_write_sources_normalizes_absolute_source_paths(tmp_path: Path) -> None:
    destination = tmp_path / "fetched"
    count = _write_sources(destination, {"/Users/aloysius/Repositories/protocol/src/Token.sol": "pragma solidity ^0.8.20;"})

    assert count == 1
    assert (destination / "Users" / "aloysius" / "Repositories" / "protocol" / "src" / "Token.sol").exists()
    assert not (tmp_path / "Users").exists()
