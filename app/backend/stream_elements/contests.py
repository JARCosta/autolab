"""StreamElements contest polling over HTTP + WebSocket connectivity check."""

import datetime
import time
import traceback

import websocket
from app.backend.notifications import send_message_threaded
from app.infrastructure.http import streamelements as streamelements_http

from . import se_helpers


def test_connection(ws: websocket.WebSocketApp) -> bool:
    try:
        ws.send("PING")
        return True
    except Exception:
        send_message_threaded(f"Error when testing connection: {traceback.format_exc()}", notification=True)
        return False


def get_active_contest(channel: str):
    channel_id = se_helpers.get_streamelements_id(channel)
    if not channel_id:
        return None, None
    while True:
        try:
            r = streamelements_http.get_active_contest(channel_id)
            break
        except Exception:
            send_message_threaded(
                f"[{channel}, streamElements] Error getting active contest: {traceback.format_exc()}"
            )
            time.sleep(2)
    if not r.ok or r.json()["contest"] is None:
        return None, None
    response_json = r.json()
    start = datetime.datetime.strptime(
        response_json["contest"]["startedAt"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ) + datetime.timedelta(hours=time.localtime().tm_isdst)
    end = start + datetime.timedelta(minutes=response_json["contest"]["duration"])
    return end, response_json


def get_contest_details(channel: str, contest_id: str):
    channel_id = se_helpers.get_streamelements_id(channel)
    if not channel_id:
        return None
    while True:
        try:
            r = streamelements_http.get_contest(channel_id, contest_id)
            break
        except Exception:
            send_message_threaded(
                f"[{channel}, streamElements] Error getting contest details: {traceback.format_exc()}"
            )
            time.sleep(2)
    if not r.ok:
        return None
    return r.json()
