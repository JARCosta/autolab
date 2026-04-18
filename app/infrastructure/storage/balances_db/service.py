"""Service layer for balance refresh/storage workflows."""

from __future__ import annotations

from datetime import datetime, timezone

from . import channels_data, repository


def _fetch_balance_live(channel: str, bettor: str) -> int:
    """Lazy import avoids circular package load (storage ↔ stream_elements)."""
    from app.backend.stream_elements import fetch_balance

    return fetch_balance(channel, bettor)


def _get_bettors_channels() -> tuple[list[str], list[str]]:
    """Bettor ids and active channel names (order matches the balances table)."""
    bettors = channels_data.list_account_ids_ordered()
    channels = channels_data.list_active_channel_names_ordered()
    return bettors, channels


def get_balance_rows_from_cache() -> list[tuple[str, list[tuple[str, int]]]]:
    """Read balance table from latest history row per (channel, bettor)."""
    repository.init_db()
    bettors, channels = _get_bettors_channels()
    by_key = repository.get_balance_values()

    rows: list[tuple[str, list[tuple[str, int]]]] = []
    for channel in channels:
        cells: list[tuple[str, int]] = [(b, by_key.get((channel, b), "—")) for b in bettors]
        rows.append((channel, cells))
    return rows

def record_balance_snapshot(
    channel: str,
    bettor: str,
    balance: int,
    updated_at: str | None = None,
) -> None:
    """Append a balance reading to history (latest row per key is current)."""
    repository.init_db()
    ts = updated_at or repository.iso_utc_now()
    repository.append_balance_snapshot(channel, bettor, balance, ts)


def fetch_and_store_balance(channel: str, bettor: str, min_age_seconds: int = 0) -> int:
    """Fetch live balance for (channel, bettor) and append to history."""
    repository.init_db()
    now = repository.iso_utc_now()
    now_dt = repository.parse_iso_utc(now)

    if min_age_seconds > 0:
        prior = repository.get_balance_snapshots().get((channel, bettor))
        if prior is not None:
            _, prior_ts = prior
            prior_dt = repository.parse_iso_utc(prior_ts)
            if prior_dt is not None:
                age = (now_dt - prior_dt).total_seconds()
                if age < float(min_age_seconds):
                    return prior[0]
    balance = _fetch_balance_live(channel, bettor)
    repository.bulk_refresh_balances([(channel, bettor, balance, now)])
    return balance


def fetch_and_store_balances(min_age_seconds: int = 0) -> list[tuple[str, list[tuple[str, int]]]]:
    """Return list of (channel, [(bettor, balance), ...])."""
    repository.init_db()
    now = repository.iso_utc_now()
    now_dt = repository.parse_iso_utc(now)

    bettors, channels = _get_bettors_channels()
    snapshots = repository.get_balance_snapshots()

    rows_out: list[tuple[str, list[tuple[str, int]]]] = []
    writes: list[tuple[str, str, int, str]] = []
    for channel in channels:
        cells_out: list[tuple[str, int]] = []
        for bettor in bettors:
            prior = snapshots.get((channel, bettor))
            should_fetch = True
            if prior is not None and min_age_seconds > 0:
                _, prior_ts = prior
                prior_dt = repository.parse_iso_utc(prior_ts)
                if prior_dt is not None:
                    age = (now_dt - prior_dt).total_seconds()
                    if age < float(min_age_seconds):
                        should_fetch = False

            if prior is not None and not should_fetch:
                balance = int(prior[0])
            else:
                balance = _fetch_balance_live(channel, bettor)

            writes.append((channel, bettor, balance, now))
            cells_out.append((bettor, balance))
        rows_out.append((channel, cells_out))

    repository.bulk_refresh_balances(writes)
    return rows_out


def get_balance_history_all_pairs(
    *,
    since_iso: str | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """History for every configured (channel, bettor); missing pairs use empty lists."""
    repository.init_db()
    bettors, channels = _get_bettors_channels()
    keys = [(c, b) for c in channels for b in bettors]
    by_key = repository.get_balance_history_batch(
        keys,
        since_iso=since_iso,
    )
    return {c: {b: by_key.get((c, b), []) for b in bettors} for c in channels}
