#!/usr/bin/env python3
"""
Multi-Source Tour Watcher - Baan Karon Buri Resort (Ocean View)
Sources: HT.kz, Freedom Travel
"""

import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SEEN_FILE = Path(os.environ.get("SEEN_TOURS_FILE", "seen_tours.json"))

TARGET_HOTEL_KEYWORDS = ["baan karon buri", "bann karon buri", "karon buri"]
TARGET_ROOM_KEYWORDS = ["ocean view", "sea view", "вид на море", "океан"]

CITY_FROM = "astana"
COUNTRY_TO = "thailand"
REGION_TO = "phuket"
ADULTS = 1

# Даты и длительность (от 6 до 11 ночей)
DATE_FROM = os.environ.get("DATE_FROM", "2026-11-18")
DATE_TO = os.environ.get("DATE_TO", "2026-11-30")
NIGHTS_MIN = int(os.environ.get("NIGHTS_MIN", "6"))
NIGHTS_MAX = int(os.environ.get("NIGHTS_MAX", "11"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


# ---------------------------------------------------------------------------
# Источник 1: HT.kz
# ---------------------------------------------------------------------------

def search_ht_tours() -> list[dict]:
    url = "https://api.ht.kz/v1/search/tours"
    headers = {**HEADERS, "Referer": "https://ht.kz/", "Origin": "https://ht.kz"}
    payload = {
        "depart_city": CITY_FROM,
        "country": COUNTRY_TO,
        "region": REGION_TO,
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "nights_from": NIGHTS_MIN,
        "nights_to": NIGHTS_MAX,
        "adults": ADULTS,
        "currency": "KZT",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        raw_tours = data.get("tours", []) or data.get("results", []) or []
        
        parsed = []
        for tour in raw_tours:
            parsed.append({
                "source": "HT.kz",
                "hotel": tour.get("hotel_name") or "Baan Karon Buri Resort",
                "room": tour.get("room_name") or "Стандарт / Уточняется",
                "price": int(tour.get("price") or tour.get("price_kzt") or 0),
                "date": tour.get("depart_date") or tour.get("date_from"),
                "nights": tour.get("nights"),
                "meal": tour.get("meal_type") or tour.get("meal") or "Завтраки",
                "url": tour.get("share_url") or "https://ht.kz/hotel/phuket-baan-karon-buri-resort",
            })
        return parsed
    except requests.RequestException as e:
        print(f"[WARN] Ошибка запроса к HT.kz: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Источник 2: Freedom Travel
# ---------------------------------------------------------------------------

def search_freedom_tours() -> list[dict]:
    url = "https://travel.freedom.kz/api/v1/tours/search"
    headers = {**HEADERS, "Referer": "https://travel.freedom.kz/"}
    payload = {
        "city_from": "TSE",  # Код Астаны
        "country": "TH",
        "region": "HKT",
        "date_start": DATE_FROM,
        "date_end": DATE_TO,
        "nights_from": NIGHTS_MIN,
        "nights_to": NIGHTS_MAX,
        "adults": ADULTS,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=25)
        if resp.status_code != 200:
            return []
        data = resp.json()
        raw_tours = data.get("data", []) or data.get("items", []) or []

        parsed = []
        for tour in raw_tours:
            parsed.append({
                "source": "Freedom Travel",
                "hotel": tour.get("hotel_name") or "Baan Karon Buri Resort",
                "room": tour.get("room_category") or tour.get("room_name") or "Стандарт / Уточняется",
                "price": int(tour.get("price_kzt") or tour.get("price") or 0),
                "date": tour.get("start_date") or tour.get("date"),
                "nights": tour.get("duration") or tour.get("nights"),
                "meal": tour.get("meal_code") or "BB (Завтраки)",
                "url": tour.get("link") or "https://travel.freedom.kz/",
            })
        return parsed
    except requests.RequestException as e:
        print(f"[WARN] Ошибка запроса к Freedom Travel: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Фильтрация и Обработка
# ---------------------------------------------------------------------------

def filter_target_tours(tours: list[dict]) -> list[dict]:
    matched = []
    for tour in tours:
        hotel_name = str(tour.get("hotel", "")).lower()
        room_name = str(tour.get("room", "")).lower()

        if not any(kw in hotel_name for kw in TARGET_HOTEL_KEYWORDS):
            continue

        is_room_match = any(kw in room_name for kw in TARGET_ROOM_KEYWORDS)
        
        entry = dict(tour)
        entry["exact_room_match"] = is_room_match
        if is_room_match and "уточняется" in entry["room"].lower():
            entry["room"] = "Ocean View"
            
        matched.append(entry)

    return matched


def load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_seen(seen: dict) -> None:
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Ошибка отправки в Telegram: {e}", file=sys.stderr)


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Проверка туров (6–11 ночей)...")
    
    all_raw = []
    all_raw.extend(search_ht_tours())
    all_raw.extend(search_freedom_tours())

    matched_tours = filter_target_tours(all_raw)

    ocean_view_tours = [t for t in matched_tours if t["exact_room_match"]]
    tours_to_process = ocean_view_tours if ocean_view_tours else matched_tours

    if not tours_to_process:
        print("[INFO] Туры по заданным критериям не найдены.")
        return

    seen = load_seen()
    updates = []

    for tour in tours_to_process:
        tour_key = f"{tour['source']}_{tour['date']}_{tour['nights']}_{tour['room']}"
        old_price = seen.get(tour_key, {}).get("price")
        current_price = tour["price"]

        if old_price is None or current_price != old_price:
            price_change = ""
            if old_price is not None:
                diff = current_price - old_price
                price_change = f" (было {old_price:,} ₸, {'📈 +' if diff > 0 else '📉 '}{diff:,} ₸)"

            updates.append((tour, price_change))
            seen[tour_key] = {
                "price": current_price,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    if updates:
        for tour, price_change in updates:
            room_icon = "🌊" if tour["exact_room_match"] else "🏨"
            msg = (
                f"🏝 <b>[{tour['source']}] Тур в Таиланд (Пхукет)</b>\n\n"
                f"🏨 <b>{html.escape(tour['hotel'])}</b>\n"
                f"{room_icon} <b>Номер:</b> {html.escape(tour['room'])}\n"
                f"📅 <b>Вылет:</b> {tour['date']} ({tour['nights']} ночей)\n"
                f"🍽 <b>Питание:</b> {html.escape(str(tour['meal']))}\n"
                f"👤 <b>Гости:</b> 1 взрослый\n\n"
                f"💰 <b>Цена:</b> {tour['price']:,} ₸{price_change}\n\n"
                f"🔗 <a href=\"{tour['url']}\">Открыть тур на {tour['source']}</a>"
            )
            send_telegram(msg)
            time.sleep(1)

        save_seen(seen)
        print(f"[INFO] Отправлено алертов: {len(updates)}")
    else:
        print("[INFO] Изменений цен нет.")


if __name__ == "__main__":
    main()
