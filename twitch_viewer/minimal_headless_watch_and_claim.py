from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from twitch_viewer.claim_points import (
    TwitchError,
    build_session,
    channel_points_bonus_snapshot,
    claim_points_once,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatchAndClaimConfig:
    username: str
    channel_login: str
    poll_seconds: int = 20
    headless: bool = True


async def watch_and_claim_channel_points(cfg: WatchAndClaimConfig) -> None:
    if not cfg.username:
        raise ValueError("username is required")
    if not cfg.channel_login:
        raise ValueError("channel_login is required")
    if cfg.poll_seconds < 5:
        raise ValueError("poll_seconds must be >= 5")

    gql_sess = build_session(cfg.username)
    channel_login = cfg.channel_login.strip().lstrip("@")

    log.info(
        "Minimal headless watch+claim: channel=%s user=%s poll=%ss headless=%s",
        channel_login,
        cfg.username,
        cfg.poll_seconds,
        cfg.headless,
    )

    token = gql_sess.oauth_token

    from playwright.async_api import async_playwright  # type: ignore[reportMissingImports]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=cfg.headless,
            args=["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": 1600, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # Provide the same auth token to the page as a best-effort cookie.
        # (Exact cookie names vary; we use auth-token since earlier runs worked for API visibility.)
        await context.add_cookies(
            [
                {
                    "name": "auth-token",
                    "value": token,
                    "domain": ".twitch.tv",
                    "path": "/",
                    "secure": True,
                    "httpOnly": False,
                    "sameSite": "None",
                }
            ]
        )

        page = await context.new_page()
        await page.goto(f"https://www.twitch.tv/{channel_login}", wait_until="domcontentloaded")
        await page.wait_for_timeout(10000)

        # If a "Start Watching" button exists, click it once so the player is active.
        with contextlib.suppress(Exception):
            mature_btn = page.get_by_role("button", name="Start Watching")
            if await mature_btn.count():
                await mature_btn.first.click(timeout=3000)

        # Page debug markers (useful when headless hits CAPTCHA).
        with contextlib.suppress(Exception):
            title = await page.title()
            html = await page.content()
            lower = html.lower()
            markers = []
            if "cloudflare" in lower:
                markers.append("cloudflare")
            if "captcha" in lower:
                markers.append("captcha")
            if "enable javascript" in lower:
                markers.append("enable_js")
            if "just a moment" in lower:
                markers.append("just_a_moment")
            log.info("Headless page debug: title=%s url=%s markers=%s", title, page.url, markers)

        # Main loop: claim whenever a bonus is available. No UI clicking here.
        last_claim_seen: str | None = None
        while True:
            now = datetime.now(timezone.utc)
            try:
                snap = channel_points_bonus_snapshot(gql_sess, channel_login)
                has_bonus = bool(snap.get("has_bonus"))
                claim_id = snap.get("claim_id")
                balance = snap.get("balance")
                bonus_points = snap.get("bonus_points")

                log.info(
                    "Tick: %s has_bonus=%s claim_id=%s bonus_points=%s balance=%s",
                    now.isoformat(timespec="seconds"),
                    has_bonus,
                    claim_id,
                    bonus_points,
                    balance,
                )

                if has_bonus and claim_id and claim_id != last_claim_seen:
                    # Attempt to claim via API mutation.
                    try:
                        res = claim_points_once(gql_sess, channel_login)
                        log.info("API claim result: %s", res.get("status"))
                    except TwitchError as e:
                        log.warning("API claim failed: %s", e)
                    last_claim_seen = claim_id

            except Exception as e:
                log.warning("Tick error: %s", e)

            await asyncio.sleep(cfg.poll_seconds)

