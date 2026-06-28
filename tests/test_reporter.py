import json
from pathlib import Path

SCORED_FIXTURE = [
    {
        "summary": {"property_id": "a1", "title": "Great Flat", "rent": 35000, "deposit": 100000,
            "maintenance": 3000, "sqft": 1100, "address": "Test Rd", "locality": "kadubeesanahalli",
            "building_name": "SLS", "detail_url": "https://nobroker.in/a1", "available_date": None, "image_urls": []},
        "detail": {"property_id": "a1", "furnishing": "Semi", "floor": "3/5", "power_backup": "Full",
            "facing": "West", "bathrooms": 2, "balconies": 1, "parking": "Car", "building_age": "1-3 Years",
            "preferred_tenant": "Family", "water_supply": "Corporation", "gated_security": True,
            "description": "Nice flat"},
        "lat": 12.94, "lon": 77.69, "walk_minutes": 8.0, "orr_distance_m": 400,
        "peace_score": 70.0, "llm_score": 88.0,
        "final_score": 80.8, "disqualified": False, "disqualify_reason": None,
        "criteria_scores": {
            "power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Full generator"},
            "noise": {"score": 16, "max": 20, "confidence": "medium", "evidence": "3rd floor"},
            "internet": {"score": 12, "max": 15, "confidence": "low", "evidence": "No mention"},
            "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "West facing"},
            "water": {"score": 9, "max": 10, "confidence": "high", "evidence": "Corporation supply"},
            "maintenance": {"score": 9, "max": 10, "confidence": "high", "evidence": "Gated"},
            "wfh_livability": {"score": 8, "max": 10, "confidence": "medium", "evidence": "Semi furnished"},
            "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "Reasonable"},
        },
        "pros": ["Full generator backup", "Gated community", "Good water supply"],
        "cons": ["No fiber internet mentioned", "Semi-furnished only"],
        "elevator_pitch": "Quiet gated apartment with full generator, 8min walk to PTP",
        "data_completeness": 0.85,
        "peace_breakdown": {"orr_distance_m": 400, "base_score": 60, "locality_bonus": 20, "final": 70},
        "comparative_rank": 1, "comparative_notes": "Best overall",
        "duplicate_of": None,
    },
    {
        "summary": {"property_id": "b2", "title": "OK Flat", "rent": 25000, "deposit": 75000,
            "maintenance": None, "sqft": 900, "address": "Other Rd", "locality": "bellandur",
            "building_name": None, "detail_url": "https://nobroker.in/b2", "available_date": None, "image_urls": []},
        "detail": {"property_id": "b2", "furnishing": "Unfurnished", "floor": "1/3", "power_backup": None,
            "facing": None, "bathrooms": 1, "balconies": 0, "parking": None, "building_age": None,
            "preferred_tenant": None, "water_supply": "Borewell", "gated_security": False,
            "description": "Basic flat"},
        "lat": 12.93, "lon": 77.68, "walk_minutes": 11.0, "orr_distance_m": 250,
        "peace_score": 35.0, "llm_score": 40.0,
        "final_score": 38.0, "disqualified": True, "disqualify_reason": "No power backup",
        "criteria_scores": {
            "power_backup": {"score": 0, "max": 20, "confidence": "high", "evidence": "Not mentioned"},
            "noise": {"score": 6, "max": 20, "confidence": "low", "evidence": "Ground floor"},
            "internet": {"score": 5, "max": 15, "confidence": "low", "evidence": "No info"},
            "light_ventilation": {"score": 4, "max": 10, "confidence": "low", "evidence": "No info"},
            "water": {"score": 5, "max": 10, "confidence": "medium", "evidence": "Borewell only"},
            "maintenance": {"score": 3, "max": 10, "confidence": "medium", "evidence": "Not gated"},
            "wfh_livability": {"score": 4, "max": 10, "confidence": "low", "evidence": "Unfurnished"},
            "value": {"score": 3, "max": 5, "confidence": "medium", "evidence": "Cheap but basic"},
        },
        "pros": ["Low rent"],
        "cons": ["No power backup", "Not gated", "Unfurnished", "Borewell only"],
        "elevator_pitch": "Budget flat, but no power backup — disqualified",
        "data_completeness": 0.35,
        "peace_breakdown": {"orr_distance_m": 250, "base_score": 37.5, "locality_bonus": 0, "final": 35},
        "comparative_rank": None, "comparative_notes": None,
        "duplicate_of": None,
    },
]


def test_generate_report(tmp_path):
    from src.reporter import generate_report
    from src.config import Config, RunContext
    import json

    cfg = Config(
        name="default", target_localities=["kadubeesanahalli"], ptp_coords=(12.942, 77.6905),
        max_walk_minutes=12, min_orr_distance_m=200, max_rent=50000, score_threshold=85,
        bhk=2, score_weights={"peace": 0.4, "llm": 0.6},
        llm_weights={"power_backup": 20, "noise": 20, "internet": 15, "light_ventilation": 10,
            "water": 10, "maintenance": 10, "wfh_livability": 10, "value": 5}
    )
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    (run_dir / "scored.json").write_text(json.dumps(SCORED_FIXTURE))
    (run_dir / "config.json").write_text(cfg.model_dump_json())
    ctx = RunContext(run_id="test", run_dir=run_dir, config=cfg)

    html_path = generate_report(ctx)
    assert html_path.exists()
    html = html_path.read_text()
    assert "Great Flat" in html
    assert "80.8" in html
    assert "elevator_pitch" in html or "elevator-pitch" in html or "Quiet gated apartment" in html
    assert "criteria" in html.lower() or "power_backup" in html
    md = (run_dir / "report.md").read_text()
    assert "Great Flat" in md
    assert "Full generator" in md  # pros
    assert "No fiber" in md  # cons


def test_compare_runs(tmp_path):
    from src.reporter import compare_runs

    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()
    (run_a / "config.json").write_text(json.dumps({"name": "default", "min_orr_distance_m": 200}))
    (run_b / "config.json").write_text(json.dumps({"name": "peaceful", "min_orr_distance_m": 300}))
    (run_a / "scored.json").write_text(json.dumps(SCORED_FIXTURE))
    (run_b / "scored.json").write_text(json.dumps([SCORED_FIXTURE[0]]))

    diff = compare_runs(run_a, run_b)
    assert "a1" in diff  # shared listing
    assert "b2" in diff  # only in run A
    assert "config" in diff.lower() or "min_orr" in diff.lower()
