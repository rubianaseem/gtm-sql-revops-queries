"""SQL on GTM data: load a CRM export, run seven RevOps queries, write a brief.

    python run_queries.py                         # sample data, rules only
    python run_queries.py --data my_export/       # your own CSVs, same file names
    python run_queries.py --sql "SELECT ..."      # run your own read-only query
    python run_queries.py --ask "Which reps ..."  # Claude drafts SQL (needs ANTHROPIC_API_KEY)
"""
import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

from gtm_sql import llm
from gtm_sql.ask import answer, draft_sql
from gtm_sql.brief import findings, review_queue, write_brief
from gtm_sql.guard import UnsafeQuery
from gtm_sql.loader import build_database
from gtm_sql.queries import run_all, write_csv

ROOT = Path(__file__).resolve().parent
SAMPLE_AS_OF = "2026-10-31"  # the sample data is frozen at this date


def print_table(cols, rows, limit=12):
    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            return f"{int(v):,}"
        return str(v)

    rows = [[fmt(v) for v in r] for r in rows[:limit]]
    widths = [min(max([len(c)] + [len(r[i]) for r in rows]), 32) for i, c in enumerate(cols)]
    print("  " + "  ".join(c[:w].ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  " + "  ".join(v[:w].ljust(w) for v, w in zip(r, widths)))


def run_ad_hoc(db, args, as_of):
    if args.ask:
        if not llm.available():
            print("--ask needs ANTHROPIC_API_KEY and the anthropic package. "
                  "Without a key, write the query yourself and pass it with --sql.")
            return 2
        sql = draft_sql(db, args.ask)
        print("Claude drafted:\n\n" + sql + "\n")
    else:
        sql = args.sql
    try:
        cols, rows, truncated = answer(db, sql, as_of)
    except UnsafeQuery as exc:
        print(f"Refused: {exc}")
        return 1
    print_table(cols, rows, limit=25)
    write_csv(Path(args.out) / "ad_hoc_result.csv", [dict(zip(cols, r)) for r in rows], cols)
    print(f"\n{len(rows)} row(s){' (truncated at 200)' if truncated else ''}. Saved to {args.out}/ad_hoc_result.csv")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(ROOT / "data"), help="folder with the CSV exports")
    p.add_argument("--out", default="out", help="output folder")
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD or 'today' (default: sample date, or today with --data)")
    p.add_argument("--no-claude", action="store_true", help="never call Claude, even with a key set")
    p.add_argument("--sql", help="run one read-only SELECT against the loaded data")
    p.add_argument("--ask", help="plain-English question; Claude drafts the SQL")
    args = p.parse_args(argv)

    custom_data = Path(args.data).resolve() != (ROOT / "data").resolve()
    as_of = args.as_of or (date.today().isoformat() if custom_data else SAMPLE_AS_OF)
    if as_of == "today":
        as_of = date.today().isoformat()

    out = Path(args.out)
    db = out / "gtm.db"
    counts = build_database(args.data, db)
    use_claude = llm.available() and not args.no_claude
    print(f"Loaded {counts['raw_contacts']} contacts, {counts['raw_companies']} companies, "
          f"{counts['raw_deals']} deals, {counts['raw_deal_stage_history']} stage changes, "
          f"{counts['raw_touches']} touches into {db}")

    if args.sql or args.ask:
        return run_ad_hoc(db, args, as_of)

    print(f"As of {as_of}. Mode: {'Claude for the brief' if use_claude else 'rules only (no API key)'}\n")
    results = run_all(db, as_of)
    for name, rows in results.items():
        write_csv(out / f"q{name}.csv", rows)

    print("Funnel (from stage history):")
    print_table(["stage", "reached", "now_here", "to_next_%"],
                [[r["stage"], r["deals_reached"], r["deals_currently_here"], r["conversion_to_next_pct"]]
                 for r in results["01_funnel_conversion"]])

    cov = results["04_pipeline_coverage"]
    first_q = min((r["quarter"] for r in cov), default=None)
    print(f"\nCoverage {first_q}:")
    print_table(["owner", "quota_usd", "won_usd", "open_usd", "coverage", "status"],
                [[r["owner"], r["quota_usd"], r["won_usd"], r["open_pipeline_usd"], r["coverage_ratio"], r["status"]]
                 for r in cov if r["quarter"] == first_q])

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    deal_owners = dict(conn.execute(
        "SELECT d.deal_id, COALESCE(o.owner_name, '(no owner)') FROM stg_deals d "
        "LEFT JOIN stg_owners o ON o.owner_id = d.owner_id"))
    conn.close()
    queue = review_queue(results, deal_owners)
    write_csv(out / "review_queue.csv", queue)
    f = findings(results)
    brief, mode = write_brief(f, as_of, use_claude)
    (out / "revops_brief.md").write_text(brief)

    dq = results["06_data_quality_audit"]
    print(f"\nData quality: {len(dq)} issues ({f['dq_high']} high). Top issues:")
    for issue, n in list(f["dq_by_issue"].items())[:6]:
        print(f"  {issue:<26}{n}")
    print(f"\nStalled with no activity: {len(f['stalled_no_activity'])} deals. "
          f"Review queue: {len(queue)} rows. Brief written by: {mode}.")
    print(f"Outputs written to {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
