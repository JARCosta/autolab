"""Wallapop Blueprint: read-only overview of active search terms."""
from flask import Blueprint, jsonify, render_template

from app.backend.wallapop_tracker.tracker import SearchTerms

wallapop_bp = Blueprint(
    "wallapop",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/wallapop",
)


def _serialize_terms() -> list[dict]:
    terms = SearchTerms().terms
    return [
        {
            "id": term_id,
            "search_str": data["search_str"],
            "category": data["category"],
            "min_price": data["min_price"],
            "max_price": data["max_price"],
        }
        for term_id, data in sorted(terms.items())
    ]


@wallapop_bp.route("/wallapop")
def wallapop():
    return render_template("wallapop.html", terms=_serialize_terms())


@wallapop_bp.route("/api/wallapop/terms")
def api_terms():
    return jsonify({"terms": _serialize_terms()})
