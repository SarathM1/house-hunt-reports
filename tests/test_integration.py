import json
from pathlib import Path
from unittest.mock import patch, MagicMock

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
    mock_response.content = [MagicMock(text='{"score": 82, "reasoning": "Good flat", "disqualified": false, "disqualify_reason": null}')]
    with patch("src.scorer.anthropic.Anthropic") as MockClient, \
         patch("src.scorer.Dedup") as MockDedup2:
        MockClient.return_value.messages.create.return_value = mock_response
        MockDedup2.return_value.update_score.return_value = None
        from src.scorer import run_score
        run_score(ctx)

    scored = json.loads(ctx.path("scored.json").read_text())
    assert len(scored) >= 1
    assert "final_score" in scored[0]

    # Report
    from src.reporter import generate_report
    report = generate_report(ctx)
    assert "House Hunt Report" in report
    assert ctx.path("report.md").exists()
