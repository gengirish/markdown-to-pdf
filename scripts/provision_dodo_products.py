#!/usr/bin/env python
"""Create (or re-price) one Dodo product per paid tier, from BILLING_TIERS.

D0 of docs/dodo-payments-integration-plan.md, as a command rather than a
dashboard click-through: the plan table is the only definition of a price, so
the products Dodo bills against are generated from it instead of typed twice.

    export DODO_PAYMENTS_API_KEY=...        # test-mode key unless --live
    python scripts/provision_dodo_products.py            # what it would do
    python scripts/provision_dodo_products.py --apply    # do it
    python scripts/provision_dodo_products.py --apply --live

It prints the `fly secrets set` line to run afterwards. Nothing here writes to
this repo or to Fly — the product ids differ between test and live mode, which
is why they live in env and not in a checked-in literal.

Three deliberate refusals:

* **It never edits a product it did not just create.** A price change on a live
  Dodo product silently re-bills existing subscribers on the new amount at
  their next cycle. A tier whose price moved is reported, with the old and new
  figures, and left alone: migrating subscribers is a decision, not a script.
* **`--live` is separate from the key.** A live key alone still provisions in
  test mode, because the failure this prevents — a real product created while
  someone meant to rehearse — is one you cannot delete your way out of once a
  card has been charged against it.
* **It is keyed off `BILLING_TIERS[...]["listed"]` as well as price.** Scale is
  hand-sold and has no checkout, so it gets no product until it is listed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# A Windows console is cp1252, which has no rupee sign: printing one raises
# UnicodeEncodeError and takes the whole run down mid-report. Amounts are
# written as "INR 1,999.00" for that reason — but the SDK can put a currency
# symbol in an error message too, so the stream is widened as well.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from api.core.config import BILLING_TIERS  # noqa: E402

#: Dodo's own name for what we call a monthly subscription product.
INTERVAL = "Month"


def _client(live: bool):
    try:
        from dodopayments import DodoPayments
    except ImportError:
        sys.exit("dodopayments is not installed — pip install -r apps/api/requirements.txt")

    key = os.environ.get("DODO_PAYMENTS_API_KEY", "").strip()
    if not key:
        sys.exit("DODO_PAYMENTS_API_KEY is not set.")
    return DodoPayments(bearer_token=key, environment="live_mode" if live else "test_mode")


def _sellable() -> list[tuple[str, dict]]:
    """The tiers a customer can buy: priced and on the pricing page."""
    return sorted(
        (
            (key, info)
            for key, info in BILLING_TIERS.items()
            if info["price_paise"] > 0 and info["listed"]
        ),
        key=lambda kv: kv[1]["order"],
    )


def _amount(product) -> int | None:
    """The product's price in paise, from either shape the SDK returns.

    A listing gives `price` as a plain integer; a create gives a price object
    whose own `price` holds the amount. Reading the wrong one silently yields
    None, which would make the drift check below pass on every product.
    """
    price = getattr(product, "price", None)
    if isinstance(price, int):
        return price
    return getattr(price, "price", None)


def _existing(client) -> dict[str, object]:
    """Products already in this Dodo account, keyed by name.

    Name is the only handle we have: the id is what this script is trying to
    discover, and Dodo has no field of ours to match on.
    """
    found = {}
    try:
        products = list(client.products.list())
    except Exception as exc:  # noqa: BLE001 — the SDK's error types vary by version
        if "401" in str(exc) or "Unauthorized" in str(exc):
            sys.exit(
                "Dodo rejected the key (401). A key belongs to one mode: a live key "
                "cannot read test mode, and vice versa. Re-run with --live if this is "
                "a live key, or check the key has not been rotated."
            )
        raise
    for product in products:
        name = getattr(product, "name", None)
        if name:
            found[name] = product
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually create products (default: print the plan)")
    parser.add_argument("--live", action="store_true",
                        help="live mode. Without this, test mode, whatever the key is")
    args = parser.parse_args()

    client = _client(args.live)
    mode = "live_mode" if args.live else "test_mode"
    print(f"Dodo {mode}; {'applying' if args.apply else 'dry run'}\n")

    existing = _existing(client)
    env: dict[str, str] = {}
    repriced: list[str] = []

    for key, info in _sellable():
        name = f"CertForge {info['name']}"
        price = info["price_paise"]
        rupees = price / 100
        found = existing.get(name)

        if found is not None:
            env[key] = found.product_id
            amount = _amount(found)
            if amount is not None and amount != price:
                repriced.append(
                    f"  {name}: Dodo has INR {amount / 100:,.2f}, BILLING_TIERS says INR {rupees:,.2f}"
                )
            print(f"exists  {name:24} {found.product_id}")
            continue

        if not args.apply:
            print(f"create  {name:24} INR {rupees:,.2f}/{INTERVAL.lower()}  (dry run)")
            continue

        created = client.products.create(
            name=name,
            description=info["tagline"],
            tax_category="saas",
            price={
                "type": "recurring_price",
                "currency": "INR",
                "price": price,
                "discount": 0,
                "purchasing_power_parity": False,
                "payment_frequency_count": 1,
                "payment_frequency_interval": INTERVAL,
                "subscription_period_count": 1,
                "subscription_period_interval": INTERVAL,
                # GST is added on top rather than carved out of the price the
                # pricing page prints, which is what BILLING_TIERS means by
                # price_paise.
                "tax_inclusive": False,
            },
        )
        env[key] = created.product_id
        print(f"created {name:24} {created.product_id}  INR {rupees:,.2f}/{INTERVAL.lower()}")

    if repriced:
        print("\nPrice drift — NOT changed here, because editing a live product "
              "re-bills its subscribers:")
        print("\n".join(repriced))

    if env:
        secrets = " ".join(f"DODO_PRODUCT_{tier.upper()}={pid}" for tier, pid in env.items())
        print(f"\nfly secrets set --app certforge-api {secrets}")
        if not args.live:
            print("(test-mode ids — set these locally, not on Fly)")

    missing = [key for key, _ in _sellable() if key not in env]
    if missing and args.apply:
        print(f"\nNo product for: {', '.join(missing)} — checkout will answer 503 for these.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
