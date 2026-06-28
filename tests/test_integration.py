import asyncio
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from tests.test_scraper import SAMPLE_SEO_MARKDOWN, SAMPLE_DETAIL_MARKDOWN


def test_full_pipeline_mocked(tmp_path):
    """Smoke test: config → scrape (mocked) → filter (mocked) → score (mocked) → report."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default_config = {
        "name": "default",
        "target_localities": ["kadubeesanahalli"],
        "ptp_coords": [12.9420, 77.6905],
        "max_walk_minutes": 12,
        "min_orr_distance_m": 200,
        "max_rent": 50000,
        "score_threshold": 85,
        "bhk": 2,
        "score_weights": {"peace": 0.4, "llm": 0.6},
        "llm_weights": {
            "power_backup": 20, "noise": 20, "internet": 15,
            "light_ventilation": 10, "water": 10, "maintenance": 10,
            "wfh_livability": 10, "value": 5
        }
    }
    (configs_dir / "default.json").write_text(json.dumps(default_config))

    from src.config import load_config, create_run
    cfg = load_config("default", configs_dir=configs_dir)
    data_dir = tmp_path / "data" / "runs"
    ctx = create_run(cfg, data_dir=data_dir)

    # Mock scrape
    with patch("src.scraper.scrape_seo_page", return_value=SAMPLE_SEO_MARKDOWN), \
         patch("src.scraper.scrape_detail_page", return_value=SAMPLE_DETAIL_MARKDOWN), \
         patch("src.scraper.Dedup") as MockDedup:
        MockDedup.return_value.is_seen.return_value = False
        MockDedup.return_value.mark_seen.return_value = None
        from src.scraper import run_scrape
        run_scrape(ctx)

    raw = json.loads(ctx.path("raw.json").read_text())
    assert len(raw) >= 1
    assert raw[0]["summary"]["property_id"]

    # Mock filter — just copy raw to filtered with spatial fields
    filtered = []
    for entry in raw:
        entry["lat"] = 12.94
        entry["lon"] = 77.69
        entry["walk_minutes"] = 8.0
        entry["orr_distance_m"] = 400
        entry["peace_score"] = 70.0
        filtered.append(entry)
    ctx.path("filtered.json").write_text(json.dumps(filtered, indent=2))

    # Mock LLM scorer
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"criteria_scores": {"power_backup": {"score": 18, "max": 20, "confidence": "high", "evidence": "Full gen"}, "noise": {"score": 14, "max": 20, "confidence": "medium", "evidence": "3rd floor"}, "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "No mention"}, "light_ventilation": {"score": 8, "max": 10, "confidence": "medium", "evidence": "East facing"}, "water": {"score": 7, "max": 10, "confidence": "high", "evidence": "Corp+bore"}, "maintenance": {"score": 8, "max": 10, "confidence": "high", "evidence": "Gated"}, "wfh_livability": {"score": 7, "max": 10, "confidence": "medium", "evidence": "Semi furnished"}, "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "28/sqft"}}, "pros": ["Full generator", "Gated community"], "cons": ["No fiber mentioned"], "elevator_pitch": "Quiet gated flat with full power backup", "disqualified": false, "disqualify_reason": null}')]
    async_mock_response = AsyncMock(return_value=mock_response)
    with patch("src.scorer.anthropic.AsyncAnthropic") as MockClient, \
         patch("src.scorer.Dedup") as MockDedup2, \
         patch("src.scorer.run_comparative_ranking", return_value=None):
        MockClient.return_value.messages.create = async_mock_response
        MockDedup2.return_value.update_score.return_value = None
        from src.scorer import run_score
        run_score(ctx)

    scored = json.loads(ctx.path("scored.json").read_text())
    assert len(scored) >= 1
    assert "final_score" in scored[0]

    # Report
    from src.reporter import generate_report
    html_path = generate_report(ctx)
    assert ctx.path("report.html").exists()
    assert ctx.path("report.md").exists()
    assert "House Hunt Report" in ctx.path("report.md").read_text()


def test_full_report_pipeline_with_structured_scoring(tmp_path):
    """Verify scored.json with new schema produces complete HTML report."""
    from src.reporter import generate_report
    from src.config import Config, RunContext

    cfg = Config(
        name="test", target_localities=["kadubeesanahalli"], ptp_coords=(12.942, 77.6905),
        max_walk_minutes=30, min_orr_distance_m=200, max_rent=60000, score_threshold=75,
        bhk=2, score_weights={"peace": 0.4, "llm": 0.6},
        llm_weights={"power_backup": 20, "noise": 20, "internet": 15, "light_ventilation": 10,
            "water": 10, "maintenance": 10, "wfh_livability": 10, "value": 5}
    )

    scored = [{
        "summary": {"property_id": "int1", "title": "Integration Test Flat", "rent": 30000,
            "deposit": 100000, "maintenance": 3000, "sqft": 1100, "address": "Test Rd",
            "locality": "kadubeesanahalli", "building_name": "Test Heights",
            "detail_url": "https://nobroker.in/int1", "available_date": None, "image_urls": []},
        "detail": {"property_id": "int1", "furnishing": "Semi", "floor": "3/5",
            "power_backup": "Full Generator", "facing": "East", "bathrooms": 2, "balconies": 1,
            "parking": "Car", "building_age": "1-3", "preferred_tenant": "Family",
            "water_supply": "Corporation + Borewell", "gated_security": True, "description": "Nice flat"},
        "lat": 12.94, "lon": 77.69, "walk_minutes": 8.0, "orr_distance_m": 450,
        "peace_score": 80.0, "llm_score": 86.0, "final_score": 83.6,
        "disqualified": False, "disqualify_reason": None,
        "criteria_scores": {
            "power_backup": {"score": 19, "max": 20, "confidence": "high", "evidence": "Full gen mentioned"},
            "noise": {"score": 16, "max": 20, "confidence": "medium", "evidence": "3rd floor, east"},
            "internet": {"score": 10, "max": 15, "confidence": "low", "evidence": "No fiber info"},
            "light_ventilation": {"score": 9, "max": 10, "confidence": "high", "evidence": "East, 1 balcony"},
            "water": {"score": 9, "max": 10, "confidence": "high", "evidence": "Corp + borewell"},
            "maintenance": {"score": 9, "max": 10, "confidence": "high", "evidence": "Gated, security"},
            "wfh_livability": {"score": 8, "max": 10, "confidence": "medium", "evidence": "Semi, spacious"},
            "value": {"score": 4, "max": 5, "confidence": "high", "evidence": "30/sqft reasonable"},
        },
        "pros": ["Full generator", "Gated community", "Good water", "Close to PTP"],
        "cons": ["No fiber internet info", "Semi-furnished"],
        "elevator_pitch": "Gated 3rd-floor flat, full generator, 8min walk to PTP",
        "data_completeness": 0.92,
        "peace_breakdown": {"orr_distance_m": 450, "base_score": 61.7, "locality_bonus": 20, "final": 80},
        "comparative_rank": 1, "comparative_notes": "Best overall for WFH",
        "duplicate_of": None,
    }]

    comparative = {
        "rankings": [{"property_id": "int1", "rank": 1, "reasoning": "Best overall"}],
        "top_3_summary": "#1 Integration Test Flat — best overall for WFH."
    }

    run_dir = tmp_path / "int_run"
    run_dir.mkdir()
    (run_dir / "scored.json").write_text(json.dumps(scored))
    (run_dir / "config.json").write_text(cfg.model_dump_json())
    (run_dir / "comparative.json").write_text(json.dumps(comparative))
    ctx = RunContext(run_id="test_int", run_dir=run_dir, config=cfg)

    html_path = generate_report(ctx)
    html = html_path.read_text()

    # Verify all new sections present
    assert "elevator-pitch" in html or "Gated 3rd-floor flat" in html
    assert "criteria-chart" in html or "criteria-bar" in html
    assert "pro-list" in html or "Strengths" in html
    assert "con-list" in html or "Weaknesses" in html
    assert "comp-banner" in html
    assert "Top Picks" in html or "top_3_summary" in html
    assert "power_backup" in html or "power backup" in html
    assert "confidence" in html.lower() or "●●●" in html

    # Verify markdown
    md = (run_dir / "report.md").read_text()
    assert "Full generator" in md
    assert "No fiber" in md
    assert "Gated 3rd-floor flat" in md
    assert "Top Picks" in md
