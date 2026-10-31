import csv
import sqlite3

from conftest import AS_OF
from gtm_sql.loader import build_database
from gtm_sql.queries import run_all


def issues(results, issue):
    return {r["record_id"] for r in results["06_data_quality_audit"] if r["issue"] == issue}


def test_raw_tables_stay_text_and_lookups_are_typed(db):
    conn = sqlite3.connect(db)
    raw = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(raw_deals)")}
    assert raw["amount"] == "TEXT"
    lookup = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(stage_map)")}
    assert lookup["stage_order"] == "INTEGER"


def test_people_view_dedupes_email_case_and_spaces(db):
    conn = sqlite3.connect(db)
    contacts = conn.execute("SELECT COUNT(*) FROM stg_contacts").fetchone()[0]
    people = conn.execute("SELECT COUNT(*) FROM stg_people").fetchone()[0]
    assert contacts - people == 4


def test_stage_map_handles_internal_names_and_casing(db):
    conn = sqlite3.connect(db)
    unmapped = conn.execute("SELECT deal_id FROM stg_deals WHERE stage IS NULL").fetchall()
    assert unmapped == [("D9006",)]  # 'Verbal Commit' is the only stage not in stage_map


def test_currency_conversion(db):
    conn = sqlite3.connect(db)
    usd, = conn.execute("SELECT amount_usd FROM stg_deals WHERE deal_id = 'D9002'").fetchone()
    assert round(usd, 2) == round(55000 * 1.27, 2)
    chf, = conn.execute("SELECT amount_usd FROM stg_deals WHERE deal_id = 'D9004'").fetchone()
    assert chf is None


def test_funnel_counts_furthest_stage_not_current(results):
    funnel = results["01_funnel_conversion"]
    reached = [r["deals_reached"] for r in funnel]
    assert reached == sorted(reached, reverse=True)
    # D9003 is in Demo now but reached Proposal before moving back.
    proposal = next(r for r in funnel if r["stage"] == "Proposal")
    assert proposal["deals_reached"] > proposal["deals_currently_here"]


def test_velocity_counts_backward_moves(results):
    assert sum(r["backward_entries"] for r in results["02_stage_velocity"]) >= 1
    assert all(r["avg_days"] >= 0 for r in results["02_stage_velocity"])


def test_cohort_people_not_records(results, db):
    conn = sqlite3.connect(db)
    people = conn.execute("SELECT COUNT(*) FROM stg_people").fetchone()[0]
    assert sum(r["people"] for r in results["03_lead_to_deal_cohort"]) == people


def test_coverage_keeps_unowned_pipeline_visible(results):
    owners = {r["owner"] for r in results["04_pipeline_coverage"]}
    assert "(no owner)" in owners
    for r in results["04_pipeline_coverage"]:
        if r["quota_usd"] is not None and r["coverage_ratio"] is not None:
            remaining = max(r["quota_usd"] - r["won_usd"], 0)
            if remaining:
                assert abs(r["coverage_ratio"] - r["open_pipeline_usd"] / remaining) < 0.01


def test_data_quality_catches_injected_mess(results):
    assert "D9001" in issues(results, "orphan_deal")
    assert "D9002" in issues(results, "deal_no_owner")
    assert "D9002" in issues(results, "close_date_in_past")
    assert "D9003" in issues(results, "backward_stage_move")
    assert "D9003" in issues(results, "duplicate_history_row")
    assert "D9004" in issues(results, "missing_fx_rate")
    assert "D9005" in issues(results, "negative_or_zero_amount")
    assert "D9006" in issues(results, "unmapped_stage")
    assert {"D9001", "D9002", "D9005"} <= issues(results, "no_stage_history")
    assert {"CO901", "CO902"} <= issues(results, "duplicate_company")
    assert len(issues(results, "duplicate_contact")) == 4
    assert len(issues(results, "unknown_campaign")) == 3


def test_stalled_deal_uses_last_stage_change(results):
    row = next(r for r in results["07_stalled_deals"] if r["deal_id"] == "D9003")
    assert row["stage"] == "Demo"
    assert row["days_in_stage"] == 151  # entered Demo 2026-06-01 10:00, as of 2026-10-31


def test_touch_after_deal_creation_gets_no_credit(data_copy, tmp_path, results):
    """A touch dated after the deal was created must not change attribution."""
    deals = list(csv.DictReader(open(data_copy / "sample_deals.csv")))
    deal = next(d for d in deals if d["primary_contact_id"] and d["deal_id"].startswith("D0"))
    with open(data_copy / "sample_touches.csv", "a", newline="") as f:
        csv.writer(f).writerow(["T99999", deal["primary_contact_id"], "C03", "Event Scan", "2026-10-30 12:00:00"])
    db2 = tmp_path / "late.db"
    build_database(data_copy, db2)
    after = run_all(db2, AS_OF)["05_campaign_attribution"]
    assert after == results["05_campaign_attribution"]
