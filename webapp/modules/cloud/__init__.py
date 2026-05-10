"""Nextcloud entry: /cloud redirects when the nextcloud module is enabled."""

from __future__ import annotations

import os

from flask import Blueprint, redirect, render_template

from app.runtime.modules import is_enabled

cloud_bp = Blueprint("cloud", __name__, template_folder="templates")


def _public_nextcloud_url() -> str:
    return os.getenv("NEXTCLOUD_PUBLIC_URL", "http://127.0.0.1:8080").strip().rstrip("/")


@cloud_bp.route("/cloud")
def cloud_entry():
    if not is_enabled("nextcloud"):
        return render_template("cloud_disabled.html")
    target = _public_nextcloud_url() + "/"
    return redirect(target, code=302)
