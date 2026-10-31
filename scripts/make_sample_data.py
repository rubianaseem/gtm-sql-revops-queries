"""Rebuild the sample CRM export in data/.

The data is fake but shaped like a real HubSpot or Salesforce export, mess
included. A fixed seed means every run produces the same files, so the
tests and the README example stay stable.

    python scripts/make_sample_data.py
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

random.seed(42)
DATA = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 10, 31)

OWNERS = [
    ("O1", "Maya Patel", "maya.patel@example.com", "AE", "EMEA", "active"),
    ("O2", "Jordan Lee", "jordan.lee@example.com", "AE", "NA", "active"),
    ("O3", "Sam Okafor", "sam.okafor@example.com", "AE", "NA", "active"),
    ("O4", "Elena Rossi", "elena.rossi@example.com", "AE", "EMEA", "active"),
    ("O5", "Chris Wong", "chris.wong@example.com", "AE", "APAC", "deactivated"),
    ("O6", "Aisha Khan", "aisha.khan@example.com", "SDR", "EMEA", "active"),
]
QUOTAS = {"O1": 150000, "O2": 120000, "O3": 110000, "O4": 90000}

# Raw stage values as they appear in exports: HubSpot internal names,
# labels, and the odd hand-typed variant from an old import.
STAGES = ["Discovery", "Qualified", "Demo", "Proposal", "Negotiation"]
RAW_VARIANTS = {
    "Discovery": ["appointmentscheduled", "Discovery", "discovery "],
    "Qualified": ["qualifiedtobuy", "Qualified"],
    "Demo": ["presentationscheduled", "Demo", "DEMO"],
    "Proposal": ["decisionmakerboughtin", "Proposal"],
    "Negotiation": ["contractsent", "Negotiation"],
    "Closed Won": ["closedwon", "Closed Won", "closed won"],
    "Closed Lost": ["closedlost", "Closed Lost"],
}

# How long a deal can sit in a stage before it counts as stalled.
MAX_DAYS = {"Discovery": 21, "Qualified": 21, "Demo": 30, "Proposal": 30, "Negotiation": 45}

COMPANY_NAMES = [
    "Northwind Logistics", "Brightpath Health", "Quill Analytics", "Lumen AI",
    "Acme Corp", "Orbit Devices", "Harbor Freight Tech", "Juniper Labs",
    "Cobalt Systems", "Riverstone Bank", "Atlas Robotics", "Fernhill Retail",
    "Kestrel Security", "Maple Learning", "Nimbus Cloud", "Oakridge Pharma",
    "Pioneer Energy", "Quartz Media", "Redwood Insurance", "Summit Travel",
    "Tidal Foods", "Umbra Games", "Vertex Legal", "Willow Telecom",
    "Xeno Biotech", "Yarrow Fashion", "Zephyr Mobility", "Granite Build",
    "Helix Software", "Ivory Hotels", "Jasper Payments", "Krypton Chips",
    "Lattice HR", "Meridian Ports", "Nova Fintech", "Onyx Mining",
]
COUNTRIES = ["GB", "US", "US", "DE", "FR", "US", "GB", "SG", "AU", "US"]
INDUSTRIES = ["Software", "Healthcare", "Financial Services", "Retail",
              "Manufacturing", "Logistics", "Media"]

CAMPAIGNS = [
    # campaign_id, name, channel, utm_source, utm_medium, cost, currency
    ("C01", "2026-Q1 Paid Search Brand", "Paid Search", "google", "cpc", 18000, "USD"),
    ("C02", "2026-Q1 LinkedIn ABM", "Paid Social", "linkedin", "paid_social", 24000, "USD"),
    ("C03", "RevOps Summit London 2026", "Events", "event", "offline", 30000, "GBP"),
    ("C04", "Pipeline Webinar Series", "Webinar", "hubspot", "email", 4000, "USD"),
    ("C05", "SEO Organic", "Organic Search", "google", "organic", 0, "USD"),
    ("C06", "Partner Referral Programme", "Partner", "partner", "referral", 9000, "EUR"),
    ("C07", "Outbound SDR Sequences", "Outbound", "outreach", "email", 12000, "USD"),
    ("C08", "linkedin abm q1", "paid social", "LinkedIn", "Paid_Social", 0, "usd"),
]
TOUCH_TYPES = ["Form Fill", "Webinar Attended", "Ad Click", "Email Click",
               "Event Scan", "Meeting Booked", "Sequence Reply"]
FIRST = ["Priya", "Tom", "Ana", "Jo", "Sam", "Li", "Ben", "Omar", "Grace",
         "Hiro", "Lena", "Marco", "Nia", "Owen", "Rosa", "Tariq", "Uma",
         "Victor", "Wen", "Zara", "Felix", "Ines", "Karl", "Mei"]
LAST = ["Shah", "Brown", "Silva", "Nguyen", "Muller", "Chen", "Adeyemi",
        "Garcia", "Kowalski", "Tanaka", "Fischer", "Rossi", "Okoro", "Evans"]


def d(x):
    return x.isoformat()


def rand_date(start, end):
    return start + timedelta(days=random.randint(0, (end - start).days))


def write(name, header, rows):
    with open(DATA / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    DATA.mkdir(exist_ok=True)
    write("sample_owners.csv",
          ["owner_id", "owner_name", "email", "role", "region", "status"], OWNERS)

    quotas = []
    for oid, q in QUOTAS.items():
        for qtr, mult in [("2026-Q4", 1.0), ("2027-Q1", 1.1)]:
            quotas.append((oid, qtr, int(q * mult)))
    write("sample_quotas.csv", ["owner_id", "quarter", "quota_usd"], quotas)

    write("sample_fx_rates.csv", ["currency", "rate_to_usd"],
          [("USD", 1.0), ("GBP", 1.27), ("EUR", 1.08), ("AUD", 0.66), ("SGD", 0.74)])

    stage_map = []
    for stage, raws in RAW_VARIANTS.items():
        order = (STAGES.index(stage) + 1) if stage in STAGES else (6 if stage == "Closed Won" else 0)
        for raw in raws:
            stage_map.append((raw.strip().lower(), stage, order,
                              int(stage.startswith("Closed")), int(stage == "Closed Won"),
                              MAX_DAYS.get(stage, "")))
    seen, sm = set(), []
    for r in stage_map:
        if r[0] not in seen:
            seen.add(r[0]); sm.append(r)
    write("stage_map.csv", ["raw_value", "stage", "stage_order", "is_closed", "is_won",
                           "max_days_in_stage"], sm)

    write("sample_campaigns.csv",
          ["campaign_id", "campaign_name", "channel", "utm_source", "utm_medium", "cost", "currency"],
          CAMPAIGNS)

    # Companies: one duplicate by name casing, one with no domain.
    companies = []
    for i, name in enumerate(COMPANY_NAMES, start=1):
        dom = name.split()[0].lower() + ".com"
        companies.append((f"CO{i:03d}", name, dom, random.choice(INDUSTRIES),
                          random.choice(COUNTRIES), random.choice([25, 80, 200, 450, 1200, 5000])))
    companies.append(("CO901", "ACME corp", "acme.com", "Manufacturing", "US", 1200))
    companies.append(("CO902", "Juniper Labs Ltd", "", "Software", "GB", 80))
    write("sample_companies.csv",
          ["company_id", "company_name", "domain", "industry", "country", "employees"], companies)

    # Contacts
    contacts = []
    cid = 1
    for co in companies[:len(COMPANY_NAMES)]:
        for _ in range(random.randint(4, 9)):
            fn, ln = random.choice(FIRST), random.choice(LAST)
            created = rand_date(date(2025, 10, 1), date(2026, 10, 20))
            owner = random.choice(["O1", "O2", "O3", "O4", "O6", "O1", "O2", ""])
            stage = random.choice(["lead", "Lead", "marketingqualifiedlead", "MQL",
                                   "salesqualifiedlead", "opportunity", "customer", "subscriber"])
            email = f"{fn}.{ln}{cid}@{co[2]}".lower()
            contacts.append([f"CT{cid:04d}", email, fn, ln, co[0], owner, stage, d(created)])
            cid += 1
    # Injected mess: duplicates by email case and whitespace.
    dup_sources = [contacts[3], contacts[40], contacts[77], contacts[150]]
    for src in dup_sources:
        e = src[1]
        user, dom = e.split("@")
        dup_email = random.choice([user.title() + "@" + dom.upper(), " " + e.upper(), e + " "])
        created = date.fromisoformat(src[7]) + timedelta(days=random.randint(3, 60))
        created = min(created, AS_OF)
        contacts.append([f"CT{cid:04d}", dup_email, src[2], src[3], src[4], "", "Lead", d(created)])
        cid += 1
    # Contact with no company and no owner.
    contacts.append([f"CT{cid:04d}", "freelancer@gmail.com", "Kim", "Park", "", "", "lead", "2026-09-02"])
    cid += 1
    write("sample_contacts.csv",
          ["contact_id", "email", "first_name", "last_name", "company_id", "owner_id",
           "lifecycle_stage", "created_date"], contacts)

    # Campaign touches before and after deal creation.
    touches = []
    tid = 1
    for c in contacts:
        created = date.fromisoformat(c[7])
        for _ in range(random.randint(0, 4)):
            camp = random.choice(["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C02", "C05"])
            when = rand_date(created - timedelta(days=30), min(created + timedelta(days=150), AS_OF))
            touches.append([f"T{tid:05d}", c[0], camp, random.choice(TOUCH_TYPES),
                            datetime.combine(when, datetime.min.time()).replace(hour=random.randint(8, 18)).isoformat(sep=" ")])
            tid += 1
    # Touches pointing at a campaign that does not exist (deleted or typo).
    for c in contacts[10:13]:
        touches.append([f"T{tid:05d}", c[0], "C99", "Form Fill", c[7] + " 10:00:00"])
        tid += 1
    write("sample_touches.csv", ["touch_id", "contact_id", "campaign_id", "touch_type", "touched_at"], touches)

    # Deals and stage history
    deals, history, deal_contacts = [], [], []
    hid = 1
    contacts_by_co = {}
    for c in contacts:
        contacts_by_co.setdefault(c[4], []).append(c)
    did = 1
    for co in companies[:len(COMPANY_NAMES)]:
        for _ in range(random.choice([1, 2, 2, 3, 3, 4])):
            cts = [c for c in contacts_by_co.get(co[0], []) if c[0] < "CT9"]
            primary = random.choice(cts)
            created = date.fromisoformat(primary[7]) + timedelta(days=random.randint(5, 90))
            if created > AS_OF - timedelta(days=3):
                created = AS_OF - timedelta(days=random.randint(5, 40))
            owner = random.choice(["O1", "O2", "O3", "O4", "O1", "O2", "O3", "O4", "O5", ""])
            pipeline = random.choice(["New Business"] * 4 + ["Renewal"])
            currency = {"GB": "GBP", "DE": "EUR", "FR": "EUR", "AU": "AUD", "SG": "SGD"}.get(co[4], "USD")
            amount = random.choice([8, 12, 18, 25, 32, 45, 60, 85, 120]) * 1000
            # Walk the stages forward with a chance of stalling, losing, or going backward.
            t = created
            path = []
            idx = 0
            outcome = None
            while True:
                path.append((STAGES[idx], t))
                dwell = random.randint(3, 35)
                t2 = t + timedelta(days=dwell)
                if t2 >= AS_OF:
                    break
                r = random.random()
                if r < 0.18:
                    outcome = "Closed Lost"; path.append((outcome, t2)); break
                if r < 0.24 and idx > 0:
                    idx -= 1  # backward move, e.g. rep re-opens discovery
                elif r < 0.30:
                    break  # stalls in this stage
                elif idx == len(STAGES) - 1:
                    outcome = "Closed Won"; path.append((outcome, t2)); break
                else:
                    idx += 1
                t = t2
            current_stage = path[-1][0]
            closed = outcome is not None
            close_date = path[-1][1] if closed else rand_date(AS_OF - timedelta(days=20), date(2027, 3, 25))
            raw_stage = random.choice(RAW_VARIANTS[current_stage])
            cur_txt = random.choice([currency, currency, currency.lower(), ""]) if currency != "USD" else random.choice(["USD", "USD", "usd", ""])
            deal_id = f"D{did:04d}"
            deals.append([deal_id, f"{co[1]} - {pipeline}", co[0], owner, pipeline, raw_stage,
                          amount, cur_txt, d(created), d(close_date), primary[0]])
            deal_contacts.append((deal_id, primary[0]))
            for stage, when in path:
                history.append([f"H{hid:05d}", deal_id, random.choice(RAW_VARIANTS[stage]),
                                datetime.combine(when, datetime.min.time()).replace(hour=random.randint(8, 18)).isoformat(sep=" ")])
                hid += 1
            did += 1

    # Hand-built edge cases the tests rely on.
    deals.append(["D9001", "Ghost Co - New Business", "CO999", "O2", "New Business", "Proposal",
                  40000, "USD", "2026-07-01", "2026-12-15", ""])                       # orphan company
    deals.append(["D9002", "Lumen AI - Expansion", "CO004", "", "New Business", "contractsent",
                  55000, "GBP", "2026-06-10", "2026-09-30", "CT0020"])                  # no owner, close date passed
    deals.append(["D9003", "Atlas Robotics - New Business", "CO011", "O1", "New Business", "Demo",
                  70000, "EUR", "2026-04-02", "2026-11-28", ""])                        # backward move, stalled
    for raw, ts in [("appointmentscheduled", "2026-04-02 09:00:00"), ("qualifiedtobuy", "2026-04-20 11:00:00"),
                    ("decisionmakerboughtin", "2026-05-15 15:00:00"), ("presentationscheduled", "2026-06-01 10:00:00"),
                    ("presentationscheduled", "2026-06-01 10:00:00")]:                  # duplicate history row
        history.append([f"H{hid:05d}", "D9003", raw, ts]); hid += 1
    deals.append(["D9004", "Nova Fintech - New Business", "CO035", "O3", "New Business", "Negotiation",
                  90000, "CHF", "2026-08-01", "2026-12-20", ""])                        # currency with no FX rate
    for raw, ts in [("Discovery", "2026-08-01 09:00:00"), ("Qualified", "2026-08-12 09:00:00"),
                    ("Demo", "2026-08-25 09:00:00"), ("Proposal", "2026-09-10 09:00:00"),
                    ("Negotiation", "2026-10-01 09:00:00")]:
        history.append([f"H{hid:05d}", "D9004", raw, ts]); hid += 1
    deals.append(["D9005", "Quill Analytics - New Business", "CO003", "O4", "New Business", "Closed Won",
                  -15000, "USD", "2026-05-01", "2026-08-15", ""])                       # negative amount, no history
    deals.append(["D9006", "Fernhill Retail - New Business", "CO012", "O4", "New Business", "Verbal Commit",
                  30000, "GBP", "2026-09-01", "2026-11-30", ""])                        # stage missing from stage map
    history.append([f"H{hid:05d}", "D9006", "Verbal Commit", "2026-10-05 12:00:00"]); hid += 1

    write("sample_deals.csv",
          ["deal_id", "deal_name", "company_id", "owner_id", "pipeline", "deal_stage", "amount",
           "currency", "create_date", "close_date", "primary_contact_id"], deals)
    write("sample_deal_stage_history.csv", ["history_id", "deal_id", "deal_stage", "changed_at"], history)
    print(f"Wrote {len(companies)} companies, {len(contacts)} contacts, {len(deals)} deals, "
          f"{len(history)} stage changes, {len(touches)} touches to {DATA}")


if __name__ == "__main__":
    main()
