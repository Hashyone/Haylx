from pathlib import Path

from quantum_economic_auditor.parser.repository_loader import load_repository


def test_repository_loader_filters_vendor_and_test_sources() -> None:
    repository = load_repository("olympus-v3")

    relpaths = [path.relative_to(repository.root).as_posix() for path in repository.contract_files]

    assert any(relpath.startswith("src/") for relpath in relpaths)
    assert all("/dependencies/" not in relpath for relpath in relpaths)
    assert all("/test/" not in relpath for relpath in relpaths)
    assert all(not relpath.startswith("dependencies/") for relpath in relpaths)
