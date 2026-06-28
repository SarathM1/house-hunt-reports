import math


def test_haversine_known_distance():
    from src.spatial import haversine_meters
    # PTP to a point ~500m away
    d = haversine_meters(12.9420, 77.6905, 12.9420, 77.6955)
    assert 400 < d < 600


def test_min_orr_distance():
    from src.spatial import min_orr_distance
    # Point right on ORR reference
    d = min_orr_distance(12.9352, 77.6830)
    assert d < 10


def test_peace_score_close_to_orr():
    from src.spatial import compute_peace_score
    score, _ = compute_peace_score(150, "bellandur")
    assert score == 0  # < 200m = disqualified, score 0


def test_peace_score_far_from_orr():
    from src.spatial import compute_peace_score
    score, _ = compute_peace_score(500, "kadubeesanahalli")
    assert score >= 70  # far + priority locality


def test_peace_score_mid_range():
    from src.spatial import compute_peace_score
    score, _ = compute_peace_score(300, "panathur")
    assert 20 < score < 70


def test_peace_score_returns_breakdown():
    from src.spatial import compute_peace_score
    score, breakdown = compute_peace_score(450, "kadubeesanahalli")
    assert breakdown.orr_distance_m == 450
    assert breakdown.locality_bonus == 20  # priority locality
    assert breakdown.final == score
    assert breakdown.base_score > 0


def test_peace_breakdown_no_bonus():
    from src.spatial import compute_peace_score
    score, breakdown = compute_peace_score(500, "bellandur")
    assert breakdown.locality_bonus == 0
    assert breakdown.final == score


def test_peace_breakdown_close_to_orr():
    from src.spatial import compute_peace_score
    score, breakdown = compute_peace_score(150, "bellandur")
    assert score == 0
    assert breakdown.final == 0
