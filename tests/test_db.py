from pathlib import Path


def test_dedup_new_listing(tmp_path):
    from src.db import Dedup
    db = Dedup(tmp_path / "test.db")
    assert not db.is_seen("prop_001")
    db.mark_seen("prop_001")
    assert db.is_seen("prop_001")


def test_dedup_update_score(tmp_path):
    from src.db import Dedup
    db = Dedup(tmp_path / "test.db")
    db.mark_seen("prop_002")
    db.update_score("prop_002", score=88.5, disqualified=False)
    db2 = Dedup(tmp_path / "test.db")
    assert db2.is_seen("prop_002")


def test_dedup_persists_across_instances(tmp_path):
    from src.db import Dedup
    db_path = tmp_path / "test.db"
    db1 = Dedup(db_path)
    db1.mark_seen("prop_003")
    del db1
    db2 = Dedup(db_path)
    assert db2.is_seen("prop_003")
