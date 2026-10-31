"""Run the numbered SQL files and write each result to CSV."""
import csv
import sqlite3
from pathlib import Path

from .loader import SQL_DIR

QUERY_FILES = [
    "01_funnel_conversion.sql",
    "02_stage_velocity.sql",
    "03_lead_to_deal_cohort.sql",
    "04_pipeline_coverage.sql",
    "05_campaign_attribution.sql",
    "06_data_quality_audit.sql",
    "07_stalled_deals.sql",
]


def run_query(conn, sql_file, as_of):
    sql = (SQL_DIR / sql_file).read_text()
    cur = conn.execute(sql, {"as_of": as_of})
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def run_all(db_path, as_of):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {f.removesuffix(".sql"): run_query(conn, f, as_of) for f in QUERY_FILES}
    finally:
        conn.close()


def write_csv(path, rows, columns=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
