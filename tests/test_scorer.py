import json


def test_build_judge_prompt():
    from src.scorer import build_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_judge_prompt(
        summary={"title": "2BHK Test", "rent": 30000, "address": "Test Rd", "sqft": 1000},
        detail={"furnishing": "Semi", "power_backup": "Full", "floor": "3/4",
                "water_supply": "Borewell", "gated_security": True, "description": "Nice flat"},
        walk_minutes=8.5,
        orr_distance_m=350,
        llm_weights=weights,
    )
    assert "20 points" in prompt  # power_backup weight
    assert "15 points" in prompt  # internet weight
    assert "₹30,000" in prompt or "30000" in prompt
    assert "Semi" in prompt
    assert "Full" in prompt  # power backup value
    assert "HARD REQUIREMENT" in prompt
    assert "disqualified" in prompt.lower() or "disqualify" in prompt.lower()


def test_prompt_includes_all_criteria():
    from src.scorer import build_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_judge_prompt(
        summary={"title": "Test", "rent": 40000, "address": "Addr", "sqft": 1200},
        detail={"furnishing": "Fully", "power_backup": None, "floor": "2/5",
                "water_supply": "Corporation", "gated_security": False, "description": "Flat"},
        walk_minutes=10, orr_distance_m=500, llm_weights=weights,
    )
    for criterion in ["power_backup", "noise", "internet", "water", "maintenance"]:
        assert criterion.replace("_", " ") in prompt.lower() or criterion in prompt.lower()
