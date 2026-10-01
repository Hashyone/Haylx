from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_source_acquisition_agent_loads_dotenv(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ETHERSCAN_API_KEY=dotenv-test-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)

    sys.modules.pop("quantum_economic_auditor.source_acquisition.agent", None)
    module = importlib.import_module("quantum_economic_auditor.source_acquisition.agent")

    assert module.os.getenv("ETHERSCAN_API_KEY") == "dotenv-test-key"
