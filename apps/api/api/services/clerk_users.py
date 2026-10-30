"""Read people's contact details from Clerk.

The database keeps only Clerk user ids (`org_members.clerk_user_id`); email
addresses and phone numbers live in Clerk and are never copied here, so a
change a user makes in Clerk is never stale in CertForge. This is the one
place that asks Clerk's Backend API for them.

It is a data read for staff screens, never part of authorization: a Clerk
outage must not take any permission check with it.
"""

from __future__ import annotations

from typing import Optional

import httpx

CLERK_API_URL = "https://api.clerk.com/v1"
#: Clerk's ceiling for one `GET /users` page.
_PAGE = 100


class ContactsUnavailable(Exception):
    """Clerk could not be asked: no secret key, or the call failed."""


def _primary(items: list[dict], primary_id: Optional[str], field: str) -> Optional[str]:
    for item in items:
        if item.get("id") == primary_id:
            return item.get(field)
    return items[0].get(field) if items else None


def fetch_contacts(user_ids: list[str]) -> dict[str, dict]:
    """`{clerk_user_id: {name, email, phone}}` for the ids Clerk knows.

    An id Clerk has no user for (deleted, or from another instance) is simply
    absent from the result; the caller says so rather than inventing a blank.
    """
    from api.core import config

    if not config.CLERK_SECRET_KEY:
        raise ContactsUnavailable("CLERK_SECRET_KEY is not set on the API")
    ids = list(dict.fromkeys(uid for uid in user_ids if uid))
    if not ids:
        return {}

    found: dict[str, dict] = {}
    try:
        with httpx.Client(timeout=10) as client:
            for start in range(0, len(ids), _PAGE):
                chunk = ids[start:start + _PAGE]
                response = client.get(
                    f"{CLERK_API_URL}/users",
                    params=[("user_id", uid) for uid in chunk] + [("limit", _PAGE)],
                    headers={"Authorization": f"Bearer {config.CLERK_SECRET_KEY}"},
                )
                response.raise_for_status()
                for user in response.json():
                    name = " ".join(
                        part for part in (user.get("first_name"), user.get("last_name")) if part
                    )
                    found[user["id"]] = {
                        "name": name or None,
                        "email": _primary(
                            user.get("email_addresses") or [],
                            user.get("primary_email_address_id"),
                            "email_address",
                        ),
                        "phone": _primary(
                            user.get("phone_numbers") or [],
                            user.get("primary_phone_number_id"),
                            "phone_number",
                        ),
                    }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ContactsUnavailable(f"Clerk did not answer: {exc.__class__.__name__}") from exc
    return found
