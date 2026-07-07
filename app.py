"""
Flask веб-застосунок: поле вводу номера авто -> кнопка Search -> результат.

Запуск:
    pip install -r requirements.txt
    python app.py

Потім відкрити http://127.0.0.1:5000
"""

from flask import Flask, render_template, request

from chipex_client import lookup_vehicle, ChipexLookupError

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    vehicle = None
    error = None
    reg_number = ""

    if request.method == "POST":
        reg_number = request.form.get("reg_number", "").strip()
        try:
            vehicle = lookup_vehicle(reg_number)
        except ChipexLookupError as exc:
            error = str(exc)

    return render_template(
        "index.html",
        vehicle=vehicle,
        error=error,
        reg_number=reg_number,
    )


if __name__ == "__main__":
    app.run(debug=True)
