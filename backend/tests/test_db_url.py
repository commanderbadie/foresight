import pytest

from app.db.session import _engine_url


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_postgres_urls_use_psycopg_v3(scheme):
    url = _engine_url(f"{scheme}://demo:secret@db.example.test:5432/foresight")

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "demo"
    assert url.password == "secret"
    assert url.database == "foresight"


def test_sqlite_database_url_is_unchanged():
    assert _engine_url("sqlite:///./foresight.db").drivername == "sqlite"
