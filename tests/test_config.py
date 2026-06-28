import json
from pathlib import Path


def test_load_default_config(tmp_path):
    default = {
        "name": "default",
        "target_localities": ["kadubeesanahalli", "bellandur", "panathur", "marathahalli"],
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
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "default.json").write_text(json.dumps(default))

    from src.config import load_config
    cfg = load_config("default", configs_dir=configs_dir)
    assert cfg.name == "default"
    assert cfg.max_rent == 50000
    assert cfg.ptp_coords == (12.9420, 77.6905)
    assert cfg.score_weights == {"peace": 0.4, "llm": 0.6}
    assert cfg.llm_weights["power_backup"] == 20


def test_profile_inherits_and_overrides(tmp_path):
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default = {
        "name": "default",
        "target_localities": ["kadubeesanahalli"],
        "ptp_coords": [12.9420, 77.6905],
        "max_walk_minutes": 12,
        "min_orr_distance_m": 200,
        "max_rent": 50000,
        "score_threshold": 85,
        "bhk": 2,
        "score_weights": {"peace": 0.4, "llm": 0.6},
        "llm_weights": {"power_backup": 20, "noise": 20, "internet": 15,
            "light_ventilation": 10, "water": 10, "maintenance": 10,
            "wfh_livability": 10, "value": 5}
    }
    peaceful = {
        "name": "peaceful",
        "min_orr_distance_m": 300,
        "score_weights": {"peace": 0.5, "llm": 0.5}
    }
    (configs_dir / "default.json").write_text(json.dumps(default))
    (configs_dir / "peaceful.json").write_text(json.dumps(peaceful))

    from src.config import load_config
    cfg = load_config("peaceful", configs_dir=configs_dir)
    assert cfg.name == "peaceful"
    assert cfg.min_orr_distance_m == 300
    assert cfg.score_weights == {"peace": 0.5, "llm": 0.5}
    assert cfg.max_rent == 50000  # inherited from default


def test_create_run(tmp_path):
    from src.config import load_config, create_run, Config
    import json

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default = {
        "name": "default", "target_localities": ["kadubeesanahalli"],
        "ptp_coords": [12.9420, 77.6905], "max_walk_minutes": 12,
        "min_orr_distance_m": 200, "max_rent": 50000, "score_threshold": 85,
        "bhk": 2, "score_weights": {"peace": 0.4, "llm": 0.6},
        "llm_weights": {"power_backup": 20, "noise": 20, "internet": 15,
            "light_ventilation": 10, "water": 10, "maintenance": 10,
            "wfh_livability": 10, "value": 5}
    }
    (configs_dir / "default.json").write_text(json.dumps(default))
    cfg = load_config("default", configs_dir=configs_dir)

    data_dir = tmp_path / "data" / "runs"
    ctx = create_run(cfg, data_dir=data_dir)
    assert ctx.run_dir.exists()
    assert (ctx.run_dir / "config.json").exists()
    snapshot = json.loads((ctx.run_dir / "config.json").read_text())
    assert snapshot["name"] == "default"
    assert ctx.path("raw.json").parent == ctx.run_dir
