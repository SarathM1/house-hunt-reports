import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / "listings.db"


class Dedup:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                property_id TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                score REAL,
                disqualified BOOLEAN DEFAULT 0
            )
        """)
        self.conn.commit()

    def is_seen(self, property_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen WHERE property_id = ?", (property_id,)
        ).fetchone()
        return row is not None

    def mark_seen(self, property_id: str, score: float | None = None, disqualified: bool = False) -> None:
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO seen (property_id, first_seen, last_seen, score, disqualified)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(property_id) DO UPDATE SET last_seen = ?""",
            (property_id, now, now, score, disqualified, now)
        )
        self.conn.commit()

    def update_score(self, property_id: str, score: float, disqualified: bool) -> None:
        self.conn.execute(
            "UPDATE seen SET score = ?, disqualified = ?, last_seen = ? WHERE property_id = ?",
            (score, disqualified, datetime.now().isoformat(), property_id)
        )
        self.conn.commit()
