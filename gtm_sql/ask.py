"""Ask a question in plain English; Claude drafts SQL; the guard runs it read-only."""
import re
import sqlite3

from . import llm
from .guard import run_readonly

SYSTEM = (
    "You write one SQLite SELECT query to answer a RevOps question. "
    "Use only the stg_* views and lookup tables in the schema given. "
    "Use CTEs for readability. Use :as_of for today's date. "
    "Return only the SQL in a ```sql block, nothing else."
)


def schema_text(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE (type='view' AND name LIKE 'stg_%') "
            "OR (type='table' AND name IN ('stage_map','fx_rates','quotas')) ORDER BY name")]
        out = []
        for n in names:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{n}")')]
            out.append(f"{n}({', '.join(cols)})")
        return "\n".join(out)
    finally:
        conn.close()


def extract_sql(text):
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else text).strip()


def draft_sql(db_path, question):
    prompt = f"Schema:\n{schema_text(db_path)}\n\nQuestion: {question}"
    return extract_sql(llm.complete(SYSTEM, prompt, max_tokens=800))


def answer(db_path, sql, as_of, max_rows=200):
    params = {"as_of": as_of} if ":as_of" in sql else None
    return run_readonly(db_path, sql, params=params, max_rows=max_rows)
