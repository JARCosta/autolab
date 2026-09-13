import json
import os
from abc import ABC
from datetime import datetime, timedelta
from time import sleep
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.sofascore.com"


def get_json(page, url):
    response = page.goto(url, wait_until="domcontentloaded")

    if response.status != 200:
        raise RuntimeError(f"HTTP {response.status}: {url}")

    return json.loads(page.locator("body").inner_text())


def get_team_search(page, query):
    query = quote(query)
    url = f"{BASE_URL}/api/v1/search/teams?q={query}&page=0"
    return get_json(page, url)


def get_team_future_calendar(page, team_id):
    events = []
    page_number = 0

    while True:
        print(f"Fetching future events page {page_number}...")

        url = (
            f"{BASE_URL}/api/v1/team/"
            f"{team_id}/events/next/{page_number}"
        )

        data = get_json(page, url)
        batch = [Match(
            event["id"],
            event["customId"],
            event["slug"],
            event["homeTeam"]["name"],
            event["awayTeam"]["name"],
            event["startTimestamp"],
            event["status"]["type"],
        ) for event in data["events"]]
        events.extend(batch)

        if not data["hasNextPage"] or batch[-1].datetime() > datetime.now() + timedelta(days=365):
            break

        page_number += 1
        sleep(1)

    return {"events": events, "hasNextPage": data["hasNextPage"]}

def get_team_past_calendar(page, team_id):
    events = []
    page_number = 0

    while True:  # Limit to 5 pages for past events
        print(f"Fetching past events page {page_number}...")

        url = (
            f"{BASE_URL}/api/v1/team/"
            f"{team_id}/events/last/{page_number}"
        )

        data = get_json(page, url)
        batch = [Match(
            event["id"],
            event["customId"],
            event["slug"],
            event["homeTeam"]["name"],
            event["awayTeam"]["name"],
            event["startTimestamp"],
            event["status"]["type"],
        ) for event in data["events"]]
        events.extend(batch)

        if not data["hasNextPage"] or batch[-1].datetime() < datetime.now() - timedelta(days=365):
            break

        page_number += 1
        sleep(1)

    return {"events": events, "hasNextPage": data["hasNextPage"]}


class Match:
    def __init__(
        self,
        id,
        custom_id,
        slug,
        home_team,
        away_team,
        start_timestamp,
        status,
    ):
        self.id = id
        self.custom_id = custom_id
        self.slug = slug
        self.home_team = home_team
        self.away_team = away_team
        self.start_timestamp = start_timestamp
        self.status = status

    def __repr__(self):
        return (
            f"{self.datetime():%Y-%m-%d %H:%M} "
            f"{self.home_team} vs {self.away_team}, "
            f"{self.status}, {self.url()}"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "custom_id": self.custom_id,
            "slug": self.slug,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "start_timestamp": self.start_timestamp,
            "status": self.status,
            "datetime": self.datetime().isoformat(),
        }

    def datetime(self):
        return datetime.fromtimestamp(self.start_timestamp)

    def url(self):
        return (
            f"{BASE_URL}/pt/football/match/"
            f"{self.slug}/{self.custom_id}#id:{self.id}"
        )


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
        )

        page = browser.new_page()

        # Search team
        search = "Benfica"
        team_data = get_team_search(page, search)

        teams = [
            {
                "id": result["entity"]["id"],
                "name": result["entity"]["name"],
            }
            for result in team_data["results"]
        ]
        print(f"Teams found for '{search}': {teams}")
        team = team_data["results"][0]["entity"]
        team_id = team["id"]
        team_name = team["name"]

        # Load or fetch calendar
        filename = (
            f"{team_name.replace(' ', '_')}_"
            f"{datetime.now():%Y-%m-%d}.json"
        )

        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            future_data = get_team_future_calendar(page, team_id)
            past_data = get_team_past_calendar(page, team_id)

            data = {
                "events": [m.to_dict() for m in future_data["events"]],
                "past_events": [m.to_dict() for m in past_data["events"]],
                "hasNextPage": future_data["hasNextPage"] or past_data["hasNextPage"],
            }

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

        # Continue your application from here
        for match in data["events"]:
            print(match)

        browser.close()
