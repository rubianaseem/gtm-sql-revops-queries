"""Load CSV exports into a SQLite file and build the staging views."""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"

# CRM exports load as raw_* tables with every column as TEXT, exactly as
# exported. Cleaning happens in SQL (sql/00_staging.sql) where you can see it.
RAW_TABLES = {
    "raw_owners": "sample_owners.csv",
    "raw_companies": "sample_companies.csv",
    "raw_contacts": "sample_contacts.csv",
    "raw_deals": "sample_deals.csv",
    "raw_deal_stage_history": "sample_deal_stage_history.csv",
    "raw_campaigns": "sample_campaigns.csv",
    "raw_touches": "sample_touches.csv",
}
# Lookup tables you own. These get real types so numbers sort as numbers.
LOOKUP_TABLES = {
    "stage_map": "stage_map.csv",
    "fx_rates": "sample_fx_rates.csv",
    "quotas": "sample_quotas.csv",
}


def _infer_type(values):
    vals = [v for v in values if v.strip() != ""]
    if not vals:
        return "TEXT"
    try:
        for v in vals:
            int(v)
        return "INTEGER"
    except ValueError:
        pass
    try:
        for v in vals:
            float(v)
        return "REAL"
    except ValueError:
        return "TEXT"


def _cast(value, sql_type):
    if sql_type == "TEXT":
        return value
    if value.strip() == "":
        return None
    return int(value) if sql_type == "INTEGER" else float(value)


def load_table(conn, table, csv_path, typed=False):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        rows = [r + [""] * (len(header) - len(r)) for r in reader if any(c.strip() for c in r)]
    types = ["TEXT"] * len(header)
    if typed:
        types = [_infer_type([r[i] for r in rows]) for i in range(len(header))]
    cols = ", ".join(f'"{h}" {t}' for h, t in zip(header, types))
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.execute(f'CREATE TABLE "{table}" ({cols})')
    marks = ", ".join("?" for _ in header)
    conn.executemany(
        f'INSERT INTO "{table}" VALUES ({marks})',
        [[_cast(v, t) for v, t in zip(r, types)] for r in rows],
    )
    return len(rows)


def build_database(data_dir, db_path, files=None):
    """Create db_path from the CSVs in data_dir. Returns row counts per table.

    files lets you point a table at a different CSV, e.g. your own export:
    {"raw_deals": "/path/to/deals.csv"}.
    """
    data_dir = Path(data_dir)
    files = files or {}
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # the db is a build artefact in out/, rebuilt every run
    conn = sqlite3.connect(db_path)
    counts = {}
    for table, name in {**RAW_TABLES, **LOOKUP_TABLES}.items():
        path = Path(files.get(table, data_dir / name))
        counts[table] = load_table(conn, table, path, typed=table in LOOKUP_TABLES)
    conn.executescript((SQL_DIR / "00_staging.sql").read_text())
    conn.commit()
    conn.close()
    return counts
