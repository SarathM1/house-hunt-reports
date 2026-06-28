from typing import Literal

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


class CriteriaScore(BaseModel):
    score: int
    max: int
    confidence: Literal["high", "medium", "low"]
    evidence: str


class PeaceBreakdown(BaseModel):
    orr_distance_m: float
    base_score: float
    locality_bonus: float
    final: float


class RankingEntry(BaseModel):
    property_id: str
    rank: int
    reasoning: str


class ComparativeResult(BaseModel):
    rankings: list[RankingEntry]
    top_3_summary: str


class ScoredListing(BaseModel):
    summary: ListingSummary
    detail: ListingDetail
    lat: float
    lon: float
    walk_minutes: float
    orr_distance_m: float
    peace_score: float
    llm_score: float
    final_score: float
    disqualified: bool
    disqualify_reason: str | None = None

    # Structured scoring
    criteria_scores: dict[str, CriteriaScore] = {}
    pros: list[str] = []
    cons: list[str] = []
    elevator_pitch: str = ""
    data_completeness: float = 0.0

    # Comparative (filled by Pass 2)
    comparative_rank: int | None = None
    comparative_notes: str | None = None

    # Peace breakdown
    peace_breakdown: PeaceBreakdown | None = None

    # Dedup
    duplicate_of: str | None = None
