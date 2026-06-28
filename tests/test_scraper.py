SAMPLE_SEO_MARKDOWN = """
# 2 BHK Flats for Rent in Kadubeesanahalli

## [2 BHK Flat In Sls Signature for Rent In Kadubeesanahalli](https://www.nobroker.in/property/rent/bangalore/Kadubeesanahalli/2-bhk-flat-sls-signature-abc123/detail)

₹50,000

₹4,200 Maintenance

₹2,00,000 Deposit

1,210 sqft

Kaverappa Layout, Kadubeesanahalli, Panathur, Bengaluru

Available from 2026-06-25

![image](https://img.nobroker.in/1.jpg)

## [2 BHK In Chourasia Manor](https://www.nobroker.in/property/rent/bangalore/Bellandur/2-bhk-chourasia-def456/detail)

₹35,000

₹3,000 Maintenance

₹1,50,000 Deposit

1,050 sqft

Gear Road, Bhoganhalli, Bengaluru
"""

SAMPLE_DETAIL_MARKDOWN = """
# 2 BHK Flat In Sls Signature for Rent

₹50,000 / month

## Property Details

| Feature | Value |
|---------|-------|
| Furnishing | Semi |
| Facing | West |
| Floor | 3 / 4 |
| Bathrooms | 2 |
| Balconies | 1 |
| Parking | Bike |
| Age of Building | 1-3 Years |
| Preferred Tenant | Family |
| Water Supply | Borewell |
| Gated Security | No |
| Power Backup | Full |

## Description

Spacious 2 BHK with good ventilation. 24x7 power backup with generator. Near Prestige Tech Park.
Close to metro station. ACT fibernet available.
"""


def test_parse_seo_listings():
    from src.scraper import parse_listings_from_markdown
    listings = parse_listings_from_markdown(SAMPLE_SEO_MARKDOWN, "kadubeesanahalli")
    assert len(listings) == 2
    first = listings[0]
    assert first.property_id == "abc123"
    assert first.rent == 50000
    assert first.maintenance == 4200
    assert first.deposit == 200000
    assert first.sqft == 1210
    assert "Kaverappa" in first.address
    assert first.locality == "kadubeesanahalli"
    assert "detail" in first.detail_url
    second = listings[1]
    assert second.rent == 35000
    assert second.property_id == "def456"


def test_parse_detail():
    from src.scraper import parse_detail_from_markdown
    detail = parse_detail_from_markdown(SAMPLE_DETAIL_MARKDOWN, "abc123")
    assert detail.property_id == "abc123"
    assert detail.furnishing == "Semi"
    assert detail.power_backup == "Full"
    assert detail.floor == "3 / 4"
    assert detail.bathrooms == 2
    assert detail.water_supply == "Borewell"
    assert detail.gated_security is False
    assert "power backup" in detail.description.lower()
