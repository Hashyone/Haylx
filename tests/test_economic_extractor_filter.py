from quantum_economic_auditor.agents.economic_extractor import StaticEconomicExtractor
from quantum_economic_auditor.parser.repository_loader import load_repository


def test_extractor_filters_implementation_variables_out_of_the_economic_model() -> None:
    repository = load_repository("olympus-v3")
    protocol_spec = StaticEconomicExtractor().extract(repository)

    leaked_names = {"target", "funcSelector", "i", "j", "slot", "selector"}
    assert leaked_names.isdisjoint(set(protocol_spec.state_variables))
    assert leaked_names.isdisjoint(set(protocol_spec.economic_variables))

    economic_keywords = {"backing", "premium", "capacity", "supply", "liquidity", "debt", "oracle", "treasury"}
    assert economic_keywords.intersection(set(protocol_spec.economic_variables))
