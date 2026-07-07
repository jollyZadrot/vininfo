"""
Flask веб-застосунок: поле вводу номера авто -> кнопка Search -> результат.

Логіка роботи:
1. Коли користувач вводить номер, додаток СПОЧАТКУ шукає його в локальному
   кеші (файл vehicle_cache.json).
2. Якщо номер знайдено в кеші -> миттєво повертаємо дані.
3. Якщо номер НЕ знайдено в кеші -> намагаємось зробити запит
   до chipex.co.uk. (УВАГА: на Render це може повернути 401 через
   захист сайту від ботів на IP дата-центрів).
4. Якщо парсинг успішний -> зберігаємо результат у кеш для майбутніх запитів.

Запуск:
    pip install -r requirements.txt
    python app.py

Потім відкрити http://127.0.0.1:5000
"""

import json
import os
from typing import Optional, Dict, Any

from flask import Flask, render_template, request, jsonify

from chipex_client import lookup_vehicle, ChipexLookupError

app = Flask(__name__)

# --- Налаштування кешу ---
CACHE_FILE = "vehicle_cache.json"


def load_cache() -> Dict[str, Any]:
    """
    Завантажує кеш з JSON-файлу.
    Повертає порожній словник, якщо файл не існує або пошкоджений.
    """
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_cache(cache: Dict[str, Any]) -> None:
    """Зберігає кеш у JSON-файл."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def get_vehicle_info(reg_number: str) -> Optional[Dict[str, Any]]:
    """
    Головна функція отримання інформації про авто.
    Спочатку перевіряє кеш, потім намагається парсити сайт.
    """
    reg_number = reg_number.strip().upper()
    if not reg_number:
        return None

    # 1. Перевіряємо кеш
    cache = load_cache()
    if reg_number in cache:
        print(f"[CACHE HIT] {reg_number}")
        return cache[reg_number]

    # 2. Якщо немає в кеші - намагаємось парсити
    print(f"[CACHE MISS] {reg_number}, спроба парсингу...")
    try:
        info = lookup_vehicle(reg_number)
        vehicle_data = {
            "reg": info.reg,
            "manufacturer": info.manufacturer,
            "model": info.model,
            "colour": info.colour,
            "fuel": info.fuel,
            "year": info.year,
            "vin": info.vin,
        }
        # Зберігаємо в кеш для наступних запитів
        cache[reg_number] = vehicle_data
        save_cache(cache)
        print(f"[CACHE SAVED] {reg_number}")
        return vehicle_data
    except ChipexLookupError as exc:
        print(f"[PARSE ERROR] {reg_number}: {exc}")
        return None


# --- Маршрути Flask ---

@app.route("/", methods=["GET", "POST"])
def index():
    """Головна сторінка з формою пошуку."""
    vehicle = None
    error = None
    reg_number = ""

    if request.method == "POST":
        reg_number = request.form.get("reg_number", "").strip()
        if not reg_number:
            error = "Будь ласка, введіть номер автомобіля."
        else:
            vehicle = get_vehicle_info(reg_number)
            if not vehicle:
                error = (
                    f"Не вдалося знайти інформацію для номера '{reg_number}'. "
                    "Можливо, цей номер не існує, або сервер заблокований. "
                    "Спробуйте інший номер або додайте його в кеш вручну."
                )

    return render_template(
        "index.html",
        vehicle=vehicle,
        error=error,
        reg_number=reg_number,
    )


# --- Тимчасові маршрути для діагностики (можна видалити після тестування) ---

@app.route("/debug")
def debug_chipex():
    """
    Діагностичний маршрут: перевіряє, що повертає chipex.co.uk
    безпосередньо з серверу Render.
    """
    import requests

    url = "https://chipex.co.uk/product/your-registration-touch-up-kit/"
    params = {"reg": "E366SJW"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        return jsonify({
            "status_code": response.status_code,
            "server_header": response.headers.get("Server", "N/A"),
            "content_type": response.headers.get("Content-Type", "N/A"),
            "html_snippet": response.text[:500],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/update_cache", methods=["POST"])
def update_cache():
    """
    Дозволяє додавати/оновлювати записи в кеші через POST-запит.
    Формат JSON: {"reg_number": "AB12CDE", "data": {...}}
    """
    payload = request.get_json(silent=True) or {}
    reg_number = payload.get("reg_number", "").strip().upper()
    data = payload.get("data")

    if not reg_number or not data:
        return jsonify({"error": "Потрібні reg_number та data"}), 400

    cache = load_cache()
    cache[reg_number] = data
    save_cache(cache)
    return jsonify({"ok": True, "reg_number": reg_number})


@app.route("/cache_status")
def cache_status():
    """Показує кількість записів у кеші (без самих даних)."""
    cache = load_cache()
    return jsonify({
        "total_entries": len(cache),
        "reg_numbers": list(cache.keys())
    })


if __name__ == "__main__":
    # Використовуємо змінну PORT для сумісності з Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
