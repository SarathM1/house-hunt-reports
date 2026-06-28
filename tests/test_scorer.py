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


def test_build_comparative_prompt():
    from src.scorer import build_comparative_prompt
    listings = [
        {"summary": {"property_id": "a1", "title": "Flat A", "rent": 30000, "sqft": 1000},
         "llm_score": 82, "peace_score": 70, "final_score": 75,
         "criteria_scores": {"power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Gen"}},
         "pros": ["Good backup"], "cons": ["No fiber"], "disqualified": False},
        {"summary": {"property_id": "b2", "title": "Flat B", "rent": 25000, "sqft": 900},
         "llm_score": 75, "peace_score": 80, "final_score": 78,
         "criteria_scores": {"power_backup": {"score": 15, "max": 20, "confidence": "medium", "evidence": "Partial"}},
         "pros": ["Quiet area"], "cons": ["Smaller"], "disqualified": False},
    ]
    prompt = build_comparative_prompt(listings)
    assert "a1" in prompt
    assert "b2" in prompt
    assert "rank" in prompt.lower()
    assert "top_3_summary" in prompt


def test_parse_comparative_result_valid():
    from src.scorer import parse_comparative_result
    raw = '{"rankings": [{"property_id": "a1", "rank": 1, "reasoning": "Best overall"}, {"property_id": "b2", "rank": 2, "reasoning": "Quieter"}], "top_3_summary": "#1 Flat A — best. #2 Flat B — quieter."}'
    result = parse_comparative_result(raw)
    assert len(result.rankings) == 2
    assert result.rankings[0].rank == 1
    assert result.top_3_summary.startswith("#1")


def test_parse_comparative_result_invalid():
    from src.scorer import parse_comparative_result
    import pytest
    with pytest.raises(ValueError):
        parse_comparative_result("not json")


def test_normalize_building_name():
    from src.scorer import normalize_building_name
    assert normalize_building_name("SLS Signature") == "sls signature"
    assert normalize_building_name("  SLS  Signature  ") == "sls signature"
    assert normalize_building_name("SLS-Signature (Phase 2)") == "sls signature phase 2"


def test_find_dupe_groups():
    from src.scorer import find_dupe_groups
    scored = [
        {"summary": {"property_id": "a1", "building_name": "SLS Signature"}, "final_score": 80},
        {"summary": {"property_id": "a2", "building_name": "SLS Signature"}, "final_score": 75},
        {"summary": {"property_id": "b1", "building_name": "Brigade Lakefront"}, "final_score": 70},
    ]
    groups = find_dupe_groups(scored)
    assert len(groups) == 1
    assert set(groups[0]) == {0, 1}


def test_find_dupe_groups_contains_match():
    from src.scorer import find_dupe_groups
    scored = [
        {"summary": {"property_id": "a1", "building_name": "SLS Signature Tower A"}, "final_score": 80},
        {"summary": {"property_id": "a2", "building_name": "SLS Signature"}, "final_score": 75},
    ]
    groups = find_dupe_groups(scored)
    assert len(groups) == 1


def test_find_dupe_groups_no_building_name():
    from src.scorer import find_dupe_groups
    scored = [
        {"summary": {"property_id": "a1", "building_name": None}, "final_score": 80},
        {"summary": {"property_id": "a2", "building_name": None}, "final_score": 75},
    ]
    groups = find_dupe_groups(scored)
    assert len(groups) == 0
