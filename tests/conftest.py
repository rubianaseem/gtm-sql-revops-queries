import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gtm_sql.loader import build_database  # noqa: E402
from gtm_sql.queries import run_all  # noqa: E402

AS_OF = "2026-10-31"


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "gtm.db"
    build_database(ROOT / "data", path)
    return path


@pytest.fixture(scope="session")
def results(db):
    return run_all(db, AS_OF)


@pytest.fixture()
def data_copy(tmp_path):
    dst = tmp_path / "data"
    shutil.copytree(ROOT / "data", dst)
    return dst
