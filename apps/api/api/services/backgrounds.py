"""Turning stored images into the data URIs a render needs.

Two of them now: a template's artwork ({{background}}) and an organization's
logo ({{logo_url}}). One module, because they are one concern — an asset row
becomes base64 in the variables dict — and because sharing the memo means the
same bytes are not fetched and encoded twice.

The renderer cannot fetch anything: `_pdf_link_callback` refuses every scheme
and every path outside the bundled fonts directory, because a template author
who could make the server fetch a URL could make it fetch an internal one. So
the image has to arrive as a `data:` URI in the variables dict, like {{qr}}.

The cache is keyed on the asset's **checksum**, not its id. An id whose bytes
were replaced would otherwise serve the old image forever, and the checksum is
already recorded for exactly this kind of question.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache

from api.core.storage import StorageError, get_object, storage_available

logger = logging.getLogger(__name__)

#: Each entry is roughly 1 MB of base64 (~1.3 MB resident). The worker lives as
#: long as the machine, so an unbounded cache here is a leak that only shows up
#: for the customer with the most templates.
_CACHE_SIZE = 8


@lru_cache(maxsize=_CACHE_SIZE)
def _fetch_data_uri(storage_key: str, checksum: str, mime: str) -> str:
    """Fetch and encode. `checksum` participates in the cache key only."""
    raw = get_object(storage_key)
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def _asset_data_uri(details, *, owner: str, what: str) -> str:
    """Fetch and encode one asset, or "" with a logged reason.

    `details` is a plain tuple read out of the ORM, never a live instance — see
    the note in background_data_uri about detached rows.

    Never raises. A missing image renders the certificate without it, which is
    wrong but legible; raising would fail a whole batch over decoration, and the
    credential is the thing that has to exist. Every failure logs at ERROR
    because none of them is normal.
    """
    if details is None:
        logger.error("%s names a %s asset that does not exist.", owner, what)
        return ""

    asset_id, storage_key, checksum, mime = details

    if not storage_available():
        logger.error("%s has a %s but object storage is not configured.", owner, what)
        return ""

    try:
        return _fetch_data_uri(storage_key, checksum, mime)
    except StorageError:
        logger.exception(
            "Could not load %s %s for %s; rendering without it.", what, asset_id, owner
        )
        return ""


def _asset_details(asset_id, loaded=None):
    """(id, storage_key, checksum, mime) for an asset, or None.

    Prefers an already-loaded relationship so the common path does no query.
    """
    if loaded is not None:
        return (loaded.id, loaded.storage_key, loaded.checksum, loaded.mime)

    from api.models import get_db
    from api.models.template_asset import TemplateAsset

    with get_db() as session:
        row = session.query(TemplateAsset).filter_by(id=asset_id).first()
        return (row.id, row.storage_key, row.checksum, row.mime) if row else None


def logo_data_uri(org) -> str:
    """The data URI for an organization's uploaded logo, or "" when it has none.

    `org.logo_url` is deliberately NOT a fallback here. It is an external URL,
    and the renderer refuses to fetch one — returning it would put the exact
    `<img src="https://…">` back into the PDF that never rendered and never
    reported why. Empty is the honest answer: this org has no logo the renderer
    can draw.
    """
    if org is None or getattr(org, "logo_asset_id", None) is None:
        return ""

    return _asset_data_uri(
        _asset_details(org.logo_asset_id, getattr(org, "logo_asset", None)),
        owner=f"Organization {getattr(org, 'slug', '?')}",
        what="logo",
    )


def background_data_uri(template) -> str:
    """The data URI for a template's artwork, or "" when it has none.

    Returns "" rather than raising when the object cannot be read. A missing
    background renders the certificate without its artwork, which is wrong but
    legible; raising would fail the whole batch, and the credential — the thing
    that has to exist — does not depend on the picture behind it. The failure
    is logged at ERROR because it is never normal.
    """
    if template is None or getattr(template, "background_asset_id", None) is None:
        return ""

    # Read into plain values, never held as an ORM instance past its session.
    # A Template loaded in one request and read in another is detached, and
    # touching a column on it then raises DetachedInstanceError from inside the
    # renderer — a failure that looks like a PDF bug and is not one.
    asset = getattr(template, "background_asset", None)
    if asset is not None:
        details = (asset.id, asset.storage_key, asset.checksum, asset.mime)
    else:
        from api.models import get_db
        from api.models.template_asset import TemplateAsset

        with get_db() as session:
            row = (
                session.query(TemplateAsset)
                .filter_by(id=template.background_asset_id)
                .first()
            )
            details = (
                (row.id, row.storage_key, row.checksum, row.mime) if row else None
            )

    return _asset_data_uri(
        details, owner=f"Template {getattr(template, 'id', '?')}", what="background"
    )


def clear_cache() -> None:
    """Drop the cached images. For tests, and for a deploy that rotates keys.

    Tolerates the memo having been replaced — a test that wants to prove the
    batch hoist works swaps in the uncached function, and clearing a cache that
    is not there is not an error.
    """
    clear = getattr(_fetch_data_uri, "cache_clear", None)
    if clear is not None:
        clear()
