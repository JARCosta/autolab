"""Telegram bot command handlers."""
from app.backend.notifications import send_message
from app.infrastructure.storage.balances_db import fetch_and_store_balances


def balance_overview():
    """Get betting balance overview for all channels."""
    message = ""
    for channel, rows in fetch_and_store_balances():
        message += f"{channel}:\n"
        for bettor, balance in rows:
            message += f"\t {bettor}: {balance}\n"
        message += "\n"
    send_message(message, notification=True)


def wallapop_overview():
    """Get Wallapop tracker overview."""
    from app.backend.wallapop_tracker.tracker import SearchTerms
    terms = SearchTerms()
    send_message(f"Wallapop Tracker Overview:\n{terms}\n", notification=True)


def search_wallapop_term(term: str, category: int = None, min_price: int = None, max_price: int = None):
    """Search Wallapop for a specific term."""
    from app.backend.wallapop_tracker.tracker import SearchTerms
    terms = SearchTerms()
    new_id = terms.add_search_term(term, category, min_price, max_price)
    if new_id is not None:
        send_message(f"Wallapop search term added successfully (id {new_id}).\n", notification=True)
    else:
        send_message("Failed to add Wallapop search term.\n", notification=True)

def restart():
    """Restart the bot script."""
    import subprocess
    send_message("Restarting script...", notification=True)
    subprocess.call(["autolab", "restart"])


def live_channels():
    """Show all Twitch channels currently live with stats."""
    from app.backend.twitch_manager import get_live_channels

    message = "🔴 LIVE CHANNELS\n"
    message += "=" * 50 + "\n\n"

    live_channels = get_live_channels()

    if not live_channels:
        message += "No channels currently live.\n"
    else:
        for idx, (channel_name, stream_info) in enumerate(live_channels, 1):
            message += f"{idx}. {channel_name}\n"
            message += f"   Title: {stream_info.get('title', 'N/A')}\n"
            message += f"   Viewers: {stream_info.get('viewer_count', 0)}\n"
            message += f"   Last Live: {stream_info.get('last_live_time', 'N/A')}\n"
            message += f"   Bettors: {stream_info.get('bettor_count', 0)}\n"
            message += "-" * 30 + "\n"

    send_message(message, notification=True)


def leaderboard():
    """Show betting leaderboard with top performers."""
    from app.backend.betting_manager import get_leaderboard

    message = "🏆 BETTING LEADERBOARD\n"
    message += "=" * 50 + "\n\n"

    leaderboard_data = get_leaderboard(limit=10)

    if not leaderboard_data:
        message += "No betting data available.\n"
    else:
        for idx, (bettor_name, stats) in enumerate(leaderboard_data, 1):
            message += f"{idx}. {bettor_name}\n"
            message += f"   Balance: ${stats.get('balance', 0)}\n"
            message += f"   Wins: {stats.get('wins', 0)}\n"
            message += f"   Losses: {stats.get('losses', 0)}\n"
            message += f"   Win Rate: {stats.get('win_rate', 0):.1f}%\n"
            message += f"   Total Bets: {stats.get('total_bets', 0)}\n"
            message += "-" * 30 + "\n"

    send_message(message, notification=True)


def history(user_id: str = None):
    """Show betting history for a user or all users."""
    from app.backend.betting_manager import get_bet_history

    message = "📜 BETTING HISTORY\n"
    message += "=" * 50 + "\n\n"

    if user_id:
        history_data = get_bet_history(user_id=user_id, limit=20)
    else:
        history_data = get_bet_history(limit=20)

    if not history_data:
        message += "No betting history available.\n"
    else:
        for idx, bet in enumerate(history_data, 1):
            message += f"{idx}. {bet.get('game', 'N/A')}\n"
            message += f"   Amount: ${bet.get('amount', 0)}\n"
            message += f"   Outcome: {'✅ WIN' if bet.get('outcome') == 'win' else '❌ LOSS'}\n"
            message += f"   Channel: {bet.get('channel', 'N/A')}\n"
            message += f"   Time: {bet.get('timestamp', 'N/A')}\n"
            message += "-" * 30 + "\n"

    send_message(message, notification=True)


def status():
    """Show system and betting status."""
    from app.backend.betting_manager import get_system_status

    message = "🔧 SYSTEM STATUS\n"
    message += "=" * 50 + "\n\n"

    status_data = get_system_status()

    if not status_data:
        message += "System status unavailable.\n"
    else:
        message += f"Server Health: {status_data.get('health', 'Unknown')}\n"
        message += f"Active Connections: {status_data.get('connections', 0)}\n"
        message += f"Pending Transactions: {status_data.get('pending_transactions', 0)}\n"
        message += f"Maintenance Mode: {status_data.get('maintenance_mode', False)}\n"
        message += f"Total Bettors: {status_data.get('total_bettors', 0)}\n"

    send_message(message, notification=True)


def help():
    """Show available commands."""
    message = "📚 AVAILABLE COMMANDS\n"
    message += "=" * 50 + "\n\n"
    message += "/balance - Get betting balance overview\n"
    message += "/live - Show currently live Twitch channels\n"
    message += "/leaderboard - Show top betting performers\n"
    message += "/history - Show recent betting history\n"
    message += "/status - Show system status\n"
    message += "/help - Show this help message\n"
    message += "\n📌 Wallapop Commands:\n"
    message += "/wallapop - Get Wallapop tracker overview\n"
    message += "/search_term <term> - Search Wallapop for a term\n"

    send_message(message, notification=True)


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
    "restart": {
        "function": restart,
        "helper": {"command": "restart", "description": "Restart the bot script"},
    },
    "live": {
        "function": live_channels,
        "helper": {"command": "live", "description": "Show currently live Twitch channels"},
    },
    "history": {
        "function": history,
        "helper": {"command": "history [user_id]", "description": "Show betting history"},
    },
    "leaderboard": {
        "function": leaderboard,
        "helper": {"command": "leaderboard", "description": "Show top betting performers"},
    },
    "status": {
        "function": status,
        "helper": {"command": "status", "description": "Show system status"},
    },
    "help": {
        "function": help,
        "helper": {"command": "help", "description": "Show available commands"},
    },
}
