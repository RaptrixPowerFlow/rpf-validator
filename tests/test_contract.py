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


def test_registry_selects_v0145_and_v0146():
    from rpf_validator.contract import load_contract

    current = load_contract("v0.14.6")
    assert current["snapshot"] == "v0.14.6"
    assert current["supported_versions"] == ["v0.14.6", "0.14.6"]
    assert current["known_envelope_presets"] == [
        "nerc_prc_029_2026",
        "pjm_att_d2_2026",
        "ercot_nogrr_282_2026",
        "wecc_llb_2026",
    ]
    names = [field["name"] for field in current["tables"]["computational_load_profiles"][0]["fields"]]
    assert names[-8:] == [
        "it_pe_fraction",
        "cooling_fraction",
        "cooling_trip_v_pu",
        "multi_sag_count",
        "multi_sag_window_s",
        "envelope_preset",
        "model_verified_unix",
        "qualified_change_pending",
    ]
    assert contract_for_stamp("v0.14.6")["snapshot"] == "v0.14.6"
    assert contract_for_stamp("0.14.6")["snapshot"] == "v0.14.6"
    assert contract_for_stamp("v0.14.5")["snapshot"] == "v0.14.5"
    assert contract_for_stamp("0.14.5")["snapshot"] == "v0.14.5"
    assert contract_for_stamp("v0.14.5")["source_commit"] == "0d4d48f"
    assert contract_for_stamp("v0.14.4") is None
