from rpf_validator.contract import contract_for_stamp, load_contract


def test_snapshot_pin_and_required_tables():
    contract = load_contract()
    assert contract["source_commit"] == "0d4d48f"
    assert contract["supported_versions"] == ["v0.14.5", "0.14.5"]
    assert len(contract["canonical_tables"]) == 18
    assert contract["required_tables"][-1] == "dc_converters"
    assert len(contract["required_tables"]) == 19
    assert "hour_ahead_advisory" in contract["case_modes"]
    assert "hour_ahead_advisory" in contract["planning_case_modes"]


def test_registry_selects_only_the_current_stamp():
    assert contract_for_stamp("v0.14.5")["snapshot"] == "v0.14.5"
    assert contract_for_stamp("0.14.5")["snapshot"] == "v0.14.5"
    assert contract_for_stamp("v0.14.4") is None
