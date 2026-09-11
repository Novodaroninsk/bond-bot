import os
import requests
from fredapi import Fred

FRED_KEY = os.getenv("FRED_KEY")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

fred = Fred(api_key=FRED_KEY)

# Тикер -> (название, короткий код валюты)
BONDS = {
    "DGS10": ("США 10Y", "USD"),
    "IRLTLT01DEM156N": ("Германия 10Y", "EUR"),
    "IRLTLT01GBM156N": ("Британия 10Y", "GBP"),
    "IRLTLT01JPM156N": ("Япония 10Y", "JPY"),
    "IRLTLT01AUM156N": ("Австралия 10Y", "AUD"),
}

def get_stats(ticker):
    """Возвращает (последнее, день назад, 5 дней назад)."""
    try:
        s = fred.get_series(ticker).dropna()
        last = s.iloc[-1]
        prev1 = s.iloc[-2] if len(s) >= 2 else last
        prev5 = s.iloc[-6] if len(s) >= 6 else last
        return last, last - prev1, last - prev5
    except Exception as e:
        return None, None, None

lines = ["📊 *Доходности облигаций*"]

# Собираем текущие значения для расчёта спредов
current = {}

for ticker, (name, code) in BONDS.items():
    last, d1, d5 = get_stats(ticker)
    if last is None:
        lines.append(f"{name}: ошибка")
        continue
    current[code] = last
    arrow1 = "🟢" if d1 > 0.01 else ("🔴" if d1 < -0.01 else "⚪️")
    arrow5 = "🟢" if d5 > 0.01 else ("🔴" if d5 < -0.01 else "⚪️")
    lines.append(f"{name}: {last:.2f}%  {arrow1}Δ1д {d1:+.2f}  {arrow5}Δ5д {d5:+.2f}")

# Сила валют относительно друг друга (спреды)
lines.append("")
lines.append("💱 *Сила валют (спреды)*")

PAIRS = [
    ("USD", "JPY", "USD/JPY"),
    ("AUD", "JPY", "AUD/JPY"),
    ("GBP", "JPY", "GBP/JPY"),
    ("USD", "EUR", "EUR/USD (обратный)"),
]

for a, b, label in PAIRS:
    if a in current and b in current:
        spread = current[a] - current[b]
        lines.append(f"{label}: {spread:+.2f} п.п.")

text = "\n".join(lines)
print(text)

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": text,
    "parse_mode": "Markdown"
})
