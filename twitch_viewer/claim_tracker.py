from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s" if sec else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return f"{hours}h{minutes}m"
    return f"{hours}h"


@dataclass
class ClaimTracker:
    default_live_window_seconds: int = 15 * 60
    max_samples: int = 12
    last_boost_at: dt.datetime | None = None
    last_boost_amount: int | None = None
    live_watch_seconds_since_claim: int = 0
    _live_seconds_this_cycle: int = 0
    observed_live_intervals: list[int] = field(default_factory=list)

    def _target_live_window(self) -> int:
        if not self.observed_live_intervals:
            return self.default_live_window_seconds
        return int(sum(self.observed_live_intervals) / len(self.observed_live_intervals))

    def update(
        self,
        *,
        now: dt.datetime,
        is_live: bool,
        current_balance: int | None,
        claimed: bool,
        claimed_points: int | None,
        elapsed_seconds: int,
    ) -> dict[str, str]:
        if is_live:
            self.live_watch_seconds_since_claim += elapsed_seconds
            self._live_seconds_this_cycle += elapsed_seconds

        if claimed:
            self.last_boost_at = now
            self.last_boost_amount = claimed_points
            if self._live_seconds_this_cycle > 0:
                self.observed_live_intervals.append(self._live_seconds_this_cycle)
                self.observed_live_intervals = self.observed_live_intervals[-self.max_samples :]
            self.live_watch_seconds_since_claim = 0
            self._live_seconds_this_cycle = 0

        target_live = self._target_live_window()
        remaining_live = max(0, target_live - self.live_watch_seconds_since_claim)

        if self.last_boost_at is not None:
            delta_s = int((now - self.last_boost_at).total_seconds())
            amt = self.last_boost_amount
            amt_s = str(amt) if amt is not None else "?"
            last_boost = f"+{amt_s} ({_format_duration(delta_s)} ago)"
        else:
            last_boost = "none"

        if is_live:
            next_boost_in = f"~{_format_duration(remaining_live)}"
        else:
            next_boost_in = "offline"

        return {
            "is_live": "yes" if is_live else "no",
            "balance": str(current_balance) if current_balance is not None else "unknown",
            "last_boost": last_boost,
            "live_minutes_since_last_boost": f"{self.live_watch_seconds_since_claim / 60:.1f}",
            "expected_live_minutes_per_boost": f"{target_live / 60:.1f}",
            "remaining_live_minutes_to_eta": f"{remaining_live / 60:.1f}",
            "next_boost_in": next_boost_in,
        }
