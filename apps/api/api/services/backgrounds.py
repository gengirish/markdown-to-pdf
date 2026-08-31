"""Turning a template's stored artwork into the {{background}} a render needs.

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

    if details is None:
        logger.error(
            "Template %s names background asset %s, which does not exist.",
            getattr(template, "id", "?"),
            template.background_asset_id,
        )
        return ""

    asset_id, storage_key, checksum, mime = details

    if not storage_available():
        logger.error(
            "Template %s has a background but object storage is not configured.",
            getattr(template, "id", "?"),
        )
        return ""

    try:
        return _fetch_data_uri(storage_key, checksum, mime)
    except StorageError:
        logger.exception(
            "Could not load background %s for template %s; rendering without it.",
            asset_id,
            getattr(template, "id", "?"),
        )
        return ""


def clear_cache() -> None:
    """Drop the cached images. For tests, and for a deploy that rotates keys.

    Tolerates the memo having been replaced — a test that wants to prove the
    batch hoist works swaps in the uncached function, and clearing a cache that
    is not there is not an error.
    """
    clear = getattr(_fetch_data_uri, "cache_clear", None)
    if clear is not None:
        clear()
