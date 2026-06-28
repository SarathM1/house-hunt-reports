import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIGS_DIR = PROJECT_ROOT / "configs"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "runs"

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

ORR_REFERENCE_POINTS = [
    (12.9352, 77.6830),
    (12.9340, 77.6870),
    (12.9330, 77.6920),
    (12.9310, 77.6960),
    (12.9280, 77.7000),
]


class Config(BaseModel):
    name: str
    target_localities: list[str]
    ptp_coords: tuple[float, float]
    max_walk_minutes: int
    min_orr_distance_m: int
    max_rent: int
    score_threshold: int
    bhk: int
    score_weights: dict[str, float]
    llm_weights: dict[str, int]


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    config: Config

    def path(self, filename: str) -> Path:
        return self.run_dir / filename


def load_config(profile: str = "default", configs_dir: Path | None = None) -> Config:
    configs_dir = configs_dir or DEFAULT_CONFIGS_DIR
    default_path = configs_dir / "default.json"
    default_data = json.loads(default_path.read_text())

    if profile != "default":
        profile_path = configs_dir / f"{profile}.json"
        profile_data = json.loads(profile_path.read_text())
        merged = {**default_data, **profile_data}
    else:
        merged = default_data

    return Config(**merged)


def create_run(config: Config, data_dir: Path | None = None) -> RunContext:
    data_dir = data_dir or DEFAULT_DATA_DIR
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = data_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(config.model_dump(), indent=2)
    )
    return RunContext(run_id=run_id, run_dir=run_dir, config=config)
