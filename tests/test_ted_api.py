
from datetime import date

from tenderscope.ingestion.ted_api import build_query


def test_build_query():
    query = build_query(date(2026, 10, 1))

    assert "buyer-country=POL" in query
    assert "classification-cpv=72*" in query
    assert "publication-date>=20261001" in query
    assert "SORT BY publication-date DESC" in query
