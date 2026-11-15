import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

STATE_SCHEMA_VERSION = 1
DEFAULT_STATE_STREAM = "ted-poland-it"
MAX_INCREMENTAL_WINDOW_DAYS = 7
STREAM_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


class StateConflictError(RuntimeError):
    """Raised when another execution advances the state first."""


@dataclass(frozen=True)
class DateWindow:
    since: date
    until: date

    @property
    def days(self) -> int:
        return (self.until - self.since).days + 1


@dataclass(frozen=True)
class PipelineState:
    stream: str
    last_completed_date: date
    last_run_id: str
    updated_at_utc: datetime
    schema_version: int = STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_stream(self.stream)

        if self.schema_version != STATE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported state schema version: {self.schema_version}")

        if not self.last_run_id.strip():
            raise ValueError("State run ID must not be empty")

        if self.updated_at_utc.tzinfo is None:
            raise ValueError("State update timestamp must be timezone-aware")

    def to_json(self) -> bytes:
        payload = {
            "schema_version": self.schema_version,
            "stream": self.stream,
            "last_completed_date": self.last_completed_date.isoformat(),
            "last_run_id": self.last_run_id,
            "updated_at_utc": (self.updated_at_utc.astimezone(UTC).isoformat()),
        }
        return json.dumps(payload, indent=2).encode("utf-8")

    @classmethod
    def from_json(cls, content: bytes) -> "PipelineState":
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("State file is not valid UTF-8 JSON") from error

        if not isinstance(payload, dict):
            raise TypeError("State file must contain a JSON object")

        required = {
            "schema_version",
            "stream",
            "last_completed_date",
            "last_run_id",
            "updated_at_utc",
        }
        missing = required - payload.keys()

        if missing:
            raise ValueError(
                "State file is missing fields: " + ", ".join(sorted(missing))
            )

        try:
            return cls(
                schema_version=int(payload["schema_version"]),
                stream=str(payload["stream"]),
                last_completed_date=date.fromisoformat(
                    str(payload["last_completed_date"])
                ),
                last_run_id=str(payload["last_run_id"]),
                updated_at_utc=datetime.fromisoformat(str(payload["updated_at_utc"])),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("State file contains invalid field values") from error


@dataclass(frozen=True)
class StateSnapshot:
    state: PipelineState | None
    etag: str | None

    def __post_init__(self) -> None:
        if (self.state is None) != (self.etag is None):
            raise ValueError("State and ETag must either both exist or both be absent")


def validate_stream(stream: str) -> None:
    if not STREAM_PATTERN.fullmatch(stream):
        raise ValueError(
            "State stream must be 3-64 lowercase letters, digits or hyphens"
        )


def resolve_incremental_window(
    *,
    snapshot: StateSnapshot,
    requested_since: date | None,
    requested_until: date | None,
    today: date,
    default_window_days: int = 1,
) -> DateWindow:
    if not 1 <= default_window_days <= MAX_INCREMENTAL_WINDOW_DAYS:
        raise ValueError("Default incremental window must contain between 1 and 7 days")

    latest_complete_date = today - timedelta(days=1)

    if snapshot.state is None:
        if requested_since is None:
            raise ValueError("A since date is required to bootstrap durable state")
        since = requested_since
    else:
        expected_since = snapshot.state.last_completed_date + timedelta(days=1)

        if requested_since is not None and requested_since != expected_since:
            raise ValueError(
                "Incremental window must start on "
                f"{expected_since.isoformat()} after the current watermark"
            )

        since = expected_since

    until = requested_until or min(
        since + timedelta(days=default_window_days - 1),
        latest_complete_date,
    )

    if since > latest_complete_date:
        raise ValueError("No completed date is available after the watermark")

    if since > until:
        raise ValueError("since date must not be after until date")

    if until > latest_complete_date:
        raise ValueError("Incremental windows may contain completed days only")

    window = DateWindow(since=since, until=until)

    if window.days > MAX_INCREMENTAL_WINDOW_DAYS:
        raise ValueError("Incremental window must not exceed 7 inclusive days")

    return window


def advance_state(
    *,
    stream: str,
    previous: PipelineState | None,
    window: DateWindow,
    run_id: str,
    now: datetime,
) -> PipelineState:
    validate_stream(stream)

    if previous is not None:
        if previous.stream != stream:
            raise ValueError("Cannot advance a different state stream")

        expected_since = previous.last_completed_date + timedelta(days=1)

        if window.since != expected_since:
            raise ValueError(
                f"State can advance only from {expected_since.isoformat()}"
            )

    if window.since > window.until:
        raise ValueError("Cannot advance state with an invalid date window")

    return PipelineState(
        stream=stream,
        last_completed_date=window.until,
        last_run_id=run_id,
        updated_at_utc=now,
    )
