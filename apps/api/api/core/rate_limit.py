"""Per-caller rate limiting for the CertForge ``/api/v1`` surface.

Why this exists
---------------
Quota bounds the month; nothing bounded the minute. An API key holder could
issue as fast as the machine allowed, and PDF rendering is the most expensive
thing this process does. ``core/envelope.py`` has mapped 429 to
``"rate_limit_exceeded"`` since the envelope was written -- a label for a
response nothing produced. This module produces it.

Relationship to the legacy limiter
----------------------------------
``api/index.py`` has its own ``_check_rate_limit`` for ``certs.intelliforge.tech``.
That surface is frozen, so this is a port of its *approach*, not a shared
implementation:

* a sliding window of timestamps per bucket;
* the same three response headers, so a client can self-pace;
* the same refusal to trust a caller-supplied ``X-Forwarded-For`` prefix.

What differs is the bucket key. Legacy has no notion of a principal and can
only bind to an IP. Here a caller usually *is* identified, so the bucket
follows the caller rather than the network path they happen to be on:

    api key    ``key:<sha256 of the presented secret>``
    clerk user ``user:<clerk_user_id>``
    anonymous  ``ip:<resolved client ip>``

An API key holder behind a shared NAT is therefore not throttled by a
stranger's traffic, and one key cannot buy more budget by rotating IPs.

Honest limitations
------------------
* **In-memory and per-instance.** There is no shared store. Two Fly machines
  mean two independent budgets, and the machine scales to zero
  (``auto_stop_machines = "stop"``), so every bucket is discarded on a cold
  start. This is best-effort back-pressure -- exactly the caveat the legacy
  limiter carries. It is not a billing control and not a security boundary.
* **Per key, not per org.** Deriving the bucket from the presented secret's
  hash costs no database round trip, so the limiter keeps working when the
  database is down and never doubles the ``api_keys`` lookup (or its
  ``last_used_at`` write) that ``resolve_principal`` already performs. The
  price is that an organization holding several keys gets a budget per key.
  That is a deliberate trade: monthly quota is what bounds an organization,
  and per-key limiting is what bounds a runaway integration.

Wiring
------
This module installs nothing. It is a dependency a route opts into::

    from api.core.rate_limit import rate_limit

    @router.post("/credentials", dependencies=[Depends(rate_limit())])
    async def issue(...): ...

Deliberately not middleware: the expensive routes are a small subset of
``/api/v1``, and a global limiter would spend the same budget on cheap reads
and on the public verification pages.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, Response

from api.core.config import (
    API_V1_RATE_LIMIT,
    API_V1_RATE_WINDOW,
    TRUSTED_PROXY_HOPS,
)

logger = logging.getLogger(__name__)

__all__ = [
    "RateLimitDecision",
    "RateLimiter",
    "bucket_key",
    "client_ip",
    "default_limiter",
    "enforce_rate_limit",
    "rate_limit",
]


# ---------------------------------------------------------------------------
# Who is calling
# ---------------------------------------------------------------------------


def client_ip(request: Request, fallback: str = "unknown") -> str:
    """Resolve the originating client IP.

    ``request.client.host`` is the socket peer, which behind the Vercel -> Fly
    rewrite is the Fly proxy: every customer would land in one bucket.

    Requests arrive as browser -> Vercel edge -> Fly proxy -> uvicorn, and each
    hop appends the address it saw to ``X-Forwarded-For``, so the header reads
    ``"<client>, <vercel-edge>"`` and the caller sits ``TRUSTED_PROXY_HOPS``
    entries from the right. Counting from the *right* is the whole point: a
    caller that prepends its own ``X-Forwarded-For`` only lengthens the chain
    ahead of the entry we read, so it cannot shift itself into a fresh bucket.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if TRUSTED_PROXY_HOPS > 0 and forwarded:
        chain = [part.strip() for part in forwarded.split(",") if part.strip()]
        if chain:
            # Never index past the start: a short chain means fewer real hops
            # than configured (a request that reached Fly directly, say).
            return chain[-min(TRUSTED_PROXY_HOPS, len(chain))]
    return request.client.host if request.client else fallback


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return ""
    return header[7:].strip()


def _key_for_principal(principal) -> str:
    """Bucket key for an already-resolved Principal, or "" if it has no identity."""
    kind = getattr(principal, "kind", None)
    if kind == "api_key":
        key_id = getattr(principal, "api_key_id", None)
        if key_id:
            return f"key-id:{key_id}"
    elif kind == "user":
        user_id = getattr(principal, "clerk_user_id", None)
        if user_id:
            return f"user:{user_id}"
    return ""


def bucket_key(request: Request) -> str:
    """The identity this request's budget is charged to.

    Prefers the principal over the network path, and falls back to the resolved
    client IP when there is no principal to speak of.
    """
    # If something upstream already resolved a principal onto the request,
    # believe it rather than re-deriving one.
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        key = _key_for_principal(principal)
        if key:
            return key

    token = _bearer_token(request)
    if not token:
        return f"ip:{client_ip(request)}"

    from api.core.principal import looks_like_api_key

    if looks_like_api_key(token):
        # The stored form of a key is its SHA-256, so hashing here yields a
        # stable per-key identity without touching the database and without
        # ever holding the raw secret in the bucket table.
        return "key:" + hashlib.sha256(token.encode("utf-8")).hexdigest()

    # A Clerk session token rotates on refresh, so hashing it would hand the
    # caller a fresh bucket every few minutes. Verify it instead -- JWKS is
    # cached in-process, and this costs no database round trip either.
    from api.core.auth import get_optional_user

    try:
        user = get_optional_user(request)
    except Exception:  # pragma: no cover - fails closed onto the IP bucket
        logger.warning("Rate limiter could not resolve a Clerk user; falling back to IP")
        user = None

    if user is not None and user.clerk_user_id:
        return f"user:{user.clerk_user_id}"

    # An unverifiable token is anonymous as far as the budget is concerned.
    # Bucketing it by IP is what keeps a flood of bad credentials from being
    # free.
    return f"ip:{client_ip(request)}"


# ---------------------------------------------------------------------------
# The limiter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitDecision:
    """The outcome of one :meth:`RateLimiter.check` call."""

    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int

    @property
    def headers(self) -> dict[str, str]:
        """The headers the legacy limiter returns, so clients can self-pace.

        ``Retry-After`` is added on refusal only; it is what a well-behaved
        HTTP client actually reads before backing off.
        """
        out = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_seconds),
        }
        if not self.allowed:
            out["Retry-After"] = str(self.reset_seconds)
        return out


@dataclass
class RateLimiter:
    """A sliding-window counter over an in-memory bucket table.

    ``clock`` is injectable purely so the suite can roll a window forward
    without sleeping through it -- a test that waits out 60 seconds is a test
    nobody runs. It defaults to ``time.monotonic`` rather than ``time.time``
    because a wall-clock step (NTP, a suspended machine) must not be able to
    expire or extend a window.
    """

    limit: int = API_V1_RATE_LIMIT
    window: int = API_V1_RATE_WINDOW
    clock: Callable[[], float] = time.monotonic
    _buckets: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list), repr=False
    )

    def check(self, key: str) -> RateLimitDecision:
        """Record a hit against ``key`` and say whether it is allowed.

        A refused request is *not* recorded. Counting rejections would push the
        window forward every time a hammering client retried, so a caller that
        ignored ``Retry-After`` could never get back in.
        """
        if self.limit <= 0:
            # A non-positive limit disables the limiter rather than refusing
            # everything -- an operator who sets 0 means "off", not "closed".
            return RateLimitDecision(True, self.limit, self.limit, self.window)

        now = self.clock()
        bucket = [t for t in self._buckets[key] if now - t < self.window]
        self._buckets[key] = bucket

        if len(bucket) >= self.limit:
            return RateLimitDecision(False, self.limit, 0, self._reset_seconds(bucket, now))

        bucket.append(now)
        return RateLimitDecision(
            True,
            self.limit,
            self.limit - len(bucket),
            self._reset_seconds(bucket, now),
        )

    def _reset_seconds(self, timestamps: list[float], now: float) -> int:
        """Whole seconds until the oldest hit in the bucket ages out."""
        if not timestamps:
            return int(self.window)
        oldest = min(timestamps)
        return max(1, int(math.ceil(self.window - (now - oldest))))

    def reset(self, key: Optional[str] = None) -> None:
        """Forget one bucket, or all of them. For tests and for operator recovery."""
        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)


#: The process-wide limiter. Routes that do not ask for their own share it, so
#: a caller cannot multiply its budget by spreading requests across endpoints.
default_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# The dependency
# ---------------------------------------------------------------------------


def rate_limit(
    limit: Optional[int] = None,
    window: Optional[int] = None,
    limiter: Optional[RateLimiter] = None,
) -> Callable[..., RateLimitDecision]:
    """Build a FastAPI dependency enforcing a budget on the calling principal.

    With no arguments it shares :data:`default_limiter`. Passing ``limit`` or
    ``window`` gives the route its own limiter with its own bucket table, which
    is what you want for a route far more expensive than the rest.

    On success the three ``X-RateLimit-*`` headers are merged onto the response.
    On refusal it raises 429 carrying the same headers plus ``Retry-After``;
    ``index.py``'s HTTPException handler renders that as the ``ApiResponse``
    envelope with ``type: "rate_limit_exceeded"`` for ``/api/v1`` paths.
    """
    if limiter is None:
        if limit is None and window is None:
            limiter = default_limiter
        else:
            limiter = RateLimiter(
                limit=API_V1_RATE_LIMIT if limit is None else limit,
                window=API_V1_RATE_WINDOW if window is None else window,
            )

    def dependency(request: Request, response: Response) -> RateLimitDecision:
        decision = limiter.check(bucket_key(request))
        headers = decision.headers
        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please retry after the window resets.",
                headers=headers,
            )
        response.headers.update(headers)
        return decision

    return dependency


#: Ready-made dependency for the common case, so a route can write
#: ``Depends(enforce_rate_limit)`` without calling the factory.
enforce_rate_limit = rate_limit()

#: Pre-built ``Depends`` for routes that want to read the decision back.
RateLimitDep = Depends(enforce_rate_limit)
