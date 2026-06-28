def test_data_completeness_full():
    from src.detail_scraper import compute_data_completeness
    detail = {
        "property_id": "abc", "furnishing": "Semi", "floor": "3/5",
        "power_backup": "Full", "water_supply": "Corporation",
        "gated_security": True, "facing": "East", "bathrooms": 2,
        "balconies": 1, "parking": "Car", "building_age": "1-3 Years",
        "preferred_tenant": "Family", "description": "Nice flat"
    }
    score = compute_data_completeness(detail)
    assert score == 1.0


def test_data_completeness_partial():
    from src.detail_scraper import compute_data_completeness
    detail = {
        "property_id": "abc", "furnishing": "Semi", "floor": "3/5",
        "power_backup": None, "water_supply": None,
        "gated_security": None, "facing": None, "bathrooms": None,
        "balconies": None, "parking": None, "building_age": None,
        "preferred_tenant": None, "description": "Nice flat"
    }
    score = compute_data_completeness(detail)
    assert 0.2 < score < 0.5


def test_data_completeness_empty():
    from src.detail_scraper import compute_data_completeness
    detail = {
        "property_id": "abc", "furnishing": "", "floor": "",
        "power_backup": None, "water_supply": None,
        "gated_security": None, "facing": None, "bathrooms": None,
        "balconies": None, "parking": None, "building_age": None,
        "preferred_tenant": None, "description": ""
    }
    score = compute_data_completeness(detail)
    assert score == 0.0


def test_needs_retry_missing_critical():
    from src.detail_scraper import needs_retry
    detail = {"power_backup": None, "water_supply": "Corp", "furnishing": "Semi"}
    assert needs_retry(detail) is True


def test_needs_retry_all_present():
    from src.detail_scraper import needs_retry
    detail = {"power_backup": "Full", "water_supply": "Corp", "furnishing": "Semi"}
    assert needs_retry(detail) is False
