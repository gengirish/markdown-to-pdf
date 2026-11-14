"""Whether CertForge may call the email provider right now.

The provider has a daily send limit (AgentMail: 100 a day on the current
plan, `window: daily`). Once it refuses one send for volume, every further
send that day will be refused too, and each refusal used to cost the
credential one of its three delivery attempts. On 2026-11-12 a batch of 86
sent 39, then made 44 refused calls and 44 more refused retries.

So the first refusal closes this gate until the limit is expected to reset,
and `deliver_credential_email` checks it before every send. A closed gate
defers the row without calling the provider. That is what lets a batch larger
than the day's allowance send what it can and queue the rest, without any
forecast of how much allowance is left, which we cannot know: the legacy
surface sends from the same account and records nothing.

Reads and writes go through the caller's session, so the pause commits with
the rows it deferred and no second connection competes for the database.
A per-process memo spares a 500-row batch 500 reads.

The legacy sender in index.py is not wired to this gate. It is frozen, and it
keeps drawing on the same allowance; that is accepted.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from api.models.email_send_pause import EmailSendPause

logger = logging.getLogger(__name__)

PROVIDER = "agentmail"

#: How long a "not paused" answer is trusted before the table is read again.
#: A pause written by this process is seen at once regardless (the memo is
#: updated on write); this only bounds how stale another machine's pause can be.
MEMO_SECONDS = 10

#: Added to the provider's reset time. Its clock and ours differ, and a send
#: one second early is a refused send that re-closes the gate for a day.
RESET_SLACK = timedelta(minutes=5)

_memo_until: Optional[datetime] = None
_memo_checked_at: Optional[datetime] = None


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes where Postgres keeps the zone."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def next_daily_reset(now: datetime) -> datetime:
    """The fallback when the provider names no reset time: next midnight UTC.

    The one production 429 we hold (tests/test_email_rate_limit.py) carried
    `retry-after: 52642`, which is midnight UTC counted from 09:22 UTC, and the
    2026-11-12 batch was refused from 09:13 UTC. The provider's own header
    wins whenever it is present.
    """
    tomorrow = (now + timedelta(days=1)).date()
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc)


def resume_at(now: datetime, retry_after: Optional[timedelta]) -> datetime:
    """When a send refused now may be tried again."""
    base = now + retry_after if retry_after is not None else next_daily_reset(now)
    return base + RESET_SLACK


def paused_until(session: Optional[Session], now: Optional[datetime] = None) -> Optional[datetime]:
    """The time sending resumes, or None if the gate is open."""
    global _memo_until, _memo_checked_at
    now = now or datetime.now(timezone.utc)

    if _memo_until is not None and _memo_until > now:
        return _memo_until
    fresh = _memo_checked_at is not None and (now - _memo_checked_at).total_seconds() < MEMO_SECONDS
    if fresh or session is None:
        return None

    row = session.get(EmailSendPause, PROVIDER)
    until = _aware(row.paused_until) if row is not None else None
    _memo_checked_at = now
    _memo_until = until if until is not None and until > now else None
    return _memo_until


def pause(session: Optional[Session], until: datetime, reason: str) -> None:
    """Close the gate until `until`. Never shortens an existing pause: two
    refusals racing must not let the earlier estimate win."""
    global _memo_until, _memo_checked_at
    until = _aware(until)
    if _memo_until is None or until > _memo_until:
        _memo_until = until
    _memo_checked_at = datetime.now(timezone.utc)

    if session is None:
        return
    row = session.get(EmailSendPause, PROVIDER)
    if row is None:
        session.add(EmailSendPause(
            provider=PROVIDER, paused_until=until, reason=reason[:500],
            updated_at=datetime.now(timezone.utc),
        ))
        # Flushed so a second pause in the same transaction finds this row
        # instead of inserting a duplicate key: session.get does not see a
        # pending object, and these sessions do not autoflush.
        session.flush()
        logger.warning("Email sending paused until %s: %s", until.isoformat(), reason)
    elif _aware(row.paused_until) < until:
        row.paused_until = until
        row.reason = reason[:500]
        row.updated_at = datetime.now(timezone.utc)
        logger.warning("Email sending paused until %s: %s", until.isoformat(), reason)


def reset_memo() -> None:
    """Forget the in-process answer. Tests, and nothing else."""
    global _memo_until, _memo_checked_at
    _memo_until = None
    _memo_checked_at = None
