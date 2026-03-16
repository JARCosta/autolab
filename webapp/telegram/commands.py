"""Telegram bot command handlers."""
from notifications import send_message
from webapp.balance_data import get_balance_rows


def balance_overview():
    message = ""
    for channel, rows in get_balance_rows():
        message += f"{channel}:\n"
        for bettor, balance in rows:
            message += f"\t {bettor}: {balance}\n"
        message += "\n"
    send_message(message, notification=True)


def wallapop_overview():
    from wallapop_tracker.tracker import SearchTerms
    terms = SearchTerms()
    send_message(f"Wallapop Tracker Overview:\n{terms}\n", notification=True)


def search_wallapop_term(term: str, category: int = None, min_price: int = None, max_price: int = None):
    from wallapop_tracker.tracker import SearchTerms
    terms = SearchTerms()
    new_id = terms.add_search_term(term, category, min_price, max_price)
    if new_id is not None:
        send_message(f"Wallapop search term added successfully (id {new_id}).\n", notification=True)
    else:
        send_message("Failed to add Wallapop search term.\n", notification=True)


def reboot():
    import os
    send_message("Rebooting machine...", notification=True)
    os.system("systemctl reboot -i")


def restart():
    import subprocess
    send_message("Restarting script...", notification=True)
    subprocess.call(["sudo", "systemctl", "restart", "autolab"])


commands = {
    "balance": {
        "function": balance_overview,
        "helper": {"command": "balance", "description": "Get betting balance overview"},
    },
    "wallapop": {
        "function": wallapop_overview,
        "helper": {"command": "wallapop", "description": "Get Wallapop tracker overview"},
    },
    "search_term": {
        "function": search_wallapop_term,
        "helper": {
            "command": "search_term <term, category=None, min_price=None, max_price=None>",
            "description": "Search Wallapop for a specific term",
        },
    },
    "reboot": {
        "function": reboot,
        "helper": {"command": "reboot", "description": "Reboot the machine"},
    },
    "restart": {
        "function": restart,
        "helper": {"command": "restart", "description": "Restart the bot script"},
    },
}
