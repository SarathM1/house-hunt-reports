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
        "peace_score": 70.0, "llm_score": 88.0, "llm_reasoning": "Good backup, quiet area",
        "final_score": 80.8, "disqualified": False, "disqualify_reason": None,
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
        "peace_score": 35.0, "llm_score": 40.0, "llm_reasoning": "No backup mentioned",
        "final_score": 38.0, "disqualified": True, "disqualify_reason": "No power backup",
    },
]


def test_generate_report(tmp_path):
    from src.reporter import generate_report
    from src.config import Config, RunContext

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
    assert html_path.suffix == ".html"
    html = html_path.read_text()
    assert "Great Flat" in html
    assert "80.8" in html
    assert "nobroker.in/a1" in html
    md = (run_dir / "report.md").read_text()
    assert "Great Flat" in md
    assert "80.8" in md


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
