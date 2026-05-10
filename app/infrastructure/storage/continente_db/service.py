"""Service layer for Continente product tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import repository


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def init_db() -> None:
    repository.init_db()


def ingest_products(rows: list[dict[str, Any]]) -> list[dict]:
    """Upsert product snapshots and return normalized inserted/updated rows."""
    init_db()
    seen_at = _iso_now()
    out: list[dict] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        external_id = str(row.get("external_id") or "").strip() or None
        regular_price = _f(row.get("regular_price"))
        current_price = _f(row.get("current_price"))
        currency = str(row.get("currency") or "EUR").strip().upper() or "EUR"
        product_id = repository.upsert_product(
            external_id=external_id,
            name=name,
            regular_price=regular_price,
            current_price=current_price,
            currency=currency,
            seen_at=seen_at,
        )
        repository.insert_price_history(product_id, seen_at, current_price, regular_price)
        out.append(
            {
                "id": product_id,
                "external_id": external_id,
                "name": name,
                "regular_price": regular_price,
                "current_price": current_price,
                "currency": currency,
                "seen_at": seen_at,
            }
        )
    return out


def list_products() -> list[dict]:
    init_db()
    return repository.list_products()


def vote(product_id: int, delta: int) -> bool:
    init_db()
    if delta not in (-1, 1):
        return False
    return repository.set_vote(product_id, delta)


def set_notify(product_id: int, enabled: bool) -> bool:
    init_db()
    return repository.set_notify_enabled(product_id, enabled)


def product_baseline(product: dict) -> float | None:
    """Baseline regular price; fallback to current price if regular missing."""
    regular = _f(product.get("regular_price"))
    current = _f(product.get("current_price"))
    return regular if regular is not None else current


def should_alert(product: dict) -> bool:
    if not product.get("notify_enabled"):
        return False
    if int(product.get("likes", 0)) <= int(product.get("dislikes", 0)):
        return False
    current = _f(product.get("current_price"))
    baseline = product_baseline(product)
    if current is None or baseline is None:
        return False
    # Alert only for true drops below baseline, not fake promo labels at baseline.
    return current < baseline


def mark_alerted(product_id: int, price: float | None) -> None:
    init_db()
    repository.upsert_alert_state(product_id, price, _iso_now())


def already_alerted_at_price(product_id: int, price: float | None) -> bool:
    init_db()
    st = repository.get_alert_state(product_id)
    if not st:
        return False
    try:
        return float(st.get("last_alert_price")) == float(price)
    except (TypeError, ValueError):
        return st.get("last_alert_price") is None and price is None
