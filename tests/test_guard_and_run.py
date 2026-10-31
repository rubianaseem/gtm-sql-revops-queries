import re
import sqlite3

import pytest

from gtm_sql import brief, llm
from gtm_sql.ask import extract_sql
from gtm_sql.guard import UnsafeQuery, check_sql, run_readonly
import run_queries


@pytest.mark.parametrize("sql", [
    "DELETE FROM raw_deals",
    "SELECT 1; DROP TABLE raw_deals",
    "WITH x AS (SELECT 1) DELETE FROM raw_deals",
    "PRAGMA table_info(raw_deals)",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT * FROM raw_deals -- ; \n; UPDATE raw_deals SET amount = 0",
    "",
])
def test_guard_refuses_writes(sql):
    with pytest.raises(UnsafeQuery):
        check_sql(sql)


def test_guard_allows_reads_with_functions_and_strings(db):
    cols, rows, _ = run_readonly(db, "SELECT replace('a;b', ';', '-') AS x")
    assert rows == [("a-b",)]
    cols, rows, _ = run_readonly(db, "WITH d AS (SELECT * FROM stg_deals) SELECT COUNT(*) FROM d")
    assert rows[0][0] == 105


def test_database_is_opened_read_only(db):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM raw_deals")


def test_row_limit(db):
    _, rows, truncated = run_readonly(db, "SELECT * FROM stg_touches", max_rows=10)
    assert len(rows) == 10 and truncated


def test_extract_sql_from_fenced_reply():
    assert extract_sql("Here:\n```sql\nSELECT 1\n```") == "SELECT 1"


def test_full_run_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert run_queries.main(["--out", str(tmp_path)]) == 0
    for name in ["review_queue.csv", "revops_brief.md", "q06_data_quality_audit.csv", "q01_funnel_conversion.csv"]:
        assert (tmp_path / name).exists()
    text = (tmp_path / "revops_brief.md").read_text()
    assert "Mode: built-in rules" in text
    assert not re.search(r"[^\x00-\x7F]", text), "brief must be plain ASCII, no emojis"


def test_claude_failure_falls_back_to_rules(results, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(llm, "complete", boom)
    text, mode = brief.write_brief(brief.findings(results), "2026-10-31", use_claude=True)
    assert mode == "rules" and "Claude call failed" in text


def test_review_queue_has_owner_for_deals(results):
    queue = brief.review_queue(results, {"D9001": "Jordan Lee"})
    row = next(r for r in queue if r["record_id"] == "D9001")
    assert row["owner"] == "Jordan Lee"
    assert [r["priority"] for r in queue] == sorted(r["priority"] for r in queue)


def test_authorizer_blocks_writes_even_without_text_check(db, tmp_path):
    """Layer 3 on its own: a writable connection with the authorizer still refuses."""
    import shutil
    from gtm_sql.guard import _authorizer
    copy = tmp_path / "copy.db"
    shutil.copy(db, copy)
    conn = sqlite3.connect(copy)
    conn.set_authorizer(_authorizer)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM raw_deals")
