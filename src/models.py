from pydantic import BaseModel


class ListingSummary(BaseModel):
    property_id: str
    title: str
    rent: int
    deposit: int
    maintenance: int | None = None
    sqft: int
    address: str
    locality: str
    building_name: str | None = None
    detail_url: str
    available_date: str | None = None
    image_urls: list[str] = []


class ListingDetail(BaseModel):
    property_id: str
    furnishing: str
    floor: str
    power_backup: str | None = None
    facing: str | None = None
    bathrooms: int | None = None
    balconies: int | None = None
    parking: str | None = None
    building_age: str | None = None
    preferred_tenant: str | None = None
    water_supply: str | None = None
    gated_security: bool | None = None
    description: str


class ScoredListing(BaseModel):
    summary: ListingSummary
    detail: ListingDetail
    lat: float
    lon: float
    walk_minutes: float
    orr_distance_m: float
    peace_score: float
    llm_score: float
    llm_reasoning: str
    final_score: float
    disqualified: bool
    disqualify_reason: str | None = None
