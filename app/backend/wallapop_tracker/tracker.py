"""Wallapop search tracker -- polls Wallapop API and sends new listings via Telegram."""
import datetime
import json
import time
import traceback

import requests

from app.backend.notifications import send_message
from app.infrastructure.storage.wallapop_store import (
    read_data_lines,
    read_search_term_lines,
    save_data_backup,
    write_data_lines,
    write_search_term_lines,
)
_AFTER_URL = "https://api.wallapop.com/api/v3/search?next_page="


def search(keywords: str, category: str = None, min_price: int = None, max_price: int = None):
    category_str = f"&category_ids={category}" if category is not None else ""
    min_price_str = f"&min_sale_price={min_price}" if min_price is not None else ""
    max_price_str = f"&max_sale_price={max_price}" if max_price is not None else ""

    first = (
        f"https://api.wallapop.com/api/v3/search?is_shippable=true"
        f"&keywords={keywords.replace(' ', '%20')}"
        f"{category_str}{min_price_str}{max_price_str}"
        f"&order_by=most_relevance&source=search_box"
    )
    headers = {"x-deviceos": "0"}
    url = first
    new_data = []

    for _ in range(10):
        response = requests.get(url, headers=headers)
        while response.status_code != 200:
            print(f"{datetime.datetime.now().strftime('%H:%M')} - Error {response.status_code}. Retrying in 1 second.")
            time.sleep(1)
            response = requests.get(url, headers=headers)
        response = response.json()
        next_page = response["meta"]["next_page"]
        for i in response["data"]["section"]["payload"]["items"]:
            created_at = datetime.datetime.fromtimestamp(i["created_at"] / 1e3).strftime("%H:%M %d-%m")
            modified_at = datetime.datetime.fromtimestamp(i["modified_at"] / 1e3).strftime("%H:%M %d-%m")
            diff = sum(created_at[j] != modified_at[j] for j in range(len(created_at)))
            item = [
                i["reserved"]["flag"],
                str(i["price"]["amount"]) + " " + i["price"]["currency"],
                created_at,
                modified_at,
                "new" if diff < 2 else "updated",
                "https://pt.wallapop.com/item/" + i["web_slug"] + " ",
                i["id"],
                i["user_id"],
                i["title"].replace(";", ",").replace("\n", " ").replace("\r", " "),
                i["description"].replace(";", ",").replace("\n", " ").replace("\r", " "),
            ]
            new_data.append(item)
        if not next_page:
            break
        url = _AFTER_URL + next_page
    return new_data


class SearchTerms:

    def __init__(self):
        self.terms = {}
        for line in read_search_term_lines():
            parts = line.strip().split(";")
            if len(parts) < 5:
                continue
            term = {
                "search_str": parts[1],
                "category": int(parts[2]) if parts[2] != "" else None,
                "min_price": int(parts[3]) if parts[3] != "" else None,
                "max_price": int(parts[4]) if parts[4] != "" else None,
            }
            self.terms[int(parts[0])] = term

    def update_file(self):
        lines: list[str] = []
        for term_id, term in self.terms.items():
            cat = term["category"] if term["category"] is not None else ""
            minp = term["min_price"] if term["min_price"] is not None else ""
            maxp = term["max_price"] if term["max_price"] is not None else ""
            lines.append(f"{term_id};{term['search_str']};{cat};{minp};{maxp}\n")
        write_search_term_lines(lines)

    def add_search_term(self, search_str: str, category: int = None, min_price: int = None, max_price: int = None):
        term_id = 0
        if len(self.terms) > 0:
            term_id = max(self.terms.keys()) + 1
        self.terms[term_id] = {
            "search_str": search_str,
            "category": category,
            "min_price": min_price,
            "max_price": max_price,
        }
        self.update_file()
        return term_id

    def delete_search_term(self, term_id: int):
        if term_id in self.terms:
            del self.terms[term_id]
            self.update_file()

    def __str__(self):
        return json.dumps(self.terms, indent=2)


def term_func(search_str: str, category: int = None, min_price: int = None, max_price: int = None):
    while True:
        try:
            old_data = read_data_lines()
            old_ids = []
            for line in old_data:
                if ";" in line:
                    old_ids.append(line.split(";")[6])
            save_data_backup(old_data)

            new_data = search(search_str, category=category, min_price=min_price, max_price=max_price)
            new_listings = [item for item in new_data if item[6] not in old_ids]

            if len(new_listings) > 0:
                print(f"{datetime.datetime.now().strftime('%H:%M')} - {len(new_listings)} new items found.")
                telegram_message = "New item found:\n"
                for i in new_listings:
                    telegram_message += i[8] + " " + i[1] + "\n" + i[5] + "\n\n"
                send_message(telegram_message, notification=True, log=False)

            out_lines: list[str] = []
            for i in new_data:
                out_lines.append("".join(str(j) + ";" for j in i) + "\n")
            write_data_lines(out_lines)

        except Exception as e:
            print(f"[Wallapop Tracker] Error: {e}")
            send_message(f"Error {e}\n{traceback.format_exc()}", notification=True)
        time.sleep(60)


class SearchRunner:

    def __init__(self):
        self.term_engine = SearchTerms()
        self.processes = {}
        for term_id in self.term_engine.terms:
            self.run_term(term_id)

    def run_term(self, term_id: int):
        import multiprocessing
        term = self.term_engine.terms[term_id]
        proc = multiprocessing.Process(
            target=term_func,
            args=(term["search_str"], term["category"], term["min_price"], term["max_price"]),
        )
        self.processes[term_id] = proc
        proc.start()

    def add_term(self, search_str: str, category: int = None, min_price: int = None, max_price: int = None):
        term_id = self.term_engine.add_search_term(search_str, category, min_price, max_price)
        self.run_term(term_id)

    def delete_term(self, term_id: int):
        if term_id in self.processes:
            self.processes[term_id].terminate()
            del self.processes[term_id]
        self.term_engine.delete_search_term(term_id)
