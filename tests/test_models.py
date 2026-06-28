import json
import pytest


def test_listing_summary_roundtrip():
    from src.models import ListingSummary
    data = {
        "property_id": "abc123",
        "title": "2 BHK in SLS Signature",
        "rent": 35000,
        "deposit": 200000,
        "maintenance": 4200,
        "sqft": 1210,
        "address": "Kaverappa Layout, Kadubeesanahalli",
        "locality": "kadubeesanahalli",
        "building_name": "SLS Signature",
        "detail_url": "https://www.nobroker.in/property/rent/bangalore/abc123/detail",
        "available_date": "2026-07-01",
        "image_urls": ["https://img.nobroker.in/1.jpg"]
    }
    s = ListingSummary(**data)
    assert s.property_id == "abc123"
    assert s.rent == 35000
    dumped = json.loads(s.model_dump_json())
    assert dumped["property_id"] == "abc123"


def test_listing_detail_optional_fields():
    from src.models import ListingDetail
    d = ListingDetail(
        property_id="abc123",
        furnishing="Semi",
        floor="3/4",
        power_backup=None,
        description="Nice flat",
    )
    assert d.power_backup is None
    assert d.bathrooms is None
    assert d.gated_security is None


def test_scored_listing_composition():
    from src.models import ListingSummary, ListingDetail, ScoredListing, CriteriaScore
    summary = ListingSummary(
        property_id="abc123", title="Test", rent=30000, deposit=100000,
        maintenance=None, sqft=1000, address="Test addr",
        locality="bellandur", building_name=None,
        detail_url="https://example.com", available_date=None, image_urls=[]
    )
    detail = ListingDetail(
        property_id="abc123", furnishing="Fully", floor="2/5",
        power_backup="Full", description="Great flat"
    )
    scored = ScoredListing(
        summary=summary, detail=detail,
        lat=12.94, lon=77.69, walk_minutes=8.5, orr_distance_m=350,
        peace_score=75.0, llm_score=82.0,
        final_score=79.2, disqualified=False, disqualify_reason=None,
        criteria_scores={
            "power_backup": CriteriaScore(score=18, max=20, confidence="high", evidence="Full generator"),
        },
        pros=["Good backup"], cons=["No fiber"], elevator_pitch="Nice flat",
        data_completeness=0.8,
    )
    assert scored.summary.rent == 30000
    assert scored.detail.power_backup == "Full"
    assert scored.disqualified is False
    d = scored.model_dump()
    assert d["summary"]["property_id"] == "abc123"
    assert d["detail"]["furnishing"] == "Fully"


def test_criteria_score():
    from src.models import CriteriaScore
    cs = CriteriaScore(score=18, max=20, confidence="high", evidence="Full generator mentioned")
    assert cs.score == 18
    assert cs.max == 20
    assert cs.confidence == "high"
    d = cs.model_dump()
    assert d["evidence"] == "Full generator mentioned"


def test_criteria_score_validation():
    from src.models import CriteriaScore
    with pytest.raises(Exception):
        CriteriaScore(score=18, max=20, confidence="invalid", evidence="test")


def test_peace_breakdown():
    from src.models import PeaceBreakdown
    pb = PeaceBreakdown(orr_distance_m=450, base_score=60, locality_bonus=20, final=80)
    assert pb.final == 80
    assert pb.locality_bonus == 20


def test_ranking_entry():
    from src.models import RankingEntry
    re = RankingEntry(property_id="abc123", rank=1, reasoning="Best overall")
    assert re.rank == 1


def test_comparative_result():
    from src.models import ComparativeResult, RankingEntry
    cr = ComparativeResult(
        rankings=[RankingEntry(property_id="abc", rank=1, reasoning="Best")],
        top_3_summary="#1 abc — best overall"
    )
    assert len(cr.rankings) == 1
    assert cr.top_3_summary.startswith("#1")


def test_scored_listing_new_fields():
    from src.models import ListingSummary, ListingDetail, ScoredListing, CriteriaScore, PeaceBreakdown
    summary = ListingSummary(
        property_id="abc123", title="Test", rent=30000, deposit=100000,
        maintenance=None, sqft=1000, address="Test addr",
        locality="bellandur", building_name=None,
        detail_url="https://example.com", available_date=None, image_urls=[]
    )
    detail = ListingDetail(
        property_id="abc123", furnishing="Fully", floor="2/5",
        power_backup="Full", description="Great flat"
    )
    scored = ScoredListing(
        summary=summary, detail=detail,
        lat=12.94, lon=77.69, walk_minutes=8.5, orr_distance_m=350,
        peace_score=75.0, llm_score=82.0,
        final_score=79.2, disqualified=False, disqualify_reason=None,
        criteria_scores={
            "power_backup": CriteriaScore(score=18, max=20, confidence="high", evidence="Full generator"),
            "noise": CriteriaScore(score=14, max=20, confidence="medium", evidence="3rd floor"),
        },
        pros=["Full generator backup", "Gated community"],
        cons=["No fiber mentioned"],
        elevator_pitch="Quiet gated flat with full generator",
        data_completeness=0.85,
        peace_breakdown=PeaceBreakdown(orr_distance_m=350, base_score=52.5, locality_bonus=0, final=52.5),
    )
    assert scored.elevator_pitch == "Quiet gated flat with full generator"
    assert scored.criteria_scores["power_backup"].score == 18
    assert scored.data_completeness == 0.85
    assert scored.comparative_rank is None
    assert scored.duplicate_of is None
    d = scored.model_dump()
    assert "criteria_scores" in d
    assert "pros" in d
    assert "peace_breakdown" in d
