"""Read/write helpers for Wallapop tracker CSV files."""

from __future__ import annotations

import os

import paths


def _ensure_wallapop_dir() -> None:
    os.makedirs(paths.WALLAPOP_DIR, exist_ok=True)


def read_search_term_lines() -> list[str]:
    _ensure_wallapop_dir()
    if not os.path.exists(paths.WALLAPOP_SEARCH_TERMS_FILE):
        return []
    with open(paths.WALLAPOP_SEARCH_TERMS_FILE, "r", encoding="utf-8") as f:
        return f.readlines()


def write_search_term_lines(lines: list[str]) -> None:
    _ensure_wallapop_dir()
    with open(paths.WALLAPOP_SEARCH_TERMS_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def read_data_lines() -> list[str]:
    _ensure_wallapop_dir()
    if not os.path.exists(paths.WALLAPOP_DATA_FILE):
        return []
    with open(paths.WALLAPOP_DATA_FILE, "r", encoding="utf-8") as f:
        return f.readlines()


def save_data_backup(lines: list[str]) -> None:
    _ensure_wallapop_dir()
    backup_path = os.path.join(paths.WALLAPOP_DIR, "data.old.csv")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def write_data_lines(lines: list[str]) -> None:
    _ensure_wallapop_dir()
    with open(paths.WALLAPOP_DATA_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
