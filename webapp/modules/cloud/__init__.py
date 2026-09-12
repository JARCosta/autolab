"""Nextcloud entry: /cloud redirects to the configured public Nextcloud URL."""

from __future__ import annotations

import os

from flask import Blueprint, redirect, render_template

cloud_bp = Blueprint("cloud", __name__, template_folder="templates")


def _public_nextcloud_url() -> str:
    return os.getenv("NEXTCLOUD_PUBLIC_URL", "http://127.0.0.1:8080").strip().rstrip("/")


@cloud_bp.route("/cloud")
def cloud_entry():
    target = _public_nextcloud_url()
    if not target:
        return render_template("cloud_disabled.html")
    return redirect(target + "/", code=302)
