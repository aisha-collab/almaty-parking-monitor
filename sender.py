import os
import csv
import sys
import time
import argparse
import logging
import re
from datetime import datetime
from pathlib import Path

# Настройка логирования
LOG_PATH = "whatsapp_sender.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

MAX_MSG_LENGTH = 1600

def normalize_phone(raw: str):
    if not raw: 
        return None
    digits = re.sub(r"\D", "", raw.strip())
    if not digits: 
        return None
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) == 10:
        digits = "7" + digits
    if not (7 <= len(digits) <= 15): 
        return None
    return f"+{digits}"

def build_from_parking_csv(path: str, template: str, mode: str):
    records = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, 1):
            phone = row.get("phone") or row.get("номер") or row.get("телефон", "")
            if not phone and mode == "dry-run":
                phone = f"+7707100{idx:03d}"  # Имитация для полной базы
            if not phone: 
                continue
            msg = template.format(
                name=row.get("name") or row.get("название", "Парковка"),
                address=row.get("address") or row.get("адрес", "Алматы"),
                url_2gis=row.get("url_2gis") or row.get("ссылка", "https://2gis.kz/almaty")
            )
            records.append({"phone": phone, "message": msg})
    return records

def run_distribution(records: list[dict], mode: str):
    stats = {"total": 0, "success": 0, "skipped": 0, "errors": 0}
    dry_lines = []
    
    log.info(f"Запуск процесса. Всего записей в очереди: {len(records)}")
    
    for i, rec in enumerate(records, 1):
        raw_phone = rec.get("phone", "")
        message = rec.get("message", "")
        stats["total"] += 1
        
        normalized = normalize_phone(raw_phone)
        if not normalized:
            log.warning(f"[{i}]  Невалидный формат номера '{raw_phone}' — Пропуск.")
            stats["skipped"] += 1
            continue
            
        if not message or len(message) > MAX_MSG_LENGTH:
            log.warning(f"[{i}]  Ошибка валидации текста — Пропуск.")
            stats["skipped"] += 1
            continue
            
        if mode == "dry-run":
            clean_msg = message.replace('\n', ' | ')
            line = f"TO={normalized} | MSG={clean_msg}"
            log.info(f"[{i}]  [DRY-RUN] {line[:90]}...")
            dry_lines.append(line)
            stats["success"] += 1
            
        elif mode == "live":
            if i > 2:
                log.info(f" Достигнут лимит LIVE-режима (2 сообщения). Безопасный выход.")
                stats["skipped"] += len(records) - (i - 1)
                break
                
            log.info(f"[{i}]  Отправка LIVE через Twilio API на номер {normalized}...")
            try:
                from twilio.rest import Client
                client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
                client.messages.create(
                    from_=os.getenv("TWILIO_WHATSAPP_NUMBER"), 
                    to=f"whatsapp:{normalized}", 
                    body=message
                )
                log.info(f"[{i}] Запрос отправлен в API.")
                stats["success"] += 1
                time.sleep(2)
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Too many attempts" in err_msg:
                    log.error(f"[{i}]  Ошибка API: Превышены лимиты отправки (Too many attempts).")
                else:
                    log.error(f"[{i}]  Ошибка: {err_msg}")
                stats["errors"] += 1

    if mode == "dry-run" and dry_lines:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"dry_run_{ts}.log", "w", encoding="utf-8") as f:
            f.write("\n".join(dry_lines))
        log.info(f"✨ Лог симуляции успешно сохранен: dry_run_{ts}.log")

    log.info(f"\n" + "="*50 + f"\nИТОГИ: Всего={stats['total']} | Успешно={stats['success']} | Пропущено={stats['skipped']} | Ошибок={stats['errors']}\n" + "="*50)

def main():
    parser = argparse.ArgumentParser(description="WhatsApp Рассыльщик Задачи №2")
    parser.add_argument("--mode", choices=["dry-run", "live"], default="dry-run", help="Режим выполнения")
    parser.add_argument("--parking-csv", default="parkings_almaty.csv", help="Путь к базе")
    args = parser.parse_args()

    template = " *Мониторинг парковок Алматы*\nОбъект: {name}\nАдрес: {address}\nКарта: {url_2gis}"
    
    if not Path(args.parking_csv).exists():
        log.error(f"Файл {args.parking_csv} не найден.")
        sys.exit(1)
        
    records = build_from_parking_csv(args.parking_csv, template, args.mode)
    run_distribution(records, args.mode)

if __name__ == "__main__":
    main()