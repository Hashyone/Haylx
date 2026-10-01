from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from quantum_economic_auditor.source_acquisition.agent import (
    SourceAcquisitionAgent,
    _query_variants,
    is_contract_address,
    is_git_reference,
    is_github_reference,
    is_solidity_source_blob,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_acquire_from_address_fetches_proxy_and_implementation_sources(tmp_path: Path) -> None:
    proxy_address = "0x1111111111111111111111111111111111111111"
    implementation_address = "0x2222222222222222222222222222222222222222"
    payloads = [
        {
            "status": "1",
            "result": [
                {
                    "ContractName": "BridgeProxy",
                    "SourceCode": "contract BridgeProxy {}",
                    "ABI": "[]",
                    "Proxy": "1",
                    "Implementation": implementation_address,
                }
            ],
        },
        {
            "status": "1",
            "result": [
                {
                    "ContractName": "BridgeImpl",
                    "SourceCode": json.dumps(
                        {
                            "sources": {
                                "src/BridgeImpl.sol": {"content": "contract BridgeImpl {}"},
                                "src/BridgeTypes.sol": {"content": "library BridgeTypes {}"},
                            }
                        }
                    ),
                    "ABI": "[]",
                    "Proxy": "0",
                    "Implementation": "",
                }
            ],
        },
    ]

    def fake_urlopen(_url: str) -> FakeResponse:
        return FakeResponse(payloads.pop(0))

    agent = SourceAcquisitionAgent(cache_root=tmp_path, api_keys=["test-key"], urlopen=fake_urlopen)
    result = agent.acquire_from_address(proxy_address, chain="base")

    assert result.input_kind == "contract_address"
    assert result.primary_contract_name == "BridgeImpl"
    assert result.proxy_chain[0].proxy_address == proxy_address
    assert (result.source_root / "proxy" / "BridgeProxy.sol").exists()
    assert (result.source_root / "implementation" / "src" / "BridgeImpl.sol").exists()
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["proxy_chain"][0]["implementation_address"] == implementation_address
    assert metadata["acquisition_report"]["mode"] == "contract_address"


def test_acquire_from_github_clones_repository_reference(tmp_path: Path) -> None:
    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> SimpleNamespace:
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        (destination / "src").mkdir()
        (destination / "src" / "Protocol.sol").write_text("contract Protocol {}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    agent = SourceAcquisitionAgent(cache_root=tmp_path, command_runner=fake_run)
    result = agent.acquire_from_github("OlympusDAO/olympus-v3")

    assert result.input_kind == "github"
    assert result.source_root.exists()
    assert (result.source_root / "src" / "Protocol.sol").exists()
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["repo_slug"] == "OlympusDAO/olympus-v3"
    assert metadata["acquisition_report"]["mode"] == "github"


def test_source_reference_detectors_cover_contracts_and_github() -> None:
    assert is_contract_address("0x1234567890abcdef1234567890abcdef12345678")
    assert not is_contract_address("olympus-v3")
    assert is_github_reference("OlympusDAO/olympus-v3")
    assert is_github_reference("https://github.com/OlympusDAO/olympus-v3")


def test_query_variants_split_camel_case_protocol_names() -> None:
    variants = _query_variants("listaDAO")
    assert "lista dao" in [variant.lower() for variant in variants]
    assert "lista-dao" in [variant.lower() for variant in variants]


def test_resolve_input_protocol_name_discovers_and_clones_github_repo(tmp_path: Path) -> None:
    github_payload = {
        "items": [
            {
                "full_name": "some-random/docs",
                "html_url": "https://github.com/some-random/docs",
                "description": "documentation snippets",
                "stargazers_count": 1,
                "language": "Markdown",
                "archived": False,
                "fork": False,
                "topics": ["docs"],
            },
            {
                "full_name": "OriginProtocol/origin-dollar",
                "html_url": "https://github.com/OriginProtocol/origin-dollar",
                "description": "DeFi protocol with vault and staking contracts",
                "stargazers_count": 900,
                "language": "Solidity",
                "archived": False,
                "fork": False,
                "topics": ["defi", "protocol", "vault"],
            },
        ]
    }

    def fake_urlopen(request) -> FakeResponse:
        url = request if isinstance(request, str) else request.full_url
        if "api.github.com/search/repositories" in url:
            return FakeResponse(github_payload)
        if "api.github.com/repos/some-random/docs/contents" in url:
            return FakeResponse(
                [
                    {"name": "README.md", "type": "file"},
                    {"name": "docs", "type": "dir"},
                ]
            )
        if "api.github.com/repos/OriginProtocol/origin-dollar/contents" in url:
            return FakeResponse(
                [
                    {"name": "README.md", "type": "file"},
                    {"name": "contracts", "type": "dir"},
                    {"name": "foundry.toml", "type": "file"},
                ]
            )
        raise AssertionError(f"unexpected url: {url}")

    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> SimpleNamespace:
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        (destination / "contracts").mkdir()
        (destination / "contracts" / "Vault.sol").write_text("contract Vault {}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    agent = SourceAcquisitionAgent(cache_root=tmp_path, urlopen=fake_urlopen, command_runner=fake_run)
    result = agent.resolve_input("origin protocol")

    assert result.input_kind == "github"
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["input_kind"] == "protocol_name"
    assert metadata["protocol_name"] == "origin protocol"
    assert metadata["selected_repository"]["full_name"] == "OriginProtocol/origin-dollar"
    assert metadata["acquisition_report"]["mode"] == "protocol_name"
    assert (result.source_root / "contracts" / "Vault.sol").exists()


def test_score_repository_candidate_prefers_non_fork_active_solidity_protocol() -> None:
    good = {
        "full_name": "OriginProtocol/origin-dollar",
        "description": "defi protocol vault",
        "stargazers_count": 500,
        "language": "Solidity",
        "archived": False,
        "fork": False,
        "topics": ["defi", "protocol"],
    }
    weak = {
        "full_name": "random/origin-notes",
        "description": "notes",
        "stargazers_count": 3,
        "language": "Markdown",
        "archived": False,
        "fork": True,
        "topics": ["docs"],
    }

    score_good = SourceAcquisitionAgent._score_repository_candidate(good, "origin protocol")
    score_weak = SourceAcquisitionAgent._score_repository_candidate(weak, "origin protocol")
    assert score_good > score_weak


def test_protocol_search_strict_gate_rejects_docs_repo_even_if_name_matches(tmp_path: Path) -> None:
    github_payload = {
        "items": [
            {
                "full_name": "ListaDAO/listadao-docs",
                "html_url": "https://github.com/ListaDAO/listadao-docs",
                "description": "ListaDAO protocol docs",
                "stargazers_count": 5000,
                "language": "Markdown",
                "archived": False,
                "fork": False,
                "topics": ["defi", "protocol"],
            },
            {
                "full_name": "ListaDAO/lista-dao-contracts",
                "html_url": "https://github.com/ListaDAO/lista-dao-contracts",
                "description": "Core ListaDAO solidity contracts",
                "stargazers_count": 400,
                "language": "Solidity",
                "archived": False,
                "fork": False,
                "topics": ["defi", "protocol", "contracts"],
            },
        ]
    }

    def fake_urlopen(request) -> FakeResponse:
        url = request if isinstance(request, str) else request.full_url
        if "api.github.com/search/repositories" in url:
            return FakeResponse(github_payload)
        if "api.github.com/repos/ListaDAO/listadao-docs/contents" in url:
            return FakeResponse([
                {"name": "README.md", "type": "file"},
                {"name": "docs", "type": "dir"},
            ])
        if "api.github.com/repos/ListaDAO/lista-dao-contracts/contents" in url:
            return FakeResponse([
                {"name": "README.md", "type": "file"},
                {"name": "contracts", "type": "dir"},
                {"name": "hardhat.config.ts", "type": "file"},
            ])
        raise AssertionError(f"unexpected url: {url}")

    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> SimpleNamespace:
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        (destination / "contracts").mkdir()
        (destination / "contracts" / "ListaCore.sol").write_text("contract ListaCore {}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    agent = SourceAcquisitionAgent(cache_root=tmp_path, urlopen=fake_urlopen, command_runner=fake_run)
    result = agent.resolve_input("listaDAO")

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["selected_repository"]["full_name"] == "ListaDAO/lista-dao-contracts"


def test_protocol_search_rejects_low_signal_small_audit_prep_repo(tmp_path: Path) -> None:
    github_payload = {
        "items": [
            {
                "full_name": "analyst/listadao-audit-prep",
                "html_url": "https://github.com/analyst/listadao-audit-prep",
                "description": "audit review prep test repo for ListaDAO",
                "stargazers_count": 0,
                "language": "Solidity",
                "archived": False,
                "fork": False,
                "topics": ["security"],
            },
            {
                "full_name": "ListaDAO/lista-contracts",
                "html_url": "https://github.com/ListaDAO/lista-contracts",
                "description": "Core protocol contracts",
                "stargazers_count": 60,
                "language": "Solidity",
                "archived": False,
                "fork": False,
                "topics": ["defi", "protocol", "dao"],
            },
        ]
    }

    def fake_urlopen(request) -> FakeResponse:
        url = request if isinstance(request, str) else request.full_url
        if "api.github.com/search/repositories" in url:
            return FakeResponse(github_payload)
        if "api.github.com/repos/analyst/listadao-audit-prep/contents" in url:
            return FakeResponse([
                {"name": "contracts", "type": "dir"},
                {"name": "foundry.toml", "type": "file"},
            ])
        if "api.github.com/repos/ListaDAO/lista-contracts/contents" in url:
            return FakeResponse([
                {"name": "contracts", "type": "dir"},
                {"name": "foundry.toml", "type": "file"},
                {"name": "README.md", "type": "file"},
            ])
        raise AssertionError(f"unexpected url: {url}")

    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> SimpleNamespace:
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        (destination / "contracts").mkdir()
        (destination / "contracts" / "Lista.sol").write_text("contract Lista {}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    agent = SourceAcquisitionAgent(cache_root=tmp_path, urlopen=fake_urlopen, command_runner=fake_run)
    result = agent.resolve_input("listaDAO")
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["selected_repository"]["full_name"] == "ListaDAO/lista-contracts"


def test_protocol_search_uses_owner_discovery_fallback_when_repo_search_is_weak(tmp_path: Path) -> None:
    weak_repo_payload = {
        "items": [
            {
                "full_name": "analyst/listadao-audit-prep",
                "html_url": "https://github.com/analyst/listadao-audit-prep",
                "description": "audit review prep test",
                "stargazers_count": 0,
                "language": "Solidity",
                "archived": False,
                "fork": False,
                "topics": ["security"],
            }
        ]
    }

    owner_search_payload = {
        "items": [
            {
                "login": "ListaDAO",
                "type": "Organization",
            }
        ]
    }

    owner_repos_payload = [
        {
            "full_name": "ListaDAO/lista-core",
            "html_url": "https://github.com/ListaDAO/lista-core",
            "description": "Core protocol contracts",
            "stargazers_count": 80,
            "language": "Solidity",
            "archived": False,
            "fork": False,
            "topics": ["defi", "dao", "protocol"],
        }
    ]

    def fake_urlopen(request) -> FakeResponse:
        url = request if isinstance(request, str) else request.full_url
        if "api.github.com/search/repositories" in url:
            return FakeResponse(weak_repo_payload)
        if "api.github.com/search/users" in url:
            return FakeResponse(owner_search_payload)
        if "api.github.com/users/ListaDAO/repos" in url:
            return FakeResponse(owner_repos_payload)
        if "api.github.com/repos/analyst/listadao-audit-prep/contents" in url:
            return FakeResponse([
                {"name": "contracts", "type": "dir"},
                {"name": "foundry.toml", "type": "file"},
            ])
        if "api.github.com/repos/ListaDAO/lista-core/contents" in url:
            return FakeResponse([
                {"name": "contracts", "type": "dir"},
                {"name": "hardhat.config.ts", "type": "file"},
                {"name": "README.md", "type": "file"},
            ])
        raise AssertionError(f"unexpected url: {url}")

    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> SimpleNamespace:
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        (destination / "contracts").mkdir()
        (destination / "contracts" / "Core.sol").write_text("contract Core {}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    agent = SourceAcquisitionAgent(cache_root=tmp_path, urlopen=fake_urlopen, command_runner=fake_run)
    result = agent.resolve_input("listaDAO")
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["selected_repository"]["full_name"] == "ListaDAO/lista-core"


def test_protocol_scoring_prefers_contracts_repo_over_token_only_repo() -> None:
    contracts_repo = {
        "full_name": "lista-dao/lista-dao-contracts",
        "description": None,
        "stargazers_count": 60,
        "language": "Solidity",
        "archived": False,
        "fork": False,
        "topics": [],
    }
    token_repo = {
        "full_name": "lista-dao/lista-token",
        "description": None,
        "stargazers_count": 26,
        "language": "Solidity",
        "archived": False,
        "fork": False,
        "topics": [],
    }

    contracts_score = SourceAcquisitionAgent._score_repository_candidate(contracts_repo, "listaDAO")
    token_score = SourceAcquisitionAgent._score_repository_candidate(token_repo, "listaDAO")
    assert contracts_score > token_score


def test_protocol_scoring_can_prefer_non_solidity_protocol_repositories() -> None:
    protocol_repo = {
        "full_name": "raydium-io/raydium-amm",
        "description": "Raydium AMM onchain protocol",
        "stargazers_count": 120,
        "language": "Rust",
        "archived": False,
        "fork": False,
        "topics": ["defi", "amm", "protocol"],
    }
    docs_repo = {
        "full_name": "raydium-io/raydium-docs",
        "description": "Raydium documentation",
        "stargazers_count": 400,
        "language": "Markdown",
        "archived": False,
        "fork": False,
        "topics": ["docs"],
    }

    protocol_score = SourceAcquisitionAgent._score_repository_candidate(protocol_repo, "Raydium")
    docs_score = SourceAcquisitionAgent._score_repository_candidate(docs_repo, "Raydium")
    assert protocol_score > docs_score


def test_git_reference_detector_covers_generic_git_urls() -> None:
    assert is_git_reference("https://gitlab.com/acme/protocol.git")
    assert is_git_reference("git@gitlab.com:acme/protocol.git")
    assert not is_git_reference("https://audits.sherlock.xyz/contests/123")


def test_solidity_blob_detector_identifies_pasted_source() -> None:
    source_blob = "pragma solidity ^0.8.20;\ncontract Vault { }\n"
    assert is_solidity_source_blob(source_blob)
    assert not is_solidity_source_blob("Origin Protocol")


def test_resolve_input_zip_archive_extracts_sources(tmp_path: Path) -> None:
    archive_path = tmp_path / "protocol.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("contracts/Core.sol", "pragma solidity ^0.8.0; contract Core {}")

    agent = SourceAcquisitionAgent(cache_root=tmp_path / "cache")
    result = agent.resolve_input(str(archive_path))

    assert result.input_kind == "zip"
    assert (result.source_root / "contracts" / "Core.sol").exists()
    assert result.contract_count == 1
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["acquisition_report"]["mode"] == "zip"


def test_resolve_input_solidity_source_blob_writes_manual_source(tmp_path: Path) -> None:
    source_blob = "pragma solidity ^0.8.20;\ncontract ManualTarget { function ping() external {} }\n"
    agent = SourceAcquisitionAgent(cache_root=tmp_path / "cache")

    result = agent.resolve_input(source_blob)

    assert result.input_kind == "manual_source"
    assert result.contract_count == 1
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["acquisition_report"]["mode"] == "manual_source"
    generated_sources = list(result.source_root.glob("*.sol"))
    assert generated_sources
    assert "ManualTarget" in generated_sources[0].read_text(encoding="utf-8")


def test_resolve_input_local_solidity_file_is_supported(tmp_path: Path) -> None:
    solidity_path = tmp_path / "Vault.sol"
    solidity_path.write_text("pragma solidity ^0.8.20;\ncontract Vault {}\n", encoding="utf-8")
    agent = SourceAcquisitionAgent(cache_root=tmp_path / "cache")

    result = agent.resolve_input(str(solidity_path))

    assert result.input_kind == "manual_source"
    assert (result.source_root / "Vault.sol").exists()
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["acquisition_report"]["mode"] == "manual_source"


def test_resolve_input_generic_git_url_clones_repository(tmp_path: Path) -> None:
    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> SimpleNamespace:
        assert command[0:3] == ["git", "clone", "--depth"]
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        (destination / "contracts").mkdir()
        (destination / "contracts" / "Generic.sol").write_text("contract Generic {}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    agent = SourceAcquisitionAgent(cache_root=tmp_path, command_runner=fake_run)
    result = agent.resolve_input("https://gitlab.com/acme/protocol.git")

    assert result.input_kind == "git"
    assert (result.source_root / "contracts" / "Generic.sol").exists()
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["acquisition_report"]["mode"] == "git"