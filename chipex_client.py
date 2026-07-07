"""
Модуль відповідає за:
1. Запит до сайту chipex.co.uk за номером авто (reg)
2. Витягування вбудованого JSON (reg_json) з HTML-сторінки за допомогою bs4/lxml + regex
3. Повернення чистих даних у вигляді словника

Якщо в майбутньому знадобиться підтримати інше джерело даних (інший сайт,
інший формат відповіді) — досить додати новий клієнт в цей файл або поруч
і підключити його в app.py, не чіпаючи решту проєкту.
"""

import re
import json
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://chipex.co.uk/product/your-registration-touch-up-kit/"

# Виглядає так: reg_json: '{"reg":"E366SJW", ... }',
REG_JSON_PATTERN = re.compile(r"reg_json:\s*'({.*?})'", re.DOTALL)

HEADERS = {
    # Деякі сайти віддають інший (обрізаний) HTML ботам без User-Agent
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


class ChipexLookupError(Exception):
    """Піднімається, коли не вдалося отримати або розпарсити дані авто."""


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


def fetch_html(reg_number: str, timeout: int = 15) -> str:
    """Робить GET-запит до chipex.co.uk з номером авто і повертає HTML."""
    reg_number = reg_number.strip().upper()
    if not reg_number:
        raise ChipexLookupError("Номер автомобіля не може бути порожнім")

    params = {"reg": reg_number}
    try:
        response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ChipexLookupError(f"Не вдалося звернутися до chipex.co.uk: {exc}") from exc

    return response.text


def extract_reg_json(html: str) -> dict:
    """Знаходить reg_json у HTML і повертає розпарсений словник."""
    soup = BeautifulSoup(html, "lxml")

    # reg_json лежить всередині <script>, тому спочатку пробуємо знайти
    # відповідний regex-збіг у всьому тексті сторінки (найнадійніше),
    # а bs4 тримаємо про запас / для майбутнього розширення (наприклад,
    # якщо колись знадобиться витягувати ще щось із розмітки).
    match = REG_JSON_PATTERN.search(html)

    if not match:
        # fallback: шукаємо той самий патерн лише всередині <script>-тегів,
        # якщо raw-html з якоїсь причини не збігся напряму
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
        raise ChipexLookupError(f"Помилка розбору JSON з відповіді сайту: {exc}") from exc


def lookup_vehicle(reg_number: str) -> VehicleInfo:
    """Повний цикл: запит + парсинг + повернення VehicleInfo."""
    html = fetch_html(reg_number)
    data = extract_reg_json(html)
    return VehicleInfo.from_dict(data)
