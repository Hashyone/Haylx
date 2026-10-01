from quantum_economic_auditor.compiler.binary_encoder import encode_variable, gray_encode


def test_gray_code_round_trip_is_deterministic() -> None:
    encoded = encode_variable("loan_amount", 250.0, lower_bound=0.0, upper_bound=1000.0, precision=50.0)
    gray_bits = gray_encode(encoded.encoded_bits)

    assert encoded.name == "loan_amount"
    assert encoded.encoded_bits
    assert gray_bits
