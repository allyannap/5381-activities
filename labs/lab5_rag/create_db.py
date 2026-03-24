import sqlite3
import os

DB_PATH = "ice_news.db"

def create_tables():
    print("running create_tables()...")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        headline TEXT NOT NULL,
        source TEXT,
        published_at TEXT,
        url TEXT UNIQUE,
        state TEXT,
        city TEXT,
        county TEXT,
        region_type TEXT,
        topic_tags TEXT,
        snippet TEXT,
        full_text TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS state_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state TEXT NOT NULL UNIQUE,
        state_abbr TEXT,
        ice_facility_count INTEGER,
        foreign_born_pct REAL,
        non_citizen_pct REAL,
        total_population INTEGER,
        notes TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

    print("database and tables created successfully.")
    print("database file path:", os.path.abspath(DB_PATH))

if __name__ == "__main__":
    create_tables()