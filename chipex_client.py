"""
chipex_lookup.py

Модуль відповідає за:
1. Запит до сайту chipex.co.uk за номером авто (reg)
2. Витягування вбудованого JSON (reg_json) з HTML‑сторінки
   за допомогою bs4/lxml + regex
3. Повернення чистих даних у вигляді VehicleInfo

Якщо в майбутньому знадобиться підтримати інше джерело даних
(інший сайт, інший формат відповіді) – достатньо додати новий
клієнт у цей файл або поруч і підключити його в app.py,
не чіпаючи решту проєкту.
"""

import re
import json
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Налаштування констант
# ----------------------------------------------------------------------
BASE_URL = "https://chipex.co.uk/product/your-registration-touch-up-kit/"

# Приклад шаблону: reg_json: '{"reg":"E366SJW", ... }',
REG_JSON_PATTERN = re.compile(r"reg_json:\s*'({.*?})'", re.DOTALL)

HEADERS = {
    # Деякі сайти віддають інший (обрізаний) HTML ботам без User-Agent
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    # Додаткові заголовки, які іноді допомагають обійти прості бот‑фільтри
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://chipex.co.uk/",
}

# ----------------------------------------------------------------------
# Виняток
# ----------------------------------------------------------------------
class ChipexLookupError(Exception):
    """Піднімається, коли не вдалося отримати або розпарсити дані авто."""


# ----------------------------------------------------------------------
# Дані про транспортний засіб
# ----------------------------------------------------------------------
@dataclass
class VehicleInfo:
    reg: str
    manufacturer: str
    model: str
    colour: str
    fuel: str
    year: str
    vin: str

    @classmethod
    def from_dict(cls, data: dict) -> "VehicleInfo":
        return cls(
            reg=data.get("reg", ""),
            manufacturer=data.get("manufacturer", ""),
            model=data.get("model", ""),
            colour=data.get("colour", ""),
            fuel=data.get("fuel", ""),
            year=data.get("year", ""),
            vin=data.get("vin", ""),
        )


# ----------------------------------------------------------------------
# Функції
# ----------------------------------------------------------------------
def fetch_html(reg_number: str, timeout: int = 15, max_retries: int = 3) -> str:
    """
    Робить GET‑запит до chipex.co.uk з номером авто і повертає HTML.
    Використовує просту логіку повторних спроб (exponential backoff).
    """
    reg_number = reg_number.strip().upper()
    if not reg_number:
        raise ChipexLookupError("Номер автомобіля не може бути порожнім")

    params = {"reg": reg_number}
    attempt = 0
    while True:
        attempt += 1
        try:
            response = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                timeout=timeout,
            )
            # Якщо код успішний – повертаємо HTML
            if response.status_code == 200:
                return response.text

            # Інші коди – формуємо детальне повідомлення
            error_msg = (
                f"Failed to fetch data from chipex.co.uk. "
                f"Status Code: {response.status_code}. "
            )
            if response.status_code == 401:
                error_msg += (
                    "Possible unauthorized access (Bot detection or missing credentials)."
                )
            elif response.status_code == 403:
                error_msg += (
                    "Forbidden access (Blocked by website anti‑bot measures)."
                )
            elif 500 <= response.status_code < 600:
                error_msg += "Server side error."
            else:
                error_msg += (
                    f"Unknown HTTP Error ({response.status_code}). "
                    f"Response snippet: {response.text[:100]}"
                )

            # Якщо вичерпано спроби – піднімаємо виключення
            if attempt >= max_retries:
                raise ChipexLookupError(error_msg) from None

            # Інакше чекаємо перед наступною спробою
            wait_time = 2 ** (attempt - 1)  # 1, 2, 4, …
            time.sleep(wait_time)

        except requests.RequestException as exc:
            # Зовнішні помилки (DNS, тайм‑аут тощо)
            if attempt >= max_retries:
                raise ChipexLookupError(
                    f"Network error while contacting chipex.co.uk after {attempt} attempts: {exc}"
                ) from exc
            wait_time = 2 ** (attempt - 1)
            time.sleep(wait_time)


def extract_reg_json(html: str) -> dict:
    """
    Знаходить reg_json у HTML і повертає розпарсений словник.
    Спочатку шукаємо у весь тексту сторінки, а якщо не вдалося –
    перебираємо теги <script>.
    """
    # 1️⃣ Пошук у весь HTML
    match = REG_JSON_PATTERN.search(html)
    if not match:
        # 2️⃣ Фолбек: шукаємо лише всередині <script>
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script"):
            script_text = script.string or ""
            match = REG_JSON_PATTERN.search(script_text)
            if match:
                break

    if not match:
        raise ChipexLookupError(
            "Не знайдено даних про автомобіль для цього номера "
            "(можливо, номер не існує в базі chipex)"
        )

    raw_json = match.group(1)
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ChipexLookupError(
            f"Помилка розбору JSON з відповіді сайту: {exc}"
        ) from exc


def lookup_vehicle(reg_number: str) -> VehicleInfo:
    """
    Повний цикл: запит + парсинг + повернення VehicleInfo.
    """
    html = fetch_html(reg_number)
    data = extract_reg_json(html)
    return VehicleInfo.from_dict(data)


# ----------------------------------------------------------------------
# Приклад використання (можна закоментувати при імпорті в інший модуль)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Тестовий номер – замени на реальний для перевірки
    test_reg = "E366SJW"
    try:
        info = lookup_vehicle(test_reg)
        print(f"Vehicle info for {test_reg}:")
        print(info)
    except ChipexLookupError as e:
        print(f"Помилка: {e}")
