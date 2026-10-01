from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from quantum_economic_auditor.source_acquisition.agent import (
    EtherscanSourceClient,
    SourceAcquisitionAgent,
    SourceAcquisitionError,
    is_scope_url,
    _ADDRESS_IN_TEXT,
)


# ── is_scope_url ───────────────────────────────────────────────────────────

def test_is_scope_url_true_for_non_github_https():
    assert is_scope_url("https://audits.sherlock.xyz/contests/123") is True


def test_is_scope_url_false_for_github():
    assert is_scope_url("https://github.com/OlympusDAO/olympus-v3") is False


def test_is_scope_url_false_for_bare_name():
    assert is_scope_url("Raydium") is False


def test_is_scope_url_false_for_address():
    assert is_scope_url("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2") is False


# ── Address extraction regex ────────────────────────────────────────────────

def test_address_regex_finds_addresses_in_prose():
    text = "Core: 0xAbCd1234567890abcdef1234567890ABCDEF1234. Other: 0x1111111111111111111111111111111111111111"
    found = _ADDRESS_IN_TEXT.findall(text)
    assert len(found) == 2
    assert found[0] == "0xAbCd1234567890abcdef1234567890ABCDEF1234"


def test_address_regex_ignores_short_hex():
    text = "value 0xdeadbeef is not an address"
    found = _ADDRESS_IN_TEXT.findall(text)
    assert found == []


# ── acquire_from_scope_url ─────────────────────────────────────────────────

def _make_agent_with_page(tmp_path: Path, page_html: str, contract_name: str = "Token") -> SourceAcquisitionAgent:
    """Return an agent whose URL fetcher returns page_html and whose Etherscan client is mocked."""
    etherscan_source = json.dumps({
        "sources": {"Token.sol": {"content": "pragma solidity ^0.8.0; contract Token {}"}}
    })

    def fake_urlopen(request):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "api.etherscan.io" in url:
            response = MagicMock()
            response.read.return_value = json.dumps({
                "status": "1",
                "result": [{
                    "SourceCode": "{" + etherscan_source + "}",
                    "ContractName": contract_name,
                    "ABI": "[]",
                    "Proxy": "0",
                    "Implementation": "",
                }],
            }).encode()
            response.__enter__ = lambda s: s
            response.__exit__ = MagicMock(return_value=False)
            return response
        # scope page fetch
        response = MagicMock()
        response.read.return_value = page_html.encode()
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    agent = SourceAcquisitionAgent(
        cache_root=tmp_path / "cache",
        api_keys=["primary-key", "alternate-key"],
        urlopen=fake_urlopen,
    )
    return agent


def test_acquire_from_scope_url_finds_and_fetches_addresses(tmp_path):
    page = """
    <html><body>
    <p>In scope: 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 (USDC)</p>
    <p>Also: 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 (WETH)</p>
    </body></html>
    """
    agent = _make_agent_with_page(tmp_path, page)
    result = agent.acquire_from_scope_url(
        "https://audits.example.com/scope",
        chain="ethereum",
        output_root=tmp_path / "out",
    )
    assert result.input_kind == "scope_url"
    assert result.contract_count >= 1
    meta = json.loads(result.metadata_path.read_text())
    assert len(meta["addresses_found"]) == 2
    assert len(meta["acquired"]) == 2
    assert meta["acquisition_report"]["mode"] == "scope_url"


def test_acquire_from_scope_url_skips_zero_address(tmp_path):
    page = "<p>0x0000000000000000000000000000000000000000 zero addr</p>"
    agent = _make_agent_with_page(tmp_path, page)
    with pytest.raises(SourceAcquisitionError, match="no Ethereum contract addresses found"):
        agent.acquire_from_scope_url("https://example.com/scope", chain="ethereum", output_root=tmp_path / "out")


def test_acquire_from_scope_url_raises_when_no_addresses(tmp_path):
    agent = _make_agent_with_page(tmp_path, "<html><p>nothing here</p></html>")
    with pytest.raises(SourceAcquisitionError, match="no Ethereum contract addresses found"):
        agent.acquire_from_scope_url("https://example.com/scope", output_root=tmp_path / "out")


def test_acquire_from_scope_url_immunefi_information_falls_back_to_scope_page(tmp_path):
    calls: list[str] = []

    def fake_urlopen(request):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        calls.append(url)
        if "api.etherscan.io" in url:
            response = MagicMock()
            response.read.return_value = json.dumps(
                {
                    "status": "1",
                    "result": [
                        {
                            "SourceCode": "contract Token {}",
                            "ContractName": "Token",
                            "ABI": "[]",
                            "Proxy": "0",
                            "Implementation": "",
                        }
                    ],
                }
            ).encode()
            response.__enter__ = lambda s: s
            response.__exit__ = MagicMock(return_value=False)
            return response

        response = MagicMock()
        if url.endswith("/information/"):
            response.read.return_value = b"<html>No addresses here</html>"
        else:
            response.read.return_value = b"<html>In scope 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48</html>"
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    agent = SourceAcquisitionAgent(cache_root=tmp_path / "cache", api_keys=["k1"], urlopen=fake_urlopen)
    result = agent.acquire_from_scope_url(
        "https://immunefi.com/bug-bounty/capyfi/information/",
        chain="ethereum",
        output_root=tmp_path / "out",
    )

    assert result.input_kind == "scope_url"
    assert any(call.endswith("/information/") for call in calls)
    assert any(call.endswith("/scope/") for call in calls)


def test_resolve_input_dispatches_to_scope_url(tmp_path):
    page = "<p>0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48</p>"
    agent = _make_agent_with_page(tmp_path, page)
    result = agent.resolve_input(
        "https://audits.example.com/scope",
        chain="ethereum",
        output_root=tmp_path / "out2",
    )
    assert result.input_kind == "scope_url"


def test_etherscan_client_uses_alternate_api_key_on_primary_failure(monkeypatch):
    responses = []

    def fake_urlopen(request):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        responses.append(url)
        if "apikey=primary-key" in url:
            payload = {"status": "0", "result": "Max rate limit reached"}
        else:
            payload = {
                "status": "1",
                "result": [{
                    "SourceCode": "contract X {}",
                    "ContractName": "X",
                    "ABI": "[]",
                    "Proxy": "0",
                    "Implementation": "",
                }],
            }
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    client = EtherscanSourceClient(api_keys=["primary-key", "alternate-key"], urlopen=fake_urlopen)
    result = client.get_contract_metadata("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "ethereum")

    assert result["ContractName"] == "X"
    assert any("apikey=primary-key" in url for url in responses)
    assert any("apikey=alternate-key" in url for url in responses)


def test_etherscan_client_builds_v2_chainid_requests():
    captured_urls = []

    def fake_urlopen(request):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        captured_urls.append(url)
        response = MagicMock()
        response.read.return_value = json.dumps({
            "status": "1",
            "result": [{
                "SourceCode": "contract X {}",
                "ContractName": "X",
                "ABI": "[]",
                "Proxy": "0",
                "Implementation": "",
            }],
        }).encode()
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    client = EtherscanSourceClient(api_keys=["api-key"], urlopen=fake_urlopen)
    client.get_contract_metadata("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "base")

    assert captured_urls
    assert any("chainid=8453" in url for url in captured_urls)
    assert any("module=contract" in url for url in captured_urls)
    assert any("action=getsourcecode" in url for url in captured_urls)


# ── Assistant endpoint ──────────────────────────────────────────────────────

def test_assistant_endpoint_returns_reply(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))
    client = TestClient(api_app.app)
    response = client.post("/api/assistant/message", json={"message": "etherscan failed", "context": None})
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 20


def test_assistant_endpoint_returns_guidance_for_scope_url(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))
    client = TestClient(api_app.app)
    response = client.post("/api/assistant/message", json={"message": "how do I use a scope URL?", "context": None})
    assert response.status_code == 200
    assert "scope" in response.json()["reply"].lower()


def test_assistant_endpoint_mentions_untested_when_ledger_present(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({
        "repository_context": {"repository_path": "/tmp/proto"},
        "consensus": {"classification": "unknown"},
        "hypothesis_evidence_ledger": [
            {"hypothesis_id": "H-001", "status": "untested", "execution_case": {"status": "untested"}},
        ],
    }), encoding="utf-8")
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(result_path))
    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    client = TestClient(api_app.app)
    response = client.post("/api/assistant/message", json={"message": "what should I do next?", "context": None})
    assert response.status_code == 200
    assert "untested" in response.json()["reply"].lower()


def test_assistant_endpoint_proactively_shows_protocol_search_and_options(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))

    monkeypatch.setattr(
        api_app,
        "_proactive_protocol_lookup",
        lambda _message: {
            "query": "capyfi",
            "suggested_target": "capyfi-labs/capyfi-contracts",
            "github_candidates": [
                {
                    "full_name": "capyfi-labs/capyfi-contracts",
                    "html_url": "https://github.com/capyfi-labs/capyfi-contracts",
                    "stars": 42,
                    "description": "Capyfi core protocol contracts",
                }
            ],
            "program_listings": [
                {
                    "program": "immunefi",
                    "url": "https://immunefi.com/bug-bounty/capyfi/information/",
                    "found": True,
                    "status_code": 200,
                }
            ],
            "github_error": None,
        },
    )

    client = TestClient(api_app.app)
    response = client.post(
        "/api/assistant/message",
        json={"message": "https://immunefi.com/bug-bounty/capyfi/information/", "context": None, "auto_execute": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Search results" in payload["reply"]
    assert "AGREE" in payload["reply"]
    assert isinstance(payload["proactive_search"], dict)
    assert payload["proactive_search"]["query"] == "capyfi"
    assert payload["options"][0]["label"] == "AGREE"


def test_assistant_endpoint_extracts_protocol_from_error_detail_payload(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))

    monkeypatch.setattr(
        api_app,
        "_proactive_protocol_lookup",
        lambda _message: {
            "query": "CapyFi",
            "suggested_target": "https://immunefi.com/bug-bounty/capyfi/information/",
            "input_kind": "scope_url",
            "github_candidates": [],
            "program_listings": [],
            "github_error": None,
        },
    )

    client = TestClient(api_app.app)
    response = client.post(
        "/api/assistant/message",
        json={
            "message": "{\"detail\":\"unable to identify a strict protocol repository for 'CapyFi'. Top search candidates were: ...\"}",
            "context": None,
            "auto_execute": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Protocol discovery query: 'CapyFi'" in payload["reply"]
    assert "AGREE" in payload["reply"]


def test_assistant_endpoint_contract_address_returns_actionable_agree(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))

    client = TestClient(api_app.app)
    address = "0x00dc4965916e03A734190fA382633657c71f867E"
    response = client.post(
        "/api/assistant/message",
        json={"message": address, "context": None, "auto_execute": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Detected input type: contract address" in payload["reply"]
    assert "Authoritative target provided" in payload["reply"]
    assert payload["proactive_search"]["suggested_target"] == address
    assert payload["options"] == []


def test_assistant_endpoint_scope_url_prefers_scope_target_over_repo(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(api_app, "_check_program_listings", lambda _query: [])

    scope_url = "https://immunefi.com/bug-bounty/capyfi/information/"
    client = TestClient(api_app.app)
    response = client.post(
        "/api/assistant/message",
        json={"message": scope_url, "context": None, "auto_execute": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Detected input type: scope URL" in payload["reply"]
    assert "Authoritative target provided" in payload["reply"]
    assert payload["proactive_search"]["input_kind"] == "scope_url"
    assert payload["options"] == []


def test_assistant_endpoint_auto_executes_authoritative_scope_url(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))

    monkeypatch.setattr(
        api_app,
        "_execute_launch_request",
        lambda request: {
            "run_id": "run-123",
            "repository_path": str(tmp_path / "repo"),
            "protocol": "capyfi",
            "methodology_phases": 10,
            "consensus": "unknown",
            "report_path": "",
            "dashboard": {
                "methodology": {"phases": [{"name": "p1"}]},
                "research_hypotheses": [{"hypothesis_id": "h1"}],
                "falsification_execution": {
                    "executed": False,
                    "cases": [{"status": "untested"}],
                    "reason": "Fork RPC is required for live-state tests. Set HALYX_FORK_RPC_URL.",
                },
                "consensus": {"classification": "unknown"},
            },
        },
    )
    monkeypatch.setattr(api_app, "_load_acquisition_metadata", lambda _path: {"acquisition_report": {"mode": "scope_url"}})

    client = TestClient(api_app.app)
    response = client.post(
        "/api/assistant/message",
        json={"message": "https://immunefi.com/bug-bounty/capyfi/scope/", "context": None},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-123"
    assert payload["options"] == []
    assert "HALYX AUDIT STATUS" in payload["reply"]
    assert "Foundry execution: BLOCKED" in payload["reply"]
    assert "EXECUTION_BLOCKED" in payload["reply"]


def test_assistant_endpoint_agree_executes_suggested_target_from_context(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))

    captured: dict[str, object] = {}

    def fake_execute(request):
        captured["target"] = request.target
        return {
            "run_id": "run-234",
            "repository_path": str(tmp_path / "repo"),
            "protocol": "capyfi",
            "methodology_phases": 2,
            "consensus": "unknown",
            "report_path": "",
            "dashboard": {"methodology": {"phases": []}, "research_hypotheses": [], "falsification_execution": {}, "consensus": {}},
        }

    monkeypatch.setattr(api_app, "_execute_launch_request", fake_execute)
    monkeypatch.setattr(api_app, "_load_acquisition_metadata", lambda _path: {"acquisition_report": {"mode": "github"}})

    client = TestClient(api_app.app)
    response = client.post(
        "/api/assistant/message",
        json={
            "message": "AGREE",
            "context": "Reply with one of these options:\n• AGREE: proceed using target 'LaChain/capyfi-sc'",
        },
    )

    assert response.status_code == 200
    assert captured["target"] == "LaChain/capyfi-sc"
    assert response.json()["run_id"] == "run-234"


def test_assistant_endpoint_auto_execute_returns_blocker_payload_not_http_error(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import HTTPException
    import quantum_economic_auditor.api.app as api_app

    monkeypatch.setenv("HALYX_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("HALYX_PIPELINE_RESULT_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(
        api_app,
        "_execute_launch_request",
        lambda request: (_ for _ in ()).throw(HTTPException(status_code=400, detail="no Etherscan API key configured")),
    )

    client = TestClient(api_app.app)
    response = client.post(
        "/api/assistant/message",
        json={"message": "https://immunefi.com/bug-bounty/capyfi/scope/", "context": None},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Acquisition: BLOCKED" in payload["reply"]
    assert "no Etherscan API key configured" in payload["reply"]


def test_extract_protocol_query_rejects_unscoped_repository_error_blob() -> None:
    from quantum_economic_auditor.api.app import _extract_protocol_query

    payload = "unable to identify a strict protocol repository. Top search candidates were: capyfile/capyfile"
    assert _extract_protocol_query(payload) is None
