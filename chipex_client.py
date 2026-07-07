"""
chipex_client.py — ДІАГНОСТИЧНА ВЕРСІЯ
Тестує доступ до chipex.co.uk з сервера Render.
"""

import re
import json
import time
import os
import requests
from dataclasses import dataclass
from typing import Optional


BASE_URL = "https://chipex.co.uk"
PRODUCT_URL = f"{BASE_URL}/product/your-registration-touch-up-kit/"
API_URL_TEMPLATE = f"{BASE_URL}/wp-json/lookup/v2/reg/{{reg}}"
TEST_REG = "E366SJW"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://chipex.co.uk/",
}

REG_JSON_PATTERN = re.compile(r"reg_json:\s*'({.*?})'", re.DOTALL)


class ChipexLookupError(Exception):
    pass


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


def divider(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def safe_request(url: str, headers: dict = None, timeout: int = 15) -> Optional[requests.Response]:
    try:
        return requests.get(url, headers=headers or HEADERS, timeout=timeout, allow_redirects=True)
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return None


def test_1_basic_html():
    """Тест 1: Базовий запит HTML-сторінки продукту."""
    divider("ТЕСТ 1: Базовий запит HTML-сторінки")
    url = f"{PRODUCT_URL}?reg={TEST_REG}"
    print(f"  URL: {url}")
    response = safe_request(url)
    if not response:
        return None
    print(f"  ✅ Status: {response.status_code}")
    print(f"  📋 Server: {response.headers.get('Server', 'N/A')}")
    print(f"  📋 Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"  📄 HTML length: {len(response.text)} chars")
    if "reg_json" in response.text:
        print(f"  🎯 reg_json знайдено в HTML!")
        match = REG_JSON_PATTERN.search(response.text)
        if match:
            print(f"  📦 Data preview: {match.group(1)[:200]}...")
    else:
        print(f"  ⚠️  reg_json НЕ знайдено")
    if "cloudflare" in response.text.lower() or "cf-ray" in response.headers:
        print(f"  🛡️  CLOUDFLARE DETECTED!")
    if "access denied" in response.text.lower():
        print(f"  🚫 ACCESS DENIED в HTML!")
    return response


def test_2_rest_api():
    """Тест 2: WordPress REST API endpoint."""
    divider("ТЕСТ 2: WordPress REST API")
    url = API_URL_TEMPLATE.format(reg=TEST_REG)
    print(f"  URL: {url}")
    response = safe_request(url, headers={**HEADERS, "Accept": "application/json"})
    if not response:
        return None
    print(f"  ✅ Status: {response.status_code}")
    print(f"  📋 Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"  📄 Body (first 500 chars):")
    print(f"     {response.text[:500]}")
    try:
        data = response.json()
        print(f"  🎯 ВАЛІДНИЙ JSON! Ключі: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        if "success" in data:
            print(f"     success: {data['success']}")
        if "data" in data:
            print(f"     data preview: {str(data['data'])[:300]}")
    except json.JSONDecodeError:
        print(f"  ⚠️  Не JSON відповідь")


def test_3_root_domain():
    """Тест 3: Запит до кореневого домену."""
    divider("ТЕСТ 3: Перевірка доступу до chipex.co.uk (root)")
    print(f"  URL: {BASE_URL}")
    response = safe_request(BASE_URL)
    if not response:
        return None
    print(f"  ✅ Status: {response.status_code}")
    print(f"  📋 Server: {response.headers.get('Server', 'N/A')}")
    print(f"  📄 HTML length: {len(response.text)} chars")
    if "chipex" in response.text.lower() or "paint" in response.text.lower():
        print(f"  ✅ Головна сторінка завантажилась нормально")
    if "blocked" in response.text.lower() or "forbidden" in response.text.lower():
        print(f"  🚫 IP-блокування виявлено!")


def test_4_own_ip():
    """Тест 4: Визначення власної IP-адреси сервера."""
    divider("ТЕСТ 4: IP-адреса сервера Render")
    ip_services = [
        "https://api.ipify.org",
        "https://ifconfig.me",
    ]
    for service in ip_services:
        print(f"\n  🔸 {service}")
        try:
            response = requests.get(service, timeout=10)
            print(f"     Response: {response.text}")
            break
        except Exception as e:
            print(f"     Failed: {e}")


def run_all_tests():
    """Запускає всі діагностичні тести."""
    print("\n🚀 ДІАГНОСТИКА ДОСТУПУ ДО chipex.co.uk З RENDER")
    print(f"📍 Test reg: {TEST_REG}")
    print(f"🕐 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Render region: {os.environ.get('RENDER_REGION', 'unknown')}")

    test_1_basic_html()
    test_2_rest_api()
    test_3_root_domain()
    test_4_own_ip()

    divider("ПІДСУМОК")
    print("  Скопіюйте весь цей вивід і надішліть мені.")


# Робоча функція для сумісності з app.py
def lookup_vehicle(reg_number: str) -> VehicleInfo:
    """Стара функція — використовує HTML-парсинг."""
    reg_number = reg_number.strip().upper()
    response = safe_request(f"{PRODUCT_URL}?reg={reg_number}")
    if not response or response.status_code != 200:
        raise ChipexLookupError(
            f"Failed to fetch data. Status: {response.status_code if response else 'no response'}"
        )
    match = REG_JSON_PATTERN.search(response.text)
    if not match:
        raise ChipexLookupError("reg_json not found")
    data = json.loads(match.group(1))
    return VehicleInfo.from_dict(data)


if __name__ == "__main__":
    run_all_tests()
