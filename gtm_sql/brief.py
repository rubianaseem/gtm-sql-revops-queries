"""Turn query results into a review queue and a RevOps brief."""
import json
from collections import Counter

from . import llm

SEVERITY_PRIORITY = {"high": 1, "medium": 2, "low": 3}


def review_queue(results, deal_owners=None):
    """Data-quality issues plus stalled deals, one list, highest priority first.

    deal_owners maps deal_id to owner name so every deal row says who to ask.
    """
    stalled = {"stalled, no activity": 1, "over stage limit": 2, "no history": 2}
    owners = dict(deal_owners or {})
    owners.update({r["deal_id"]: r["owner"] for r in results["07_stalled_deals"]})
    rows = []
    for r in results["06_data_quality_audit"]:
        rows.append({
            "priority": SEVERITY_PRIORITY[r["severity"]],
            "source": "data_quality",
            "issue": r["issue"],
            "record_type": r["record_type"],
            "record_id": r["record_id"],
            "owner": owners.get(r["record_id"], ""),
            "detail": r["detail"],
            "suggested_fix": r["suggested_fix"],
        })
    for r in results["07_stalled_deals"]:
        rows.append({
            "priority": stalled[r["status"]],
            "source": "stalled_deals",
            "issue": r["status"].replace(", ", "_").replace(" ", "_"),
            "record_type": "deal",
            "record_id": r["deal_id"],
            "owner": r["owner"],
            "detail": f'{r["deal_name"]}: {r["days_in_stage"]} days in {r["stage"]} '
                      f'(limit {r["max_days_in_stage"]}), last touch {r["days_since_touch"]} days ago',
            "suggested_fix": "Owner confirms next step and date, or closes the deal",
        })
    rows.sort(key=lambda r: (r["priority"], r["source"], r["issue"], r["record_id"]))
    return rows


def findings(results):
    """The small set of facts the brief is written from. Aggregates only."""
    funnel = [r for r in results["01_funnel_conversion"] if r["conversion_to_next_pct"] is not None]
    weakest = min(funnel, key=lambda r: r["conversion_to_next_pct"])
    stage_names = [r["stage"] for r in results["01_funnel_conversion"]]
    next_stage = stage_names[stage_names.index(weakest["stage"]) + 1]
    velocity = results["02_stage_velocity"]
    slowest = max(velocity, key=lambda r: r["avg_days"])
    coverage = results["04_pipeline_coverage"]
    quarters = sorted({r["quarter"] for r in coverage})
    next_q = quarters[0] if quarters else None
    q_rows = [r for r in coverage if r["quarter"] == next_q]
    attribution = results["05_campaign_attribution"]
    top_first = max(attribution, key=lambda r: r["first_touch_pipeline_usd"] or 0)
    top_last = max(attribution, key=lambda r: r["last_touch_pipeline_usd"] or 0)
    dq = results["06_data_quality_audit"]
    stalled = results["07_stalled_deals"]
    cohorts = [r for r in results["03_lead_to_deal_cohort"] if not r["window_incomplete"]]
    return {
        "funnel_weakest_step": {
            "from": weakest["stage"], "to": next_stage, "to_pct": weakest["conversion_to_next_pct"],
            "deals_reached": weakest["deals_reached"],
        },
        "funnel_reached_closed_won": funnel[-1]["deals_reached_next"] if funnel else 0,
        "slowest_stage": {"stage": slowest["stage"], "avg_days": slowest["avg_days"],
                          "max_days": slowest["max_days"]},
        "backward_entries": sum(r["backward_entries"] for r in velocity),
        "coverage_quarter": next_q,
        "coverage": [{"owner": r["owner"], "ratio": r["coverage_ratio"], "status": r["status"],
                      "open_pipeline_usd": r["open_pipeline_usd"]} for r in q_rows],
        "open_pipeline_no_quota_usd": sum(r["open_pipeline_usd"] for r in q_rows if r["quota_usd"] is None),
        "top_first_touch": {"channel": top_first["channel"], "pipeline_usd": top_first["first_touch_pipeline_usd"]},
        "top_last_touch": {"channel": top_last["channel"], "pipeline_usd": top_last["last_touch_pipeline_usd"]},
        "cohort_best": max(cohorts, key=lambda r: r["conversion_pct"]) if cohorts else None,
        "cohort_worst": min(cohorts, key=lambda r: r["conversion_pct"]) if cohorts else None,
        "dq_by_issue": dict(Counter(r["issue"] for r in dq).most_common()),
        "dq_high": sum(r["severity"] == "high" for r in dq),
        "stalled_no_activity": [
            {"deal_id": r["deal_id"], "deal_name": r["deal_name"], "owner": r["owner"],
             "stage": r["stage"], "days_in_stage": r["days_in_stage"], "amount_usd": r["amount_usd"]}
            for r in stalled if r["status"] == "stalled, no activity"
        ],
    }


def _usd(x):
    return f"${x:,.0f}" if x is not None else "n/a"


def rule_brief(f, as_of):
    lines = [f"# RevOps brief, data as of {as_of}", "", "Mode: built-in rules (no API key).", ""]
    lines += ["## Pipeline", ""]
    under = [c for c in f["coverage"] if c["status"] == "under 3x coverage"]
    lines.append(f"- {f['coverage_quarter']} coverage: {len(under)} of "
                 f"{sum(1 for c in f['coverage'] if c['ratio'] is not None)} reps with a quota are under 3x. "
                 + ", ".join(f"{c['owner']} {c['ratio']}x" for c in f["coverage"] if c["ratio"] is not None) + ".")
    if f["open_pipeline_no_quota_usd"]:
        lines.append(f"- {_usd(f['open_pipeline_no_quota_usd'])} of {f['coverage_quarter']} pipeline sits with "
                     "no owner or a deactivated owner, so no rep forecast includes it.")
    w = f["funnel_weakest_step"]
    lines.append(f"- Weakest funnel step: {w['from']} to {w['to']} converts at {w['to_pct']}% "
                 f"({w['deals_reached']} deals reached {w['from']}).")
    s = f["slowest_stage"]
    lines.append(f"- Slowest stage: {s['stage']}, {s['avg_days']} days on average, longest {s['max_days']} days. "
                 f"{f['backward_entries']} stage entries were backward moves.")
    lines += ["", "## Marketing", ""]
    ft, lt = f["top_first_touch"], f["top_last_touch"]
    lines.append(f"- First touch credits {ft['channel']} with the most pipeline ({_usd(ft['pipeline_usd'])}); "
                 f"last touch credits {lt['channel']} ({_usd(lt['pipeline_usd'])}).")
    if ft["channel"] != lt["channel"]:
        lines.append("  The two models disagree, so report both before moving budget.")
    if f["cohort_best"] and f["cohort_worst"]:
        b, wc = f["cohort_best"], f["cohort_worst"]
        lines.append(f"- Lead-to-deal: the {b['cohort_month']} cohort converted best ({b['conversion_pct']}%), "
                     f"{wc['cohort_month']} worst ({wc['conversion_pct']}%). Cohorts under 90 days old are excluded.")
    lines += ["", "## Fix the data first", ""]
    lines.append(f"- {sum(f['dq_by_issue'].values())} data-quality issues, {f['dq_high']} high severity "
                 "(they change a number leadership sees).")
    for issue, n in f["dq_by_issue"].items():
        lines.append(f"  - {issue}: {n}")
    lines += ["", "## Deals to chase this week", ""]
    for d in sorted(f["stalled_no_activity"], key=lambda d: -(d["amount_usd"] or 0))[:5]:
        owner = d["owner"].strip("()")
        lines.append(f"- {d['deal_id']} {d['deal_name']} ({owner}): {d['days_in_stage']} days in "
                     f"{d['stage']}, {_usd(d['amount_usd'])}, no activity in 21+ days.")
    lines += ["", "Full lists: out/review_queue.csv and the q0*.csv files.", ""]
    return "\n".join(lines)


SYSTEM = (
    "You write short weekly RevOps briefs for a VP of Sales and a Head of Marketing. "
    "Use only the numbers in the JSON you are given. Do not invent figures, names or causes. "
    "Plain English, no emojis, no hype. Markdown with the headings: Pipeline, Marketing, "
    "Fix the data first, Deals to chase this week. Under 300 words."
)


def write_brief(f, as_of, use_claude):
    if use_claude:
        try:
            text = llm.complete(SYSTEM, f"Data as of {as_of}.\n\n" + json.dumps(f, indent=2, default=str))
            return f"# RevOps brief, data as of {as_of}\n\nMode: Claude (from aggregated findings only).\n\n{text}\n", "claude"
        except Exception as exc:  # network, auth, rate limit: fall back, never fail the run
            return rule_brief(f, as_of) + f"\nClaude call failed ({type(exc).__name__}); used built-in rules.\n", "rules"
    return rule_brief(f, as_of), "rules"
