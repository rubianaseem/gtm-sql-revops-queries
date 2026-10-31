"""Run one read-only SELECT safely.

Used for SQL you did not write yourself: a query Claude drafted from a
question, or one pasted in with --sql. Three layers, any one of which
would stop a write on its own:

1. Text check: one statement, starts with SELECT or WITH, no write keywords.
2. The database is opened read-only (mode=ro) and query_only is on.
3. An authorizer callback lets SQLite itself refuse anything but reads.
"""
import re
import sqlite3

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|replace(?!\s*\()|attach|detach|pragma|"
    r"vacuum|reindex|analyze|begin|commit|rollback|savepoint|release|load_extension)\b",
    re.IGNORECASE,
)

ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


class UnsafeQuery(ValueError):
    pass


def _strip_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def check_sql(sql):
    """Return the cleaned statement or raise UnsafeQuery with the reason."""
    body = _strip_comments(sql).strip().rstrip(";").strip()
    if not body:
        raise UnsafeQuery("empty query")
    # Ignore semicolons inside string literals before counting statements.
    no_strings = re.sub(r"'([^']|'')*'", "''", body)
    if ";" in no_strings:
        raise UnsafeQuery("only one statement is allowed")
    if not re.match(r"^(select|with)\b", body, re.IGNORECASE):
        raise UnsafeQuery("query must start with SELECT or WITH")
    hit = FORBIDDEN.search(no_strings)
    if hit:
        raise UnsafeQuery(f"keyword not allowed: {hit.group(0).upper()}")
    return body


def _authorizer(action, arg1, arg2, db_name, trigger):
    return sqlite3.SQLITE_OK if action in ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def run_readonly(db_path, sql, params=None, max_rows=200):
    """Run a checked SELECT against db_path. Returns (columns, rows, truncated)."""
    body = check_sql(sql)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_authorizer)
        cur = conn.execute(body, params or {})
        cols = [c[0] for c in cur.description]
        rows = cur.fetchmany(max_rows + 1)
        return cols, rows[:max_rows], len(rows) > max_rows
    except sqlite3.DatabaseError as exc:
        raise UnsafeQuery(f"SQLite refused the query: {exc}") from exc
    finally:
        conn.close()
