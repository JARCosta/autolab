"""TV iframe viewer module."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from app.infrastructure.storage.tv_store import (
    extract_stream_from_iframe,
    load_streams,
    normalize_stream,
    save_streams,
)


tv_bp = Blueprint(
    "tv",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/tv",
)


@tv_bp.route("/tv")
def tv_page():
    streams = load_streams()
    selected = streams[0] if streams else None
    return render_template("tv.html", streams=streams, selected=selected)


@tv_bp.route("/api/tv/streams", methods=["GET", "POST"])
def api_streams():
    streams = load_streams()

    if request.method == "GET":
        return jsonify({"streams": streams})

    payload = request.get_json(silent=True) or {}
    iframe_html = payload.get("iframe_html")

    try:
        if iframe_html:
            stream = extract_stream_from_iframe(str(iframe_html), str(payload.get("name") or ""))
        else:
            stream = normalize_stream(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    streams.append(stream)
    save_streams(streams)
    return jsonify({"streams": load_streams()})


@tv_bp.route("/api/tv/streams/<int:index>", methods=["DELETE"])
def api_delete_stream(index: int):
    streams = load_streams()
    if 0 <= index < len(streams):
        del streams[index]
        save_streams(streams)
    return jsonify({"streams": streams})
