from __future__ import annotations

import json
import math
import os
import re
import subprocess
import urllib.parse
import urllib.request
import zipfile
from urllib.error import HTTPError, URLError
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv


def _load_environment() -> None:
    candidates: list[Path] = []
    for base in (
        Path.cwd(),
        Path(__file__).resolve().parents[3],
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parents[0],
    ):
        candidates.append(base / ".env")

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            load_dotenv(resolved, override=False)
            return

    load_dotenv(override=False)


_load_environment()

ETHERSCAN_V2_API_URL = "https://api.etherscan.io/v2/api"
SCOPE_URL_PATTERN = re.compile(r"^https?://")
# Addresses must be surrounded by word-boundary-like chars to avoid hex false-positives
_ADDRESS_IN_TEXT = re.compile(r"(?<![a-fA-F0-9])(0x[a-fA-F0-9]{40})(?![a-fA-F0-9])")
CHAIN_IDS: dict[str, str] = {
    "ethereum": "1",
    "mainnet": "1",
    "optimism": "10",
    "bsc": "56",
    "polygon": "137",
    "fantom": "250",
    "base": "8453",
    "arbitrum": "42161",
    "avalanche": "43114",
    "linea": "59144",
    "blast": "81457",
    "scroll": "534352",
}
PROTOCOL_KEYWORDS = {"protocol", "defi", "dao", "vault", "token", "bridge", "staking", "amm", "lending"}
LOW_SIGNAL_KEYWORDS = {"audit", "review", "prep", "template", "example", "demo", "test", "playground", "poc"}
CODE_SIGNAL_LANGUAGES = {
    "solidity",
    "rust",
    "go",
    "typescript",
    "javascript",
    "python",
    "move",
    "cairo",
}
ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
GITHUB_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$")
GENERIC_GIT_URL_PATTERN = re.compile(r"^(?:https?://|git@)[^\s]+(?:\.git)?/?$")


class SourceAcquisitionError(RuntimeError):
    """Raised when source acquisition fails."""


@dataclass(slots=True)
class ProxyResolution:
    proxy_address: str
    implementation_address: str


@dataclass(slots=True)
class AcquisitionResult:
    source_root: Path
    input_kind: str
    primary_contract_name: str
    contract_count: int
    metadata_path: Path
    proxy_chain: list[ProxyResolution] = field(default_factory=list)


def is_contract_address(value: str) -> bool:
    return bool(ADDRESS_PATTERN.match(value.strip()))


def is_scope_url(value: str) -> bool:
    """Returns True when the value looks like an http(s) URL but is NOT a known git host."""
    stripped = value.strip()
    if not SCOPE_URL_PATTERN.match(stripped):
        return False
    # GitHub URLs are handled by the existing GitHub path, not the scope-URL path.
    if "github.com/" in stripped:
        return False
    return True


def is_github_reference(value: str) -> bool:
    stripped = value.strip()
    if stripped.startswith("https://github.com/") or stripped.startswith("git@github.com:"):
        return True
    return bool(GITHUB_SLUG_PATTERN.match(stripped))


def is_git_reference(value: str) -> bool:
    stripped = value.strip()
    if is_github_reference(stripped):
        return True
    if stripped.startswith("git@"):
        return bool(GENERIC_GIT_URL_PATTERN.match(stripped))
    if stripped.startswith("http://") or stripped.startswith("https://"):
        parsed = urllib.parse.urlparse(stripped)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path:
            if parsed.path.endswith(".git"):
                return True
            # Common git hosts that are often referenced without ".git" suffix.
            if any(host in parsed.netloc.lower() for host in ("github.com", "gitlab.com", "bitbucket.org")):
                path_parts = [segment for segment in parsed.path.strip("/").split("/") if segment]
                return len(path_parts) >= 2
    return False


def is_solidity_source_blob(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    has_newline = "\n" in stripped or "\r" in stripped
    has_solidity_signal = any(
        signal in stripped for signal in ("pragma solidity", "contract ", "interface ", "library ")
    )
    return has_newline and has_solidity_signal


def _normalize_chain_id(chain: str) -> str:
    normalized = chain.strip().lower()
    if normalized.isdigit():
        return normalized
    if normalized not in CHAIN_IDS:
        supported = ", ".join(sorted(CHAIN_IDS))
        raise SourceAcquisitionError(f"unsupported chain '{chain}'. Supported values: {supported}")
    return CHAIN_IDS[normalized]


def _sanitize_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-") or "source"


def _tokenize(value: str) -> list[str]:
    with_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    lowered = with_boundaries.lower()
    return [token for token in re.split(r"[^a-z0-9]+", lowered) if token]


def _query_variants(protocol_name: str) -> list[str]:
    tokens = _tokenize(protocol_name)
    variants = [protocol_name.strip()]
    if tokens:
        variants.append(" ".join(tokens))
        variants.append("-".join(tokens))
    dedup: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        normalized = variant.strip().lower()
        if not normalized or normalized in seen:
            continue
        dedup.append(variant.strip())
        seen.add(normalized)
    return dedup


def _parse_source_files(source_code_raw: str, contract_name: str) -> dict[str, str]:
    src = source_code_raw.strip()
    if src.startswith("{{") and src.endswith("}}"):
        src = src[1:-1]

    try:
        parsed = json.loads(src)
    except json.JSONDecodeError:
        return {f"{contract_name}.sol": source_code_raw}

    sources = parsed.get("sources", {}) if isinstance(parsed, dict) else {}
    extracted: dict[str, str] = {}
    for path, payload in sources.items():
        if isinstance(payload, dict) and "content" in payload:
            extracted[path] = payload["content"]
    return extracted or {f"{contract_name}.sol": source_code_raw}


def _normalize_contract_metadata(raw: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}

    lowered: dict[str, object] = {}
    for key, value in raw.items():
        if isinstance(key, str):
            lowered[key.lower()] = value

    canonical: dict[str, object] = {}
    for key, raw_key in {
        "SourceCode": ("sourcecode", "source_code"),
        "ABI": ("abi",),
        "ContractName": ("contractname", "contract_name"),
        "Proxy": ("proxy",),
        "Implementation": ("implementation", "implementationaddress", "implementation_address"),
        "CompilerVersion": ("compilerversion", "compiler_version"),
        "OptimizationUsed": ("optimizationused", "optimization_used"),
        "Runs": ("runs",),
        "LicenseType": ("licensetype", "license_type"),
    }.items():
        for candidate in raw_key:
            if candidate in lowered:
                canonical[key] = lowered[candidate]
                break

    for key, value in raw.items():
        if isinstance(key, str) and key not in canonical:
            canonical[key] = value
    return canonical


def _is_proxy_record(metadata: dict[str, object]) -> bool:
    proxy_value = metadata.get("Proxy")
    if proxy_value is None:
        proxy_value = metadata.get("proxy")
    if isinstance(proxy_value, bool):
        return proxy_value
    if isinstance(proxy_value, (int, float)):
        return bool(proxy_value)
    if isinstance(proxy_value, str):
        lowered = proxy_value.strip().lower()
        return lowered in {"1", "true", "yes", "y"}
    return False


def _write_sources(destination: Path, source_map: dict[str, str]) -> int:
    count = 0
    for relative_path, content in source_map.items():
        normalized_path = str(relative_path).strip().replace("\\", "/")
        if normalized_path.startswith("/"):
            normalized_path = normalized_path.lstrip("/")
        target = destination / normalized_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        count += 1
    return count


def _scope_url_variants(url: str) -> list[str]:
    parsed = urllib.parse.urlparse(url)
    if "immunefi.com" not in parsed.netloc.lower():
        return [url]

    normalized = url.rstrip("/")
    variants = [normalized]
    if "/bug-bounty/" in normalized:
        if normalized.endswith("/information"):
            variants.append(normalized.removesuffix("/information") + "/scope")
        elif normalized.endswith("/scope"):
            variants.append(normalized.removesuffix("/scope") + "/information")
        else:
            variants.append(normalized + "/scope")
            variants.append(normalized + "/information")

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        candidate = variant + "/"
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _build_acquisition_report(
    *,
    mode: str,
    source_root: Path,
    primary_contract_name: str,
    contract_count: int,
    source_reference: str,
    chain: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "version": "1",
        "mode": mode,
        "status": "success",
        "source_reference": source_reference,
        "artifacts": {
            "source_root": str(source_root),
            "primary_contract_name": primary_contract_name,
            "contract_count": contract_count,
        },
    }
    if chain:
        report["chain"] = chain
    if warnings:
        report["warnings"] = warnings
    return report


class EtherscanSourceClient:
    """Fetch verified contract sources via the Etherscan V2 API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_alt: str | None = None,
        api_keys: list[str] | None = None,
        urlopen: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        candidate_keys = list(api_keys or [])
        for value in (
            api_key,
            api_key_alt,
            os.getenv("ETHERSCAN_API_KEY"),
            os.getenv("ETHERSCAN_API_KEY_ALT"),
            os.getenv("ETHERSCAN_API_TOKEN"),
        ):
            if value and value.strip():
                candidate_keys.append(value.strip())
        env_keys = os.getenv("ETHERSCAN_API_KEYS") or ""
        for value in re.split(r"[\n,;]+", env_keys):
            if value and value.strip():
                candidate_keys.append(value.strip())
        self.api_keys = list(dict.fromkeys(candidate_keys))
        self.urlopen = urlopen

    def get_contract_metadata(self, address: str, chain: str) -> dict[str, object]:
        chain_id = _normalize_chain_id(chain)
        if not self.api_keys:
            raise SourceAcquisitionError("no Etherscan API key configured")

        failures: list[str] = []
        for api_key in self.api_keys:
            params = urllib.parse.urlencode(
                {
                    "chainid": chain_id,
                    "module": "contract",
                    "action": "getsourcecode",
                    "address": address,
                    "apikey": api_key,
                }
            )
            url = f"{ETHERSCAN_V2_API_URL}?{params}"
            try:
                with self.urlopen(url) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, json.JSONDecodeError, OSError) as error:
                failures.append(f"{api_key[:6]}...: {error}")
                continue

            result = payload.get("result")
            if payload.get("status") == "1" and result:
                records: list[dict[str, object]] = []
                if isinstance(result, list):
                    records = [entry for entry in result if isinstance(entry, dict)]
                elif isinstance(result, dict):
                    records = [result]
                for raw_record in records:
                    normalized = _normalize_contract_metadata(raw_record)
                    if normalized.get("SourceCode") or normalized.get("Implementation") or _is_proxy_record(normalized):
                        return normalized
                if records:
                    return _normalize_contract_metadata(records[0])
                failures.append(f"{api_key[:6]}...: empty result payload")
                continue

            failures.append(f"{api_key[:6]}...: {payload.get('result')}")

        raise SourceAcquisitionError(f"block explorer lookup failed for {address} on {chain}: {'; '.join(failures)}")


def _resolve_storage_root(*, env_var: str, default_subdir: str) -> Path:
    configured = os.getenv(env_var)
    if configured:
        path = Path(configured).expanduser()
    else:
        path = Path.cwd() / ".halyx-home"
    path.mkdir(parents=True, exist_ok=True)
    return path


class SourceAcquisitionAgent:
    """Acquire protocol source trees from local paths, block explorers, or GitHub."""

    def __init__(
        self,
        *,
        cache_root: Path | None = None,
        api_key: str | None = None,
        api_key_alt: str | None = None,
        api_keys: list[str] | None = None,
        github_token: str | None = None,
        urlopen: Callable[..., object] = urllib.request.urlopen,
        command_runner: Callable[..., object] | None = None,
    ) -> None:
        self.cache_root = cache_root or (_resolve_storage_root(env_var="HALYX_HOME", default_subdir="sources") / "sources")
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.etherscan = EtherscanSourceClient(api_key=api_key, api_key_alt=api_key_alt, api_keys=api_keys, urlopen=urlopen)
        self.github_token = github_token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
        self.urlopen = urlopen
        self.command_runner = command_runner or subprocess.run

    def resolve_input(self, value: str, *, chain: str | None = None, output_root: Path | None = None) -> AcquisitionResult:
        candidate_path = Path(value)
        if candidate_path.exists():
            resolved = candidate_path.resolve()
            if resolved.is_dir():
                root = resolved
                contract_count = len(list(root.rglob("*.sol")))
                metadata_path = root / ".halyx-acquisition.json"
                if not metadata_path.exists():
                    metadata_path.write_text(
                        json.dumps(
                            {
                                "input_kind": "local",
                                "source": str(root),
                                "acquisition_report": _build_acquisition_report(
                                    mode="local",
                                    source_root=root,
                                    primary_contract_name=root.name,
                                    contract_count=contract_count,
                                    source_reference=str(root),
                                ),
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                return AcquisitionResult(
                    source_root=root,
                    input_kind="local",
                    primary_contract_name=root.name,
                    contract_count=contract_count,
                    metadata_path=metadata_path,
                )
            if resolved.is_file() and resolved.suffix.lower() == ".zip":
                return self.acquire_from_zip(resolved, output_root=output_root)
            if resolved.is_file() and resolved.suffix.lower() == ".sol":
                return self.acquire_from_solidity_file(resolved, output_root=output_root)
            raise SourceAcquisitionError(
                f"unsupported local file input '{resolved}'. Provide a directory, .zip archive, or .sol file"
            )
        if is_solidity_source_blob(value):
            return self.acquire_from_source_text(value, output_root=output_root)
        if is_git_reference(value):
            if is_github_reference(value):
                return self.acquire_from_github(value, output_root=output_root)
            return self.acquire_from_git(value, output_root=output_root)
        if is_scope_url(value):
            return self.acquire_from_scope_url(value, chain=chain or "ethereum", output_root=output_root)
        if is_contract_address(value):
            return self.acquire_from_address(value, chain=chain or "ethereum", output_root=output_root)
        return self.acquire_from_protocol_name(value, output_root=output_root)

    def acquire_from_zip(self, archive_path: Path, *, output_root: Path | None = None) -> AcquisitionResult:
        archive = archive_path.resolve()
        slug = _sanitize_segment(archive.stem)
        root = output_root or (self.cache_root / "archives" / slug)
        root.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(archive, "r") as zf:
            for member in zf.infolist():
                member_name = member.filename
                if not member_name or member_name.endswith("/"):
                    continue
                target = (root / member_name).resolve()
                if not str(target).startswith(str(root.resolve())):
                    raise SourceAcquisitionError(f"zip archive contains invalid path traversal entry: {member_name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as source_file:
                    target.write_bytes(source_file.read())

        metadata_path = root / ".halyx-acquisition.json"
        contract_count = len(list(root.rglob("*.sol")))
        metadata_path.write_text(
            json.dumps(
                {
                    "input_kind": "zip",
                    "archive_path": str(archive),
                    "acquisition_report": _build_acquisition_report(
                        mode="zip",
                        source_root=root,
                        primary_contract_name=slug,
                        contract_count=contract_count,
                        source_reference=str(archive),
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return AcquisitionResult(
            source_root=root,
            input_kind="zip",
            primary_contract_name=slug,
            contract_count=contract_count,
            metadata_path=metadata_path,
        )

    def acquire_from_solidity_file(self, source_file: Path, *, output_root: Path | None = None) -> AcquisitionResult:
        source = source_file.resolve()
        source_text = source.read_text(encoding="utf-8", errors="ignore")
        contract_hint = source.stem
        return self.acquire_from_source_text(source_text, output_root=output_root, source_name=contract_hint)

    def acquire_from_source_text(
        self,
        source_text: str,
        *,
        output_root: Path | None = None,
        source_name: str | None = None,
    ) -> AcquisitionResult:
        contract_name = _sanitize_segment(source_name or "PastedContract")
        root = output_root or (self.cache_root / "manual" / contract_name.lower())
        root.mkdir(parents=True, exist_ok=True)
        source_path = root / f"{contract_name}.sol"
        source_path.write_text(source_text, encoding="utf-8")

        metadata_path = root / ".halyx-acquisition.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "input_kind": "manual_source",
                    "source_name": contract_name,
                    "line_count": len(source_text.splitlines()),
                    "acquisition_report": _build_acquisition_report(
                        mode="manual_source",
                        source_root=root,
                        primary_contract_name=contract_name,
                        contract_count=1,
                        source_reference=source_name or "pasted-source",
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return AcquisitionResult(
            source_root=root,
            input_kind="manual_source",
            primary_contract_name=contract_name,
            contract_count=1,
            metadata_path=metadata_path,
        )

    def acquire_from_scope_url(
        self,
        url: str,
        *,
        chain: str = "ethereum",
        output_root: Path | None = None,
    ) -> AcquisitionResult:
        """Fetch a scope page, extract all Ethereum addresses, pull each from the block explorer."""
        addresses: list[str] = []
        fetched_pages: list[str] = []
        for candidate_url in _scope_url_variants(url):
            try:
                page_text = self._fetch_url_text(candidate_url)
            except SourceAcquisitionError:
                continue
            fetched_pages.append(candidate_url)
            addresses.extend(_ADDRESS_IN_TEXT.findall(page_text))

        # Deduplicate while preserving order; skip the zero address.
        seen: set[str] = set()
        unique_addresses: list[str] = []
        for addr in addresses:
            lower = addr.lower()
            if lower == "0x0000000000000000000000000000000000000000":
                continue
            if lower not in seen:
                seen.add(lower)
                unique_addresses.append(addr)

        if not unique_addresses:
            page_hint = ", ".join(fetched_pages) if fetched_pages else url
            raise SourceAcquisitionError(
                f"no Ethereum contract addresses found on scope page(s): {page_hint}"
            )

        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", urllib.parse.urlparse(url).netloc + urllib.parse.urlparse(url).path).strip("-") or "scope"
        root = output_root or (self.cache_root / _sanitize_segment(chain) / slug)
        root.mkdir(parents=True, exist_ok=True)

        acquired: list[dict[str, object]] = []
        errors: list[str] = []
        total_files = 0
        primary_name = slug

        for address in unique_addresses[:20]:  # cap to avoid runaway API usage
            try:
                result = self.acquire_from_address(address, chain=chain, output_root=root / address.lower())
                total_files += result.contract_count
                if primary_name == slug:
                    primary_name = result.primary_contract_name
                acquired.append({
                    "address": address,
                    "contract_name": result.primary_contract_name,
                    "contract_count": result.contract_count,
                    "source_root": str(result.source_root),
                })
            except SourceAcquisitionError as exc:
                errors.append(f"{address}: {exc}")

        if not acquired:
            detail = "; ".join(errors[:5])
            raise SourceAcquisitionError(
                f"scope page {url} listed {len(unique_addresses)} address(es) but none could be fetched. Errors: {detail}"
            )

        metadata: dict[str, object] = {
            "input_kind": "scope_url",
            "scope_url": url,
            "chain": chain,
            "addresses_found": unique_addresses,
            "acquired": acquired,
            "errors": errors,
            "acquisition_report": _build_acquisition_report(
                mode="scope_url",
                source_root=root,
                primary_contract_name=primary_name,
                contract_count=total_files,
                source_reference=url,
                chain=chain,
                warnings=errors,
            ),
        }
        metadata_path = root / ".halyx-acquisition.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return AcquisitionResult(
            source_root=root,
            input_kind="scope_url",
            primary_contract_name=primary_name,
            contract_count=total_files,
            metadata_path=metadata_path,
        )

    def _fetch_url_text(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Halyx-Source-Agent/1.0"},
        )
        try:
            with self.urlopen(request) as response:
                raw = response.read()
        except (HTTPError, URLError) as exc:
            raise SourceAcquisitionError(f"failed to fetch scope URL {url}: {exc}") from exc
        # Decode leniently; scope pages are usually UTF-8 or latin-1.
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")


    def search_github_repositories(self, protocol_name: str, *, per_page: int = 20) -> list[dict[str, object]]:
        variants = _query_variants(protocol_name)
        queries: list[str] = []
        for variant in variants:
            queries.extend(
                [
                    f"\"{variant}\" in:name",
                    f"{variant} protocol",
                    f"{variant} defi protocol",
                    f"{variant} contracts",
                    f"{variant} onchain",
                ]
            )
        dedup: dict[str, dict[str, object]] = {}
        for query in queries:
            params = urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": str(per_page)})
            payload = self._github_request_json(f"https://api.github.com/search/repositories?{params}")
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                full_name = str(item.get("full_name") or "").strip().lower()
                if full_name:
                    dedup[full_name] = item

        if not dedup:
            raise SourceAcquisitionError(f"no GitHub repositories found for protocol search '{protocol_name}'")
        return list(dedup.values())

    def search_github_owners(self, protocol_name: str, *, per_page: int = 10) -> list[str]:
        variants = _query_variants(protocol_name)
        queries: list[str] = []
        for variant in variants:
            queries.extend([f"{variant} type:org", f"{variant} type:user"])
        owners: list[str] = []
        for query in queries:
            params = urllib.parse.urlencode({"q": query, "per_page": str(per_page)})
            payload = self._github_request_json(f"https://api.github.com/search/users?{params}")
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                login = str(item.get("login") or "").strip()
                if not login:
                    continue
                owners.append(login)
        deduped: list[str] = []
        seen: set[str] = set()
        for owner in owners:
            lower_owner = owner.lower()
            if lower_owner in seen:
                continue
            deduped.append(owner)
            seen.add(lower_owner)
        return deduped

    def list_owner_repositories(self, owner: str, *, per_page: int = 50) -> list[dict[str, object]]:
        payload = self._github_request_json(
            f"https://api.github.com/users/{owner}/repos?sort=updated&per_page={per_page}&type=public"
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _github_request_json(self, url: str) -> object:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                **({"Authorization": f"Bearer {self.github_token}"} if self.github_token else {}),
            },
        )
        with self.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def _repository_structure_score(self, full_name: str) -> float:
        try:
            payload = self._github_request_json(f"https://api.github.com/repos/{full_name}/contents")
        except (HTTPError, URLError, json.JSONDecodeError):
            return -20.0
        if not isinstance(payload, list):
            return -20.0

        entries = [item for item in payload if isinstance(item, dict)]
        names = {str(item.get("name") or "").lower() for item in entries}
        dirs = {
            str(item.get("name") or "").lower()
            for item in entries
            if str(item.get("type") or "") == "dir"
        }

        score = 0.0
        has_contract_dir = bool({"contracts", "src", "programs", "packages"} & dirs)
        has_contract_config = bool(
            {
                "foundry.toml",
                "hardhat.config.ts",
                "hardhat.config.js",
                "truffle-config.js",
                "brownie-config.yaml",
                "remappings.txt",
                "anchor.toml",
                "cargo.toml",
                "move.toml",
                "scarb.toml",
            }
            & names
        )

        if has_contract_dir:
            score += 35.0
        if has_contract_config:
            score += 25.0
        if "package.json" in names:
            score += 8.0
        if "readme.md" in names:
            score += 4.0
        if not has_contract_dir and not has_contract_config:
            score -= 35.0

        return score

    @staticmethod
    def _candidate_token_overlap(candidate: dict[str, object], protocol_name: str) -> int:
        query_tokens = set(_tokenize(protocol_name))
        full_name = str(candidate.get("full_name") or "")
        name_tokens = set(_tokenize(full_name))
        description_tokens = set(_tokenize(str(candidate.get("description") or "")))
        return len(query_tokens & (name_tokens | description_tokens))

    def _passes_strict_candidate_gate(self, candidate: dict[str, object], *, protocol_name: str, structure_score: float) -> bool:
        language = str(candidate.get("language") or "")
        archived = bool(candidate.get("archived"))
        fork = bool(candidate.get("fork"))
        token_overlap = self._candidate_token_overlap(candidate, protocol_name)
        stars = int(candidate.get("stargazers_count") or 0)
        full_name = str(candidate.get("full_name") or "")
        owner_segment = full_name.split("/")[0] if "/" in full_name else full_name
        query_tokens = set(_tokenize(protocol_name))
        owner_overlap = len(query_tokens & set(_tokenize(owner_segment)))

        full_name = str(candidate.get("full_name") or "")
        normalized_query = " ".join(_tokenize(protocol_name))
        exact_slug_match = normalized_query and normalized_query in " ".join(_tokenize(full_name))
        low_signal_overlap = len(LOW_SIGNAL_KEYWORDS & set(_tokenize(str(candidate.get("description") or ""))))

        if archived or fork:
            return False
        if structure_score < 0:
            return False
        if token_overlap <= 0 and not exact_slug_match:
            return False
        if owner_overlap <= 0 and stars < 20:
            return False
        if low_signal_overlap >= 2 and owner_overlap <= 0 and stars < 100:
            return False
        return True

    def acquire_from_protocol_name(self, protocol_name: str, *, output_root: Path | None = None) -> AcquisitionResult:
        candidates = self.search_github_repositories(protocol_name)
        scored_candidates: list[dict[str, object]] = []
        for candidate in candidates:
            full_name = str(candidate.get("full_name") or "").strip()
            if not full_name:
                continue
            structure_score = self._repository_structure_score(full_name)
            base_score = self._score_repository_candidate(candidate, protocol_name)
            combined_score = base_score + structure_score
            enriched = dict(candidate)
            enriched["_structure_score"] = structure_score
            enriched["_base_score"] = base_score
            enriched["_combined_score"] = combined_score
            if self._passes_strict_candidate_gate(enriched, protocol_name=protocol_name, structure_score=structure_score):
                scored_candidates.append(enriched)

        ranked = sorted(scored_candidates, key=lambda item: float(item.get("_combined_score") or 0.0), reverse=True)

        if not ranked:
            owner_candidates = self.search_github_owners(protocol_name)
            expanded_candidates: list[dict[str, object]] = []
            for owner in owner_candidates:
                expanded_candidates.extend(self.list_owner_repositories(owner))

            dedup: dict[str, dict[str, object]] = {}
            for candidate in expanded_candidates:
                full_name = str(candidate.get("full_name") or "").strip().lower()
                if full_name:
                    dedup[full_name] = candidate

            rescored: list[dict[str, object]] = []
            for candidate in dedup.values():
                full_name = str(candidate.get("full_name") or "").strip()
                if not full_name:
                    continue
                structure_score = self._repository_structure_score(full_name)
                base_score = self._score_repository_candidate(candidate, protocol_name)
                combined_score = base_score + structure_score
                enriched = dict(candidate)
                enriched["_structure_score"] = structure_score
                enriched["_base_score"] = base_score
                enriched["_combined_score"] = combined_score
                if self._passes_strict_candidate_gate(enriched, protocol_name=protocol_name, structure_score=structure_score):
                    rescored.append(enriched)
            ranked = sorted(rescored, key=lambda item: float(item.get("_combined_score") or 0.0), reverse=True)

        best = ranked[0] if ranked else None
        if not best:
            short_list = ", ".join(str(candidate.get("full_name") or "?") for candidate in candidates[:5])
            raise SourceAcquisitionError(
                f"unable to identify a strict protocol repository for '{protocol_name}'. "
                f"Top search candidates were: {short_list}"
            )

        full_name = str(best.get("full_name") or "").strip()
        if not full_name:
            raise SourceAcquisitionError(f"best GitHub candidate for '{protocol_name}' did not include full_name")

        result = self.acquire_from_github(full_name, output_root=output_root)
        existing_metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        existing_metadata["input_kind"] = "protocol_name"
        existing_metadata["protocol_name"] = protocol_name
        existing_metadata["selected_repository"] = {
            "full_name": best.get("full_name"),
            "html_url": best.get("html_url"),
            "description": best.get("description"),
            "stargazers_count": best.get("stargazers_count"),
            "archived": best.get("archived"),
            "fork": best.get("fork"),
            "language": best.get("language"),
            "base_score": best.get("_base_score"),
            "structure_score": best.get("_structure_score"),
            "score": best.get("_combined_score"),
        }
        existing_metadata["candidate_repositories"] = [
            {
                "full_name": candidate.get("full_name"),
                "html_url": candidate.get("html_url"),
                "description": candidate.get("description"),
                "stargazers_count": candidate.get("stargazers_count"),
                "base_score": candidate.get("_base_score"),
                "structure_score": candidate.get("_structure_score"),
                "score": candidate.get("_combined_score"),
            }
            for candidate in ranked[:5]
        ]
        existing_metadata["acquisition_report"] = _build_acquisition_report(
            mode="protocol_name",
            source_root=result.source_root,
            primary_contract_name=result.primary_contract_name,
            contract_count=result.contract_count,
            source_reference=protocol_name,
        )
        result.metadata_path.write_text(json.dumps(existing_metadata, indent=2), encoding="utf-8")
        return result

    def acquire_from_address(self, address: str, *, chain: str = "ethereum", output_root: Path | None = None) -> AcquisitionResult:
        root = output_root or (self.cache_root / _sanitize_segment(chain) / address.lower())
        root.mkdir(parents=True, exist_ok=True)

        proxy_metadata = self.etherscan.get_contract_metadata(address, chain)
        source_code = str(proxy_metadata.get("SourceCode") or "")
        proxy_sources = _parse_source_files(source_code, str(proxy_metadata.get("ContractName") or "Contract"))

        proxy_chain: list[ProxyResolution] = []
        implementation_address = str(proxy_metadata.get("Implementation") or "").strip()
        is_proxy = _is_proxy_record(proxy_metadata) and is_contract_address(implementation_address)

        if is_proxy:
            proxy_chain.append(ProxyResolution(proxy_address=address, implementation_address=implementation_address))
            _write_sources(root / "proxy", proxy_sources)
            implementation_metadata = self.etherscan.get_contract_metadata(implementation_address, chain)
            implementation_sources = _parse_source_files(
                str(implementation_metadata["SourceCode"]),
                str(implementation_metadata.get("ContractName") or "Implementation"),
            )
            contract_count = _write_sources(root / "implementation", implementation_sources) + len(proxy_sources)
            primary_contract_name = str(implementation_metadata.get("ContractName") or proxy_metadata.get("ContractName") or "Contract")
            persisted_metadata = {
                "input_kind": "contract_address",
                "chain": chain,
                "address": address,
                "proxy": proxy_metadata,
                "implementation": implementation_metadata,
                "proxy_chain": [asdict(resolution) for resolution in proxy_chain],
                "acquisition_report": _build_acquisition_report(
                    mode="contract_address",
                    source_root=root,
                    primary_contract_name=primary_contract_name,
                    contract_count=contract_count,
                    source_reference=address,
                    chain=chain,
                ),
            }
        else:
            contract_count = _write_sources(root, proxy_sources)
            primary_contract_name = str(proxy_metadata.get("ContractName") or "Contract")
            persisted_metadata = {
                "input_kind": "contract_address",
                "chain": chain,
                "address": address,
                "contract": proxy_metadata,
                "proxy_chain": [],
                "acquisition_report": _build_acquisition_report(
                    mode="contract_address",
                    source_root=root,
                    primary_contract_name=primary_contract_name,
                    contract_count=contract_count,
                    source_reference=address,
                    chain=chain,
                ),
            }

        abi_payload = proxy_metadata.get("ABI", "[]")
        (root / f"{primary_contract_name}.abi.json").write_text(str(abi_payload), encoding="utf-8")
        metadata_path = root / ".halyx-acquisition.json"
        metadata_path.write_text(json.dumps(persisted_metadata, indent=2), encoding="utf-8")

        return AcquisitionResult(
            source_root=root,
            input_kind="contract_address",
            primary_contract_name=primary_contract_name,
            contract_count=contract_count,
            metadata_path=metadata_path,
            proxy_chain=proxy_chain,
        )

    def acquire_from_github(self, reference: str, *, output_root: Path | None = None) -> AcquisitionResult:
        repository_url, repo_slug = self._normalize_github_reference(reference)
        root = output_root or (self.cache_root / "github" / _sanitize_segment(repo_slug))

        if not (root.exists() and any(root.iterdir())):
            root.parent.mkdir(parents=True, exist_ok=True)
            completed = self.command_runner(
                ["git", "clone", "--depth", "1", repository_url, str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            if getattr(completed, "returncode", 1) != 0:
                stderr = getattr(completed, "stderr", "")
                raise SourceAcquisitionError(f"git clone failed for {repository_url}: {stderr.strip()}")

        metadata_path = root / ".halyx-acquisition.json"
        contract_count = len(list(root.rglob("*.sol")))
        metadata_path.write_text(
            json.dumps(
                {
                    "input_kind": "github",
                    "reference": reference,
                    "repository_url": repository_url,
                    "repo_slug": repo_slug,
                    "acquisition_report": _build_acquisition_report(
                        mode="github",
                        source_root=root,
                        primary_contract_name=repo_slug.split("/")[-1],
                        contract_count=contract_count,
                        source_reference=reference,
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return AcquisitionResult(
            source_root=root,
            input_kind="github",
            primary_contract_name=repo_slug.split("/")[-1],
            contract_count=contract_count,
            metadata_path=metadata_path,
        )

    def acquire_from_git(self, reference: str, *, output_root: Path | None = None) -> AcquisitionResult:
        repo_slug = self._normalize_generic_git_slug(reference)
        root = output_root or (self.cache_root / "git" / _sanitize_segment(repo_slug))

        if not (root.exists() and any(root.iterdir())):
            root.parent.mkdir(parents=True, exist_ok=True)
            completed = self.command_runner(
                ["git", "clone", "--depth", "1", reference, str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            if getattr(completed, "returncode", 1) != 0:
                stderr = getattr(completed, "stderr", "")
                raise SourceAcquisitionError(f"git clone failed for {reference}: {stderr.strip()}")

        metadata_path = root / ".halyx-acquisition.json"
        contract_count = len(list(root.rglob("*.sol")))
        metadata_path.write_text(
            json.dumps(
                {
                    "input_kind": "git",
                    "reference": reference,
                    "repo_slug": repo_slug,
                    "acquisition_report": _build_acquisition_report(
                        mode="git",
                        source_root=root,
                        primary_contract_name=repo_slug.split("/")[-1],
                        contract_count=contract_count,
                        source_reference=reference,
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return AcquisitionResult(
            source_root=root,
            input_kind="git",
            primary_contract_name=repo_slug.split("/")[-1],
            contract_count=contract_count,
            metadata_path=metadata_path,
        )

    @staticmethod
    def _score_repository_candidate(candidate: dict[str, object], protocol_name: str) -> float:
        query_tokens = set(_tokenize(protocol_name))
        full_name = str(candidate.get("full_name") or "")
        owner_segment = full_name.split("/")[0] if "/" in full_name else full_name
        repo_segment = full_name.split("/")[1] if "/" in full_name else full_name
        name_tokens = set(_tokenize(full_name))
        owner_tokens = set(_tokenize(owner_segment))
        repo_tokens = set(_tokenize(repo_segment))
        description_tokens = set(_tokenize(str(candidate.get("description") or "")))
        topics = {str(topic).lower() for topic in candidate.get("topics", []) if isinstance(topic, str)}

        stars = int(candidate.get("stargazers_count") or 0)
        language = str(candidate.get("language") or "")
        archived = bool(candidate.get("archived"))
        fork = bool(candidate.get("fork"))

        token_overlap = len(query_tokens & (name_tokens | description_tokens))
        owner_overlap = len(query_tokens & owner_tokens)
        exact_slug_match = " ".join(_tokenize(protocol_name)) in " ".join(_tokenize(full_name))
        keyword_overlap = len(PROTOCOL_KEYWORDS & (description_tokens | topics | name_tokens))
        low_signal_overlap = len(LOW_SIGNAL_KEYWORDS & description_tokens)

        score = 0.0
        score += token_overlap * 20.0
        score += owner_overlap * 18.0
        score += 35.0 if exact_slug_match else 0.0
        score += 12.0 if language.lower() in CODE_SIGNAL_LANGUAGES else 0.0
        score += min(math.log10(stars + 1) * 8.0, 28.0)
        score += min(keyword_overlap * 3.0, 15.0)
        score += 8.0 if not archived else -15.0
        score += 8.0 if not fork else -8.0
        score += 18.0 if "contracts" in repo_tokens else 0.0
        score += 12.0 if "core" in repo_tokens else 0.0
        score += 10.0 if "protocol" in repo_tokens else 0.0
        score -= 12.0 if "token" in repo_tokens and "contracts" not in repo_tokens else 0.0
        score -= 8.0 if "bot" in repo_tokens else 0.0
        score -= 6.0 if "integration" in repo_tokens else 0.0
        score -= min(low_signal_overlap * 12.0, 30.0)
        return score

    @staticmethod
    def _normalize_github_reference(reference: str) -> tuple[str, str]:
        stripped = reference.strip()
        if stripped.startswith("git@github.com:"):
            slug = stripped.removeprefix("git@github.com:").removesuffix(".git")
            return stripped if stripped.endswith(".git") else f"{stripped}.git", slug
        if stripped.startswith("https://github.com/"):
            slug = stripped.removeprefix("https://github.com/").removesuffix(".git").strip("/")
            return f"https://github.com/{slug}.git", slug
        slug = stripped.removesuffix(".git")
        return f"https://github.com/{slug}.git", slug

    @staticmethod
    def _normalize_generic_git_slug(reference: str) -> str:
        stripped = reference.strip()
        if stripped.startswith("git@") and ":" in stripped:
            host, path = stripped.split(":", 1)
            return f"{host.removeprefix('git@')}/{path.removesuffix('.git').strip('/')}"
        if stripped.startswith("http://") or stripped.startswith("https://"):
            parsed = urllib.parse.urlparse(stripped)
            path = parsed.path.removesuffix(".git").strip("/")
            return f"{parsed.netloc}/{path}" if path else parsed.netloc
        return _sanitize_segment(stripped.removesuffix(".git"))