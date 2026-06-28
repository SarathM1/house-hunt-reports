import json


def test_build_structured_judge_prompt():
    from src.scorer import build_structured_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_structured_judge_prompt(
        summary={"title": "2BHK Test", "rent": 30000, "address": "Test Rd", "sqft": 1000},
        detail={"furnishing": "Semi", "power_backup": "Full", "floor": "3/4",
                "water_supply": "Borewell", "gated_security": True, "description": "Nice flat"},
        walk_minutes=8.5,
        orr_distance_m=350,
        data_completeness=0.85,
        llm_weights=weights,
    )
    assert "criteria_scores" in prompt
    assert "pros" in prompt
    assert "cons" in prompt
    assert "elevator_pitch" in prompt
    assert "confidence" in prompt
    assert "evidence" in prompt
    assert "HARD REQUIREMENT" in prompt
    assert "data_completeness" in prompt.lower() or "0.85" in prompt


def test_structured_prompt_includes_all_criteria():
    from src.scorer import build_structured_judge_prompt
    weights = {
        "power_backup": 20, "noise": 20, "internet": 15,
        "light_ventilation": 10, "water": 10, "maintenance": 10,
        "wfh_livability": 10, "value": 5
    }
    prompt = build_structured_judge_prompt(
        summary={"title": "Test", "rent": 40000, "address": "Addr", "sqft": 1200},
        detail={"furnishing": "Fully", "power_backup": None, "floor": "2/5",
                "water_supply": "Corporation", "gated_security": False, "description": "Flat"},
        walk_minutes=10, orr_distance_m=500, data_completeness=0.6, llm_weights=weights,
    )
    for criterion in weights:
        assert criterion in prompt


def test_parse_structured_score_valid():
    from src.scorer import parse_structured_score
    weights = {"power_backup": 20, "noise": 20, "internet": 15,
               "light_ventilation": 10, "water": 10, "maintenance": 10,
               "wfh_livability": 10, "value": 5}
    raw = '''{
        "criteria_scores": {
            "power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Full gen"},
            "noise": {"score": 14, "max": 20, "confidence": "medium", "evidence": "3rd floor"},
            "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "No mention"},
            "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "East"},
            "water": {"score": 7, "max": 10, "confidence": "high", "evidence": "Corp+bore"},
            "maintenance": {"score": 8, "max": 10, "confidence": "high", "evidence": "Gated"},
            "wfh_livability": {"score": 7, "max": 10, "confidence": "medium", "evidence": "Semi"},
            "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "28/sqft"}
        },
        "pros": ["Full generator", "Gated community"],
        "cons": ["No fiber mentioned"],
        "elevator_pitch": "Quiet gated flat with generator",
        "disqualified": false,
        "disqualify_reason": null
    }'''
    result = parse_structured_score(raw, weights)
    assert result["criteria_scores"]["power_backup"]["score"] == 18
    assert len(result["pros"]) == 2
    assert result["disqualified"] is False


def test_parse_structured_score_with_markdown_fences():
    from src.scorer import parse_structured_score
    weights = {"power_backup": 20, "noise": 20, "internet": 15,
               "light_ventilation": 10, "water": 10, "maintenance": 10,
               "wfh_livability": 10, "value": 5}
    raw = '```json\n{"criteria_scores": {"power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Gen"}, "noise": {"score": 14, "max": 20, "confidence": "medium", "evidence": "OK"}, "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "?"}, "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "OK"}, "water": {"score": 7, "max": 10, "confidence": "high", "evidence": "OK"}, "maintenance": {"score": 8, "max": 10, "confidence": "high", "evidence": "OK"}, "wfh_livability": {"score": 7, "max": 10, "confidence": "medium", "evidence": "OK"}, "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "OK"}}, "pros": ["A"], "cons": ["B"], "elevator_pitch": "OK flat", "disqualified": false, "disqualify_reason": null}\n```'
    result = parse_structured_score(raw, weights)
    assert result["criteria_scores"]["power_backup"]["score"] == 18


def test_parse_structured_score_invalid():
    from src.scorer import parse_structured_score
    import pytest
    weights = {"power_backup": 20}
    with pytest.raises(ValueError):
        parse_structured_score("not json at all", weights)
