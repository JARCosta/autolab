

# from twitch_viewer.claim_points import build_session, claim_points_once

# sess = build_session("El_Pipow")
# print(claim_points_once(sess, "move_mind"))


import asyncio
import logging

from twitch_viewer.minimal_headless_watch_and_claim import (
    WatchAndClaimConfig,
    watch_and_claim_channel_points,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] [%(name)s] %(message)s",
)

asyncio.run(
    watch_and_claim_channel_points(
        WatchAndClaimConfig(
            username="El_Pipow",
            channel_login=(
                __import__("os").environ.get("TWITCH_CHANNEL", "warn").strip().lstrip("@")
            ),
            poll_seconds=20,
            headless=True,
        )
    )
)