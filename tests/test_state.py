from datetime import UTC, date, datetime

import pytest

from tenderscope.orchestration.state import (
    DateWindow,
    PipelineState,
    StateSnapshot,
    advance_state,
    resolve_incremental_window,
)


def make_state(last_completed_date: date) -> PipelineState:
    return PipelineState(
        stream="ted-poland-it",
        last_completed_date=last_completed_date,
        last_run_id="ted_previous",
        updated_at_utc=datetime(2026, 11, 13, 20, 0, tzinfo=UTC),
    )


def test_bootstrap_requires_explicit_since_date():
    with pytest.raises(ValueError, match="required to bootstrap"):
        resolve_incremental_window(
            snapshot=StateSnapshot(state=None, etag=None),
            requested_since=None,
            requested_until=None,
            today=date(2026, 11, 14),
        )


def test_bootstrap_accepts_bounded_historical_window():
    window = resolve_incremental_window(
        snapshot=StateSnapshot(state=None, etag=None),
        requested_since=date(2026, 11, 10),
        requested_until=date(2026, 11, 12),
        today=date(2026, 11, 14),
    )

    assert window == DateWindow(
        since=date(2026, 11, 10),
        until=date(2026, 11, 12),
    )
    assert window.days == 3


def test_existing_state_infers_next_completed_day():
    state = make_state(date(2026, 11, 11))

    window = resolve_incremental_window(
        snapshot=StateSnapshot(state=state, etag='"etag-1"'),
        requested_since=None,
        requested_until=None,
        today=date(2026, 11, 14),
    )

    assert window == DateWindow(
        since=date(2026, 11, 12),
        until=date(2026, 11, 12),
    )


@pytest.mark.parametrize(
    ("since", "message"),
    [
        (date(2026, 11, 11), "must start on 2026-11-12"),
        (date(2026, 11, 13), "must start on 2026-11-12"),
    ],
)
def test_existing_state_rejects_overlap_and_gap(since, message):
    state = make_state(date(2026, 11, 11))

    with pytest.raises(ValueError, match=message):
        resolve_incremental_window(
            snapshot=StateSnapshot(state=state, etag='"etag-1"'),
            requested_since=since,
            requested_until=since,
            today=date(2026, 11, 14),
        )


def test_window_rejects_future_and_more_than_seven_days():
    empty = StateSnapshot(state=None, etag=None)

    with pytest.raises(ValueError, match="completed days only"):
        resolve_incremental_window(
            snapshot=empty,
            requested_since=date(2026, 11, 13),
            requested_until=date(2026, 11, 14),
            today=date(2026, 11, 14),
        )

    with pytest.raises(ValueError, match="must not exceed 7"):
        resolve_incremental_window(
            snapshot=empty,
            requested_since=date(2026, 11, 1),
            requested_until=date(2026, 11, 8),
            today=date(2026, 11, 14),
        )


def test_state_json_round_trip_is_versioned_and_utc():
    original = make_state(date(2026, 11, 11))

    restored = PipelineState.from_json(original.to_json())

    assert restored == original
    assert b'"schema_version": 1' in original.to_json()
    assert restored.updated_at_utc.tzinfo is not None


def test_state_rejects_unknown_schema_version():
    content = make_state(date(2026, 11, 11)).to_json().replace(
        b'"schema_version": 1',
        b'"schema_version": 2',
    )

    with pytest.raises(ValueError, match="invalid field values"):
        PipelineState.from_json(content)


def test_advance_state_records_successful_window():
    previous = make_state(date(2026, 11, 11))
    now = datetime(2026, 11, 14, 20, 0, tzinfo=UTC)

    advanced = advance_state(
        stream="ted-poland-it",
        previous=previous,
        window=DateWindow(
            since=date(2026, 11, 12),
            until=date(2026, 11, 13),
        ),
        run_id="ted_current",
        now=now,
    )

    assert advanced.last_completed_date == date(2026, 11, 13)
    assert advanced.last_run_id == "ted_current"
    assert advanced.updated_at_utc == now


def test_snapshot_requires_state_and_etag_together():
    with pytest.raises(ValueError, match="both exist"):
        StateSnapshot(
            state=make_state(date(2026, 11, 11)),
            etag=None,
        )
