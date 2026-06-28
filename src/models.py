from pydantic import BaseModel, Field
from typing import Optional


class ListingSummary(BaseModel):
    """From SEO listing page scrape — basic info + detail URL."""
    title: str
    url: str
    rent: int
    maintenance: int = 0
    deposit: int = 0
    sqft: int = 0
    address: str = ""
    locality: str = ""
    available_date: str = ""
    building_name: str = ""
    source_locality: str = ""  # which target locality page it came from


class ListingDetail(BaseModel):
    """Full listing data after scraping detail page."""
    title: str
    url: str
    property_id: str = ""
    rent: int
    maintenance: int = 0
    deposit: int = 0
    sqft: int = 0
    address: str = ""
    locality: str = ""
    building_name: str = ""
    available_date: str = ""
    furnishing: str = ""
    facing: str = ""
    floor: str = ""
    bathrooms: int = 0
    balconies: int = 0
    parking: str = ""
    building_age: str = ""
    preferred_tenant: str = ""
    water_supply: str = ""
    gated_security: str = ""
    power_backup: str = ""
    description: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source_locality: str = ""


class ScoredListing(ListingDetail):
    """Listing with spatial and LLM scores."""
    walk_minutes: Optional[float] = None
    orr_distance_meters: Optional[float] = None
    peace_score: float = 0.0
    llm_score: float = 0.0
    llm_reasoning: str = ""
    total_score: float = 0.0
