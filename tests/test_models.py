import json

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
    from src.models import ListingSummary, ListingDetail, ScoredListing
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
        peace_score=75.0, llm_score=82.0, llm_reasoning="Good backup",
        final_score=79.2, disqualified=False, disqualify_reason=None
    )
    assert scored.summary.rent == 30000
    assert scored.detail.power_backup == "Full"
    assert scored.disqualified is False
    d = scored.model_dump()
    assert d["summary"]["property_id"] == "abc123"
    assert d["detail"]["furnishing"] == "Fully"
