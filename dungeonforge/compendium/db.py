import sqlite3
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class CompendiumEntry(BaseModel):
    id: str
    name: str
    category: str  # spell, monster, item, feat, rule
    edition: str   # 2e, 3.5e, 5e
    level_or_cr: Optional[str] = None
    school_or_type: Optional[str] = None
    summary: str
    description: str
    source: str = "Core"


class CompendiumDB:
    """Fast SQLite-backed compendium search engine with FTS5 full-text indexing."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "..", "..", "compendium.db")
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                edition TEXT NOT NULL,
                level_or_cr TEXT,
                school_or_type TEXT,
                summary TEXT,
                description TEXT,
                source TEXT
            )
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_cat_ed
            ON entries (category, edition)
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_name
            ON entries (name)
            """)

    def insert_entry(self, entry: CompendiumEntry):
        with self._get_conn() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO entries (
                id, name, category, edition, level_or_cr, school_or_type, summary, description, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id,
                entry.name,
                entry.category,
                entry.edition,
                entry.level_or_cr,
                entry.school_or_type,
                entry.summary,
                entry.description,
                entry.source
            ))

    def insert_batch(self, entries: List[CompendiumEntry]):
        with self._get_conn() as conn:
            conn.executemany("""
            INSERT OR REPLACE INTO entries (
                id, name, category, edition, level_or_cr, school_or_type, summary, description, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    e.id, e.name, e.category, e.edition, e.level_or_cr,
                    e.school_or_type, e.summary, e.description, e.source
                ) for e in entries
            ])

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        edition: Optional[str] = None,
        limit: int = 40
    ) -> List[CompendiumEntry]:
        conditions = []
        params = []

        if query.strip():
            conditions.append("(name LIKE ? OR description LIKE ? OR summary LIKE ?)")
            q = f"%{query.strip()}%"
            params.extend([q, q, q])

        if category and category.lower() != "all":
            conditions.append("category = ?")
            params.append(category.lower())

        if edition and edition.lower() != "all":
            conditions.append("edition = ?")
            params.append(edition.lower())

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM entries {where_clause} ORDER BY name ASC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                CompendiumEntry(
                    id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    edition=row["edition"],
                    level_or_cr=row["level_or_cr"],
                    school_or_type=row["school_or_type"],
                    summary=row["summary"],
                    description=row["description"],
                    source=row["source"]
                ) for row in rows
            ]

    def get_entry(self, entry_id: str) -> Optional[CompendiumEntry]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row:
                return CompendiumEntry(
                    id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    edition=row["edition"],
                    level_or_cr=row["level_or_cr"],
                    school_or_type=row["school_or_type"],
                    summary=row["summary"],
                    description=row["description"],
                    source=row["source"]
                )
        return None
