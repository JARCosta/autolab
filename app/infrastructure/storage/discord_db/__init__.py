"""Discord-related JSON persistence under ``data/`` (file-backed, hand-editable).

For player Elo / W–D–L, use :func:`load_players_document` /
:func:`save_players_document` from ``.repository`` or import them from this
package.
"""

from .repository import (
    ensure_boost_data_dir,
    load_players_document,
    save_players_document,
)

__all__ = [
    "ensure_boost_data_dir",
    "load_players_document",
    "save_players_document",
]
