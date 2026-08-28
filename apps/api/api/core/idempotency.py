"""Best-effort idempotency for write operations.

WHAT THIS IS NOT
----------------
This store is **in-memory and per-instance**. The Fly machine scales to zero
(`auto_stop_machines = "stop"`, `min_machines_running = 0` in `fly.toml`), so
every entry is lost the moment the machine stops, and a second machine would
never see the first one's entries at all. It therefore **does not guarantee
exactly-once issuance**. It collapses the retry that actually happens in
practice — the client's own immediate retry of a request that timed out, hitting
a warm machine seconds later — and nothing more.

Say that to callers plainly rather than letting `Idempotency-Key` imply a
promise the deployment cannot keep. The legacy surface has exactly the same
property (`_check_idempotency` in `api/index.py`), and CLAUDE.md already
describes both in-memory caches there as "best-effort".

A durable store would need a table with a unique index on
`(org_id, idempotency_key)` and the insert done in the issuing transaction, so
that a concurrent duplicate loses on the constraint rather than on a dict
lookup. That is a real migration and a real change to issuance's transaction
boundaries; it is deliberately not what this is.

REUSABLE AND ORG-SCOPED
-----------------------
The legacy cache keys on the raw client-supplied string, which is fine when
there is one tenant. CertForge is multi-tenant: two organizations picking the
same key (`"batch-1"`, a UUID a client regenerates deterministically, anything)
must not see each other's results. Every entry here is filed under a `scope`
string — for issuance, the org slug — so a lookup can only ever return
something that scope stored.

SAME KEY, DIFFERENT PAYLOAD
---------------------------
Handled by `fingerprint`. If a key is replayed with a payload that does not
match the one it was stored with, `lookup` raises `IdempotencyConflict` rather
than returning the stored result.

The alternative — return the original anyway — is what "idempotency" loosely
suggests, and it is the wrong call here. A key reused with different data is
never a network retry; it is a client bug (a fixed key in a loop, a key derived
from something less unique than the caller thought). Returning the original
silently means the second recipient's credential is never issued and the caller
is handed the first recipient's id as if it were theirs. That failure is
invisible and lands in someone's inbox. A 409 is loud, is what
draft-ietf-httpapi-idempotency-key-header and Stripe both specify, and costs the
caller nothing but a new key.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

#: One hour, matching the legacy cache. Long enough to cover a client's retry
#: budget, short enough that a stale key does not shadow a genuinely new
#: request for the rest of the day.
DEFAULT_TTL_SECONDS = 3600

#: Above this many live entries a `store` sweeps expired ones. A bound, not a
#: policy: normal traffic never gets near it, and a flood of unique keys should
#: cost a sweep rather than unbounded memory.
DEFAULT_MAX_ENTRIES = 10_000


class IdempotencyConflict(Exception):
    """The key was replayed with a different payload. See the module docstring."""

    def __init__(self, scope: str, key: str):
        super().__init__(
            "This Idempotency-Key was already used with a different request body. "
            "Use a new key for a new request."
        )
        self.scope = scope
        self.key = key


@dataclass
class _Entry:
    value: Any
    fingerprint: str
    stored_at: float


def fingerprint(payload: Any) -> str:
    """A stable digest of the request payload, for conflict detection.

    `sort_keys` and `default=str` matter: dict ordering must not make two equal
    payloads look different, and metadata may carry UUIDs or datetimes that
    json cannot serialise on its own.
    """
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class IdempotencyStore:
    """A TTL'd, scope-partitioned cache of completed operation results.

    The clock is injected (`clock=`) so expiry is testable without sleeping —
    tests hand it a callable they advance by hand.

    Guarded by a lock because uvicorn runs handlers on a thread pool and a bare
    dict mutated from several threads can drop writes mid-resize.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.time,
    ):
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = threading.Lock()

    def lookup(self, scope: str, key: str, request_fingerprint: str) -> Optional[Any]:
        """Return the stored result for `(scope, key)`, or None.

        None means "go ahead and do the work" — either nothing was stored, or
        what was stored has expired. Raises `IdempotencyConflict` when an
        unexpired entry exists under a different fingerprint.
        """
        if not key:
            return None
        with self._lock:
            entry = self._entries.get((scope, key))
            if entry is None:
                return None
            if self._clock() - entry.stored_at >= self._ttl:
                # Expired. Drop it so the caller's fingerprint cannot collide
                # with a dead entry, then treat this as a fresh request.
                self._entries.pop((scope, key), None)
                return None
            if entry.fingerprint != request_fingerprint:
                raise IdempotencyConflict(scope, key)
            return entry.value

    def store(self, scope: str, key: str, request_fingerprint: str, value: Any) -> None:
        """Record the result of a completed operation. No-op on an empty key."""
        if not key:
            return
        with self._lock:
            self._entries[(scope, key)] = _Entry(
                value=value,
                fingerprint=request_fingerprint,
                stored_at=self._clock(),
            )
            if len(self._entries) > self._max_entries:
                self._sweep_locked()

    def _sweep_locked(self) -> None:
        cutoff = self._clock() - self._ttl
        for k in [k for k, v in self._entries.items() if v.stored_at <= cutoff]:
            self._entries.pop(k, None)

    def clear(self) -> None:
        """Drop everything. For tests, and for nothing else."""
        with self._lock:
            self._entries.clear()


#: The store credential issuance uses. Module-level because it must outlive a
#: request; see the docstring for exactly how little that guarantees.
issuance_store = IdempotencyStore()
