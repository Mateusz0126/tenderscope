
from datetime import date

import pytest

from tenderscope.ingestion.ted_api import build_query, resolve_date_window


def test_build_query():
    query = build_query(date(2026, 10, 1))

    assert "buyer-country=POL" in query
    assert "classification-cpv=72*" in query
    assert "publication-date>=20261001" in query
    assert "SORT BY publication-date DESC" in query


def test_build_query_with_closed_date_window():
    query = build_query(
        date(2026, 11, 1),
        date(2026, 11, 7),
    )

    assert "publication-date>=20261101" in query
    assert "publication-date<=20261107" in query


def test_build_query_rejects_reversed_date_window():
    with pytest.raises(
        ValueError,
        match="since date must not be after until date",
    ):
        build_query(date(2026, 11, 8), date(2026, 11, 7))


def test_resolve_date_window_uses_default_lookback():
    since, until = resolve_date_window(
        since=None,
        until=None,
        today=date(2026, 11, 14),
    )

    assert since == date(2026, 9, 30)
    assert until is None


def test_resolve_date_window_preserves_explicit_bounds():
    since, until = resolve_date_window(
        since=date(2026, 11, 1),
        until=date(2026, 11, 7),
        today=date(2026, 11, 14),
    )

    assert since == date(2026, 11, 1)
    assert until == date(2026, 11, 7)
