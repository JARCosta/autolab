


from app.infrastructure.http_clients.twitch import is_channel_live
from app.infrastructure.storage.twitch_oauth.service import check_oauth_token
from app.infrastructure.http_clients.twitch import validate_token


if __name__ == "__main__":
    oauth_username = "el_pipow"
    channel_login = "prcs"

    token = check_oauth_token(oauth_username)
    response = is_channel_live(channel_login, token)

    print(f"Is channel {channel_login} live using {oauth_username}'s token: {response}")