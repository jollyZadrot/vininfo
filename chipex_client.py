"""
chipex_client.py

Клієнт для WordPress REST API сайту chipex.co.uk.
Endpoint: https://chipex.co.uk/wp-json/lookup/v2/reg/{REG}

Стратегія:
1. Спробувати REST API напряму (якщо доступний без авторизації)
2. Якщо не вийшло - fallback на HTML-парсинг
3. Детальні повідомлення про помилки для логування
"""

import re
import json
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup


# ----------------------------------------------------------------------
# Конфігурація
# ----------------------------------------------------------------------
BASE_URL = "https://chipex.co.uk"
WORDPRESS_API_URL = f"{BASE_URL}/wp-json/lookup/v2/reg/{{reg_number}}"
PRODUCT_URL = f"{BASE_URL}/product/your-registration-touch-up-kit/"

REG_JSON_PATTERN = re.compile(r"reg_json:\s*'({.*?})'", re.DOTALL)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://chipex.co.uk/",
    "Origin": "https://chipex.co.uk",
}


# ----------------------------------------------------------------------
# Винятки з детальною інформацією
# ----------------------------------------------------------------------
class ChipexLookupError(Exception):
    """Базовий виняток для помилок chipex.co.uk."""

    def __init__(self, message: str, status_code: int = None, details: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class ChipexAuthError(ChipexLookupError):
    """Помилка авторизації (401/403)."""
    pass


class ChipexNotFoundError(ChipexLookupError):
    """Номер не знайдено в базі (404)."""
    pass


class ChipexNetworkError(ChipexLookupError):
    """Мережева помилка (timeout, DNS, тощо)."""
    pass


# ----------------------------------------------------------------------
# Модель даних
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
        """Створює VehicleInfo з словника. Підтримує різні варіанти назв полів."""
        return cls(
            reg=str(data.get("reg", "")),
            manufacturer=str(data.get("manufacturer", data.get("make", ""))),
            model=str(data.get("model", "")),
            colour=str(data.get("colour", data.get("color", ""))),
            fuel=str(data.get("fuel", "")),
            year=str(data.get("year", "")),
            vin=str(data.get("vin", "")),
        )

    def to_dict(self) -> dict:
        return {
            "reg": self.reg,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "colour": self.colour,
            "fuel": self.fuel,
            "year": self.year,
            "vin": self.vin,
        }


# ----------------------------------------------------------------------
# Допоміжна функція для запитів
# ----------------------------------------------------------------------
def _make_request(
    url: str,
    headers: Dict[str, str] = None,
    timeout: int = 15,
) -> requests.Response:
    """Виконує HTTP-запит з детальною обробкою помилок."""
    request_headers = {**DEFAULT_HEADERS, **(headers or {})}

    try:
        response = requests.get(url, headers=request_headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ChipexNetworkError(
            f"Timeout after {timeout}s: {exc}",
            details={"url": url, "timeout": timeout},
        ) from exc
    except requests.ConnectionError as exc:
        raise ChipexNetworkError(
            f"Connection error: {exc}",
            details={"url": url},
        ) from exc
    except requests.RequestException as exc:
        raise ChipexNetworkError(
            f"Request failed: {exc}",
            details={"url": url, "exception_type": type(exc).__name__},
        ) from exc

    return response


def _handle_response(response: requests.Response, context: str = "") -> Dict[str, Any]:
    """
    Перевіряє HTTP-статус та повертає JSON або піднімає виняток.
    """
    status = response.status_code

    if status == 200:
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ChipexLookupError(
                f"Invalid JSON response from {context}",
                status_code=status,
                details={"body_snippet": response.text[:200]},
            ) from exc

    # Детальні повідомлення для різних статусів
    if status == 401:
        raise ChipexAuthError(
            f"Unauthorized (401) from {context}. "
            "Endpoint requires authentication or bot protection triggered.",
            status_code=status,
            details={
                "server": response.headers.get("Server"),
                "body_snippet": response.text[:200],
            },
        )
    elif status == 403:
        raise ChipexAuthError(
            f"Forbidden (403) from {context}. "
            "Access blocked by server (likely Cloudflare or similar).",
            status_code=status,
            details={
                "server": response.headers.get("Server"),
                "body_snippet": response.text[:200],
            },
        )
    elif status == 404:
        raise ChipexNotFoundError(
            f"Not Found (404) from {context}. "
            "Endpoint may not exist or resource is missing.",
            status_code=status,
            details={"url": response.url},
        )
    elif status == 429:
        raise ChipexLookupError(
            f"Rate limited (429) from {context}. "
            "Too many requests, slow down.",
            status_code=status,
            details={"retry_after": response.headers.get("Retry-After")},
        )
    elif 500 <= status < 600:
        raise ChipexLookupError(
            f"Server error ({status}) from {context}",
            status_code=status,
            details={"body_snippet": response.text[:200]},
        )
    else:
        raise ChipexLookupError(
            f"Unexpected status {status} from {context}",
            status_code=status,
            details={"body_snippet": response.text[:200]},
        )


# ----------------------------------------------------------------------
# Основні методи запиту
# ----------------------------------------------------------------------
def fetch_via_wordpress_api(reg_number: str, timeout: int = 15) -> VehicleInfo:
    """
    Отримує дані через WordPress REST API endpoint.
    Це публічний endpoint, який використовується JavaScript на сайті.
    """
    reg_number = reg_number.strip().upper()
    if not reg_number:
        raise ChipexLookupError("Registration number cannot be empty")

    url = WORDPRESS_API_URL.format(reg_number=reg_number)
    print(f"[API] GET {url}")

    response = _make_request(url, timeout=timeout)
    data = _handle_response(response, context="WordPress REST API")

    # Перевіряємо структуру відповіді
    # Очікувані формати:
    # 1. {"success": true, "data": {"reg": "...", "manufacturer": "...", ...}}
    # 2. {"reg": "...", "manufacturer": "...", ...} (прямі дані)
    if isinstance(data, dict):
        if "data" in data and "success" in data:
            if not data.get("success"):
                raise ChipexNotFoundError(
                    data.get("message", "API returned success=false"),
                    status_code=200,
                    details={"api_response": data},
                )
            vehicle_data = data["data"]
        else:
            vehicle_data = data
    else:
        raise ChipexLookupError(
            "Unexpected API response format: not a dictionary",
            status_code=200,
            details={"response_type": type(data).__name__},
        )

    if not isinstance(vehicle_data, dict) or not vehicle_data.get("reg"):
        raise ChipexNotFoundError(
            "API response doesn't contain vehicle data",
            status_code=200,
            details={"response": data},
        )

    return VehicleInfo.from_dict(vehicle_data)


def fetch_via_html_parsing(reg_number: str, timeout: int = 15) -> VehicleInfo:
    """
    Fallback: парсинг HTML-сторінки продукту.
    Використовується, якщо REST API недоступний.
    """
    reg_number = reg_number.strip().upper()
    if not reg_number:
        raise ChipexLookupError("Registration number cannot be empty")

    url = f"{PRODUCT_URL}?reg={reg_number}"
    print(f"[HTML] GET {url}")

    response = _make_request(url, timeout=timeout)

    if response.status_code != 200:
        _handle_response(response, context="HTML page")

    html = response.text

    # Шукаємо reg_json у всьому HTML
    match = REG_JSON_PATTERN.search(html)
    if not match:
        # Fallback: шукаємо в <script> тегах
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script"):
            script_text = script.string or ""
            match = REG_JSON_PATTERN.search(script_text)
            if match:
                break

    if not match:
        raise ChipexNotFoundError(
            f"reg_json not found in HTML for registration '{reg_number}'. "
            "The registration may not exist in chipex.co.uk database.",
            status_code=200,
            details={"html_length": len(html)},
        )

    try:
        raw_json = match.group(1)
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ChipexLookupError(
            f"Failed to parse reg_json from HTML: {exc}",
            status_code=200,
            details={"raw_json_snippet": match.group(1)[:200]},
        ) from exc

    return VehicleInfo.from_dict(data)


def lookup_vehicle(reg_number: str, use_api_first: bool = True) -> VehicleInfo:
    """
    Головна функція: спочатку пробує REST API, потім fallback на HTML.
    """
    reg_number = reg_number.strip().upper()
    if not reg_number:
        raise ChipexLookupError("Registration number cannot be empty")

    last_error: Optional[ChipexLookupError] = None

    # Визначаємо порядок спроб
    methods = (
        [fetch_via_wordpress_api, fetch_via_html_parsing]
        if use_api_first
        else [fetch_via_html_parsing, fetch_via_wordpress_api]
    )

    for method in methods:
        method_name = method.__name__
        try:
            print(f"[LOOKUP] Trying {method_name} for '{reg_number}'")
            result = method(reg_number)
            print(f"[LOOKUP] ✅ {method_name} succeeded")
            return result
        except ChipexAuthError as exc:
            print(f"[LOOKUP] ⚠️ {method_name} failed: {exc}")
            last_error = exc
            # Якщо це auth error, інший метод навряд чи допоможе,
            # але спробуємо HTML-парсинг як fallback
            continue
        except ChipexNotFoundError as exc:
            print(f"[LOOKUP] ⚠️ {method_name} failed: {exc}")
            last_error = exc
            # Якщо 404 в API, HTML може мати іншу логіку
            continue
        except ChipexLookupError as exc:
            print(f"[LOOKUP] ⚠️ {method_name} failed: {exc}")
            last_error = exc
            continue

    # Якщо всі методи не спрацювали
    if last_error:
        raise last_error

    raise ChipexLookupError(f"All lookup methods failed for '{reg_number}'")


# ----------------------------------------------------------------------
# Діагностичні функції
# ----------------------------------------------------------------------
def diagnose() -> Dict[str, Any]:
    """
    Запускає діагностику і повертає детальну інформацію.
    Корисно для дебагу на Render.
    """
    test_reg = "E366SJW"
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_registration": test_reg,
        "tests": {},
    }

    # Test 1: WordPress API
    try:
        result = fetch_via_wordpress_api(test_reg)
        results["tests"]["wordpress_api"] = {
            "status": "success",
            "data": result.to_dict(),
        }
    except ChipexLookupError as exc:
        results["tests"]["wordpress_api"] = {
            "status": "failed",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "status_code": exc.status_code,
            "details": exc.details,
        }

    # Test 2: HTML parsing
    try:
        result = fetch_via_html_parsing(test_reg)
        results["tests"]["html_parsing"] = {
            "status": "success",
            "data": result.to_dict(),
        }
    except ChipexLookupError as exc:
        results["tests"]["html_parsing"] = {
            "status": "failed",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "status_code": exc.status_code,
            "details": exc.details,
        }

    return results


# ----------------------------------------------------------------------
# CLI для тестування
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--diagnose":
        print(json.dumps(diagnose(), indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1:
        reg = sys.argv[1]
        try:
            info = lookup_vehicle(reg)
            print(json.dumps(info.to_dict(), indent=2, ensure_ascii=False))
        except ChipexLookupError as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            print(f"   Type: {type(e).__name__}", file=sys.stderr)
            if e.details:
                print(f"   Details: {json.dumps(e.details, indent=2, ensure_ascii=False)}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Usage:")
        print("  python chipex_client.py <REG>          - Lookup vehicle")
        print("  python chipex_client.py --diagnose     - Run diagnostics")
