"""
2GIS Parking Parser — Алматы (Финальная версия с обходом лимита page_size=10)
Разбивает город на радиусные зоны, собирает парковки порциями по 10 объектов,
парсит реальную структуру JSON, очищает дубликаты и выгружает в CSV/Google Sheets.
"""

import os
import csv
import time
import math
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("parser.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

BASE_URL      = "https://catalog.api.2gis.com/3.0/items"
PAGE_SIZE     = 10  # Жесткий лимит вашего API-ключа
REQUEST_DELAY = 0.5

FIELDNAMES = ["id", "name", "address", "lat", "lon", "url_2gis", "district"]

def make_2gis_url(item_id: str) -> str:
    return f"https://2gis.kz/almaty/firm/{item_id}"

def parse_item(item: dict) -> dict:
    """Парсит объект на основе подтвержденной структуры вашего ответа API."""
    item_id = item.get("id", "")
    name = item.get("name", "").strip()
    address = item.get("full_name", "Алматы")
    
    point = item.get("point", {})
    lat = point.get("lat", "")
    lon = point.get("lon", "")
    
    url_2gis = make_2gis_url(item_id)
    district = "Алматы"

    return {
        "id": item_id,
        "name": name,
        "address": address,
        "lat": lat,
        "lon": lon,
        "url_2gis": url_2gis,
        "district": district
    }

def generate_radius_grid(lat_min, lon_min, lat_max, lon_max, steps_lat=6, steps_lon=6):
    """Генерирует сетку центральных точек для сканирования города."""
    points = []
    lat_step = (lat_max - lat_min) / steps_lat
    lon_step = (lon_max - lon_min) / steps_lon

    lat_mid = (lat_min + lat_max) / 2
    meters_per_lat = 111000
    meters_per_lon = 111000 * math.cos(math.radians(lat_mid))
    
    step_lat_m = lat_step * meters_per_lat
    step_lon_m = lon_step * meters_per_lon
    
    radius = int(math.sqrt(step_lat_m**2 + step_lon_m**2) / 2 * 1.15)

    for i in range(steps_lat):
        for j in range(steps_lon):
            c_lat = lat_min + (i * lat_step) + (lat_step / 2)
            c_lon = lon_min + (j * lon_step) + (lon_step / 2)
            points.append({
                "lat": round(c_lat, 6),
                "lon": round(c_lon, 6),
                "radius": radius
            })
    return points

def fetch_parkings_by_radius(center: dict, api_key: str, global_results: dict):
    """Ищет парковки в конкретном радиусе постранично."""
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "AlmatyParkingParser/7.0"})

    while True:
        params = {
            "q":         "парковка",
            "point":     f"{center['lon']},{center['lat']}",
            "radius":    center['radius'],
            "page":      page,
            "page_size": PAGE_SIZE,
            "key":       api_key,
            "fields":    "items.point",
        }

        try:
            resp = session.get(BASE_URL, params=params, timeout=15)
            if page == 1 and resp.status_code == 404:
                break
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.error(f"Ошибка запроса: {e}")
            break

        data = resp.json()
        if data.get("meta", {}).get("code") != 200:
            break

        result_data = data.get("result", {})
        items       = result_data.get("items", [])

        if not items:
            break

        added_in_this_page = 0
        for item in items:
            parsed = parse_item(item)
            if parsed["id"] and parsed["id"] not in global_results:
                global_results[parsed["id"]] = parsed
                added_in_this_page += 1

        if added_in_this_page > 0:
            log.info(f"    [Стр {page}] Найдено новых парковок: {added_in_this_page}")

        # Если вернулось меньше, чем лимит страницы, значит, в этой зоне объекты закончились
        if len(items) < PAGE_SIZE:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

def post_process_deduplicate(records: list[dict]) -> list[dict]:
    """Удаляет дубликаты по координатам или связке имя+адрес."""
    seen_coords = set()
    seen_names = set()
    unique_records = []

    for r in records:
        coord_key = (round(float(r["lat"]), 5), round(float(r["lon"]), 5)) if r["lat"] and r["lon"] else None
        name_key = f"{r['name'].lower()}_{r['address'].lower()}".strip()

        if coord_key and coord_key in seen_coords:
            continue
        if name_key in seen_names:
            continue

        if coord_key:
            seen_coords.add(coord_key)
        seen_names.add(name_key)
        unique_records.append(r)

    log.info(f"🧹 Очистка дубликатов: из {len(records)} записей оставлено {len(unique_records)} уникальных.")
    return unique_records

def save_to_csv(records: list[dict], path: str = "parkings_almaty.csv") -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)
    log.info(f"💾 Локальный CSV сохранён: {path} ({len(records)} строк)")

def upload_to_sheets(records: list[dict], spreadsheet_id: str, sheet_name: str = "Парковки") -> None:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        log.error("Библиотеки gspread или google-auth не найдены.")
        return

    creds_path = os.getenv("GOOGLE_CREDENTIALS_JSON", "creds.json")
    if not os.path.exists(creds_path):
        log.warning(f"Файл credentials не найден: {creds_path}. Пропускаем Sheets.")
        return

    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds  = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(creds)
        sh     = client.open_by_key(spreadsheet_id)

        try:
            ws = sh.worksheet(sheet_name)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=len(records) + 10, cols=len(FIELDNAMES))

        headers = ["ID объекта", "Название", "Адрес", "Широта (Lat)", "Долгота (Lon)", "Ссылка на 2GIS", "Район / Город"]
        rows = [headers]
        for r in records:
            rows.append([str(r.get(f, "")) for f in FIELDNAMES])

        ws.update(rows, value_input_option="RAW")
        ws.format("A1:G1", {
            "backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.15},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })
        log.info(f"✨ Google Sheets успешно обновлён! Залито строк: {len(records)}")
    except Exception as e:
        log.error(f"Ошибка при записи в Sheets: {e}")

def main():
    api_key = "a01a6ea0-71b7-4f6e-a361-1667ae9ba28f"
    spreadsheet_id = "1pYwoXP7xjHyVN0dyW42xrAE-dQ-oSR0W46Z9h4QX3Ks"

    log.info("=== Запуск адаптивного GRID-парсера 2GIS: Парковки Алматы ===")
    start = datetime.now()

    all_parkings = {}

    # Координатные границы Алматы
    ALMATY_LAT_MIN = 43.1900
    ALMATY_LON_MIN = 76.8200
    ALMATY_LAT_MAX = 43.3400
    ALMATY_LON_MAX = 76.9700

    # Делаем сетку 6х6 (36 зон сканирования)
    grid_points = generate_radius_grid(
        ALMATY_LAT_MIN, ALMATY_LON_MIN, ALMATY_LAT_MAX, ALMATY_LON_MAX, 
        steps_lat=6, steps_lon=6
    )
    
    log.info(f"🌐 Создано {len(grid_points)} радиусных зон. Радиус покрытия каждой: ~{grid_points[0]['radius']}м.")

    for idx, center in enumerate(grid_points, 1):
        log.info(f"📦 Сканируем зону {idx}/{len(grid_points)}...")
        fetch_parkings_by_radius(center, api_key, all_parkings)
        time.sleep(0.3)

    raw_records = list(all_parkings.values())

    if not raw_records:
        log.warning("Данные не получены.")
        return

    clean_records = post_process_deduplicate(raw_records)

    save_to_csv(clean_records)
    upload_to_sheets(clean_records, spreadsheet_id)

    elapsed = (datetime.now() - start).seconds
    log.info(f"=== Процесс завершён! Чистых объектов собрано: {len(clean_records)} за {elapsed}с ===")

if __name__ == "__main__":
    main()