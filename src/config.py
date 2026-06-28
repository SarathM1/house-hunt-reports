import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

FIRECRAWL_API_KEY = os.environ["FIRECRAWL_API_KEY"]
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
FILTERED_DIR = DATA_DIR / "filtered"
SCORED_DIR = DATA_DIR / "scored"

# Prestige Tech Park main gate coordinates
PTP_LAT = 12.9316
PTP_LON = 77.6904

# Outer Ring Road reference line (approximate center lat/lon segments)
ORR_REFERENCE_POINTS = [
    (12.9352, 77.6830),
    (12.9340, 77.6870),
    (12.9330, 77.6920),
    (12.9310, 77.6960),
    (12.9280, 77.7000),
]

# Pipeline thresholds
MAX_WALK_MINUTES = 12
MIN_ORR_DISTANCE_METERS = 200
MIN_SCORE_FOR_REPORT = 85

# Target localities for NoBroker SEO pages
TARGET_LOCALITIES = [
    "kadubeesanahalli",
    "bellandur",
    "panathur",
    "marathahalli",
    "doddakannelli",
]

# Max rent filter (optional, set 0 to disable)
MAX_RENT = 0
# Min sqft filter (optional, set 0 to disable)
MIN_SQFT = 0
