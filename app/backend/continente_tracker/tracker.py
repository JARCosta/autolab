"""Continente polling worker.

Reads authenticated endpoints using headers/cookies from env, normalizes product
rows, stores them in SQLite, and sends Telegram alerts for liked products whose
price goes below baseline regular price.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from app.backend import notifications
from app.infrastructure.storage.continente_db import (
    already_alerted_at_price,
    ingest_products,
    list_products,
    mark_alerted,
    should_alert,
)
from logging_config import setup_logging

log = setup_logging("continente_tracker")


def _session() -> requests.Session:
    s = requests.Session()
    ua = os.getenv("CONTINENTE_USER_AGENT", "").strip()
    if ua:
        s.headers.update({"User-Agent": ua})
    accept = os.getenv("CONTINENTE_ACCEPT", "application/json, text/plain, */*").strip()
    if accept:
        s.headers.update({"Accept": accept})
    cookie = os.getenv("CONTINENTE_COOKIE", "").strip()
    if cookie:
        s.headers.update({"Cookie": cookie})
    extra_raw = os.getenv("CONTINENTE_EXTRA_HEADERS_JSON", "").strip()
    if extra_raw:
        try:
            extra = json.loads(extra_raw)
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if k and v is not None:
                        s.headers[str(k)] = str(v)
        except json.JSONDecodeError:
            log.warning("Invalid CONTINENTE_EXTRA_HEADERS_JSON; ignoring.")
    return s


def _endpoints() -> list[str]:
    raw = os.getenv(
        "CONTINENTE_ENDPOINTS",
        "https://www.continente.pt/on/demandware.store/Sites-continente-Site/default/Cart-GetCustomerBenefits",
    ).strip()
    out = [item.strip() for item in raw.split(",") if item.strip()]
    return out


def _poll_interval_seconds() -> int:
    try:
        sec = int(os.getenv("CONTINENTE_POLL_SECONDS", "1800").strip())
    except ValueError:
        sec = 1800
    return max(60, sec)


def _normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    # Keep normalization permissive so it can absorb shape changes.
    name = (
        item.get("name")
        or item.get("productName")
        or item.get("displayName")
        or item.get("description")
    )
    if not name:
        return None
    external_id = (
        item.get("id")
        or item.get("productId")
        or item.get("sku")
        or item.get("ean")
        or item.get("code")
    )
    price = item.get("price") or item.get("currentPrice") or item.get("salePrice")
    regular = (
        item.get("regularPrice")
        or item.get("basePrice")
        or item.get("pvp")
        or item.get("listPrice")
    )
    currency = item.get("currency") or item.get("currencyCode") or "EUR"
    return {
        "external_id": str(external_id) if external_id is not None else None,
        "name": str(name),
        "current_price": price,
        "regular_price": regular,
        "currency": currency,
    }


def _extract_products(payload: Any) -> list[dict[str, Any]]:
    """Extract products from unknown nested JSON structures."""
    out: list[dict[str, Any]] = []
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            normalized = _normalize_item(node)
            if normalized:
                out.append(normalized)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    stack.append(value)
    return out


def run_once() -> dict:
    s = _session()
    inserted = 0
    endpoints_ok = 0
    for endpoint in _endpoints():
        try:
            r = s.get(endpoint, timeout=30)
            if r.status_code >= 400:
                log.warning("Endpoint returned %s: %s", r.status_code, endpoint)
                continue
            data = r.json()
            rows = _extract_products(data)
            if not rows:
                continue
            inserted_rows = ingest_products(rows)
            inserted += len(inserted_rows)
            endpoints_ok += 1
        except requests.RequestException as exc:
            log.warning("Request failed for %s: %s", endpoint, exc)
        except ValueError:
            log.warning("Non-JSON response for %s", endpoint)

    alerts_sent = 0
    for p in list_products():
        if not should_alert(p):
            continue
        if already_alerted_at_price(int(p["id"]), p.get("current_price")):
            continue
        msg = (
            f"Continente price drop: {p['name']}\n"
            f"Now: {p.get('current_price')} {p.get('currency', 'EUR')} "
            f"(baseline: {p.get('regular_price')})\n"
            f"Votes: +{p.get('likes', 0)} / -{p.get('dislikes', 0)}"
        )
        notifications.send_message_threaded(msg, notification=True, log=False)
        mark_alerted(int(p["id"]), p.get("current_price"))
        alerts_sent += 1

    result = {"inserted": inserted, "alerts_sent": alerts_sent, "sources_ok": endpoints_ok}
    log.info("Continente sync: %s", result)
    return result


def run_forever() -> None:
    interval = _poll_interval_seconds()
    while True:
        try:
            run_once()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.exception("Continente poll loop error: %s", exc)
        time.sleep(interval)
