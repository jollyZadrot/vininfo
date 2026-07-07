"""
app.py

Flask веб-застосунок для пошуку інформації про авто за реєстраційним номером.
Використовує WordPress REST API сайту chipex.co.uk.

Запуск:
    python app.py

Або для production:
    gunicorn app:app --bind 0.0.0.0:$PORT
"""

import os
from typing import Optional, Dict, Any

from flask import Flask, render_template, request, jsonify

from chipex_client import (
    lookup_vehicle,
    ChipexLookupError,
    ChipexAuthError,
    ChipexNotFoundError,
    ChipexNetworkError,
    diagnose,
)

app = Flask(__name__)


# ----------------------------------------------------------------------
# Допоміжні функції для форматування помилок
# ----------------------------------------------------------------------
def format_error_for_user(error: ChipexLookupError) -> Dict[str, str]:
    """
    Перетворює технічну помилку у зрозуміле повідомлення для користувача.
    Повертає dict з title та message.
    """
    if isinstance(error, ChipexAuthError):
        return {
            "title": "Access Denied",
            "message": (
                "The chipex.co.uk server blocked our request. "
                "This is likely due to bot protection on the server side. "
                "Please try again later."
            ),
        }
    elif isinstance(error, ChipexNotFoundError):
        return {
            "title": "Not Found",
            "message": (
                f"The registration number was not found in the database. "
                "Please check the number and try again."
            ),
        }
    elif isinstance(error, ChipexNetworkError):
        return {
            "title": "Connection Problem",
            "message": (
                "Could not connect to chipex.co.uk. "
                "The server may be temporarily unavailable. "
                "Please try again in a few moments."
            ),
        }
    else:
        return {
            "title": "Lookup Error",
            "message": (
                "An unexpected error occurred while looking up the vehicle. "
                "Please try again or contact support if the problem persists."
            ),
        }


# ----------------------------------------------------------------------
# Маршрути
# ----------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    vehicle = None
    error_info = None
    reg_number = ""

    if request.method == "POST":
        reg_number = request.form.get("reg_number", "").strip()

        if not reg_number:
            error_info = {
                "title": "Invalid Input",
                "message": "Please enter a registration number.",
            }
        else:
            try:
                vehicle = lookup_vehicle(reg_number)
            except ChipexLookupError as exc:
                error_info = format_error_for_user(exc)
                # Додаємо технічні деталі в логи (не показуємо користувачу)
                app.logger.error(
                    f"Lookup failed for '{reg_number}': "
                    f"{type(exc).__name__}: {exc} | "
                    f"Status: {exc.status_code} | "
                    f"Details: {exc.details}"
                )

    return render_template(
        "index.html",
        vehicle=vehicle,
        error=error_info,
        reg_number=reg_number,
    )


@app.route("/api/lookup/<reg_number>")
def api_lookup(reg_number: str):
    """JSON API endpoint."""
    try:
        vehicle = lookup_vehicle(reg_number)
        return jsonify({
            "success": True,
            "data": vehicle.to_dict(),
        })
    except ChipexLookupError as exc:
        error_info = format_error_for_user(exc)
        return jsonify({
            "success": False,
            "error": error_info,
            "technical": {
                "type": type(exc).__name__,
                "status_code": exc.status_code,
                "message": str(exc),
            },
        }), exc.status_code or 500


@app.route("/diagnose")
def diagnose_endpoint():
    """
    Діагностичний endpoint для перевірки стану на Render.
    Відкрийте https://your-app.onrender.com/diagnose
    """
    return jsonify(diagnose())


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


# ----------------------------------------------------------------------
# Запуск
# ----------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
