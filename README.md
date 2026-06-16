# AFO AI Internship — Тестовое задание

**Задача 1:** Парсер 2ГИС — парковки Алматы → Google Sheets  
**Задача 2:** WhatsApp рассыльщик (dry-run + live)

---

## Быстрый старт (5 минут)

### 1. Клонируем и ставим зависимости

```bash
git clone https://github.com/YOUR_USERNAME/afo-ai-internship.git
cd afo-ai-internship

# Задача 1
cd task1_2gis_parser
pip install -r requirements.txt

# Задача 2
cd ../task2_whatsapp_sender
pip install -r requirements.txt
```

---

## Задача 1 — Парсер 2ГИС

### Настройка

```bash
cd task1_2gis_parser
cp .env.example .env
```

Заполнить `.env`:

| Переменная | Где взять |
|---|---|
| `DGIS_API_KEY` | [dev.2gis.ru](https://dev.2gis.ru/) → создать проект → API key |
| `GOOGLE_SPREADSHEET_ID` | ID из URL таблицы: `docs.google.com/spreadsheets/d/**ID**/edit` |
| `GOOGLE_CREDENTIALS_JSON` | [Google Cloud Console](https://console.cloud.google.com/) → Service Account → Download JSON |

### Запуск

```bash
python parser.py
```

**Результат:**
- `parkings_almaty.csv` — локальная копия данных
- `parser.log` — лог выполнения
- Google Sheets обновляется автоматически (если задан `GOOGLE_SPREADSHEET_ID`)

### Собираемые поля

| Поле | Описание |
|---|---|
| name | Название парковки |
| address | Полный адрес |
| lat / lon | Координаты |
| url_2gis | Прямая ссылка на объект |
| is_paid | Платная / бесплатная |
| tariff | Тариф (если указан) |
| total_spots | Количество мест |
| parking_type | Тип: ТЦ / БЦ / подземная / открытая… |
| related_object | К какому объекту относится |
| hours | Часы работы |
| phone | Телефон |
| district | Район Алматы |

### Выбор подхода: почему API, а не скрапинг

- **Официальный Catalog API v3** — бесплатный ключ, JSON, координаты и расписание из коробки
- Скрапинг HTML 2GIS требует обхода динамической загрузки (React SPA) через Playwright/Selenium — дороже по времени и хрупче
- Selenium-подход рассматривался как fallback для полей, которых нет в API (тарифы), но большинство нужных данных API отдаёт напрямую

---

## Задача 2 — WhatsApp рассыльщик

### Настройка

```bash
cd task2_whatsapp_sender
cp .env.example .env
```

Заполнить `.env`:

| Переменная | Где взять |
|---|---|
| `TWILIO_ACCOUNT_SID` | [console.twilio.com](https://console.twilio.com) |
| `TWILIO_AUTH_TOKEN` | Там же |
| `TWILIO_WHATSAPP_NUMBER` | Sandbox: `+14155238886` |

> **Sandbox:** перед тестом отправьте с вашего WhatsApp сообщение `join <sandbox-code>` на `+14155238886`

### Запуск — dry-run (по умолчанию, безопасно)

```bash
# На своём CSV
python sender.py --input contacts_sample.csv --mode dry-run

# На данных из задачи 1 (полная база парковок)
python sender.py --parking-csv ../task1_2gis_parser/parkings_almaty.csv --mode dry-run
```

### Запуск — live (только на свой номер!)

```bash
python sender.py --input my_test.csv --mode live
```

`my_test.csv` должен содержать только **ваш собственный номер** для демонстрации.

### Формат входного CSV

```csv
phone,message
+77001234567,Привет! Это тестовое сообщение.
87771234567,Ещё одно сообщение.
```

Поддерживаются форматы: `+7XXXXXXXXXX`, `8XXXXXXXXXX`, `7XXXXXXXXXX`, с пробелами и дефисами.

### Обработка ошибок

| Ситуация | Поведение |
|---|---|
| Невалидный номер | Пропуск + WARNING в лог |
| Пустое сообщение | Пропуск + WARNING |
| Сообщение > 1600 символов | Пропуск + WARNING |
| Номер не в WhatsApp (Twilio 21614) | ERROR в лог, продолжаем |
| Rate limit | ERROR в лог, продолжаем |
| Обрыв соединения | ERROR в лог, продолжаем |

---

## Структура репозитория

```
afo-ai-internship/
├── task1_2gis_parser/
│   ├── parser.py           # Основной парсер
│   ├── requirements.txt
│   └── .env.example
├── task2_whatsapp_sender/
│   ├── sender.py           # Рассыльщик
│   ├── contacts_sample.csv # Пример входных данных
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

---

## Ссылки

- [Google Sheets с данными](https://docs.google.com/spreadsheets/d/YOUR_ID) ← вставить после запуска
- [2GIS API документация](https://docs.2gis.com/ru/api/catalog/overview)
- [Twilio WhatsApp Sandbox](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
