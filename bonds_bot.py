import os
import requests
from fredapi import Fred

FRED_KEY = os.getenv("FRED_KEY")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

fred = Fred(api_key=FRED_KEY)

BONDS = {
    "США 10 лет": "DGS10",
    "Германия 10 лет": "IRLTLT01DEM156N",
    "Великобритания 10 лет": "IRLTLT01GBM156N",
    "Япония 10 лет": "IRLTLT01JPM156N",
    "Австралия 10 лет": "IRLTLT01AUM156N",
}

lines = ["📊 Доходности облигаций:"]
for name, ticker in BONDS.items():
    try:
        data = fred.get_series(ticker)
        last_value = data.dropna().iloc[-1]
        lines.append(f"{name}: {last_value:.2f}%")
    except Exception as e:
        lines.append(f"{name}: Ошибка: {e}")

text = "\n".join(lines)
print(text)

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
response = requests.post(url, data={"chat_id": CHAT_ID, "text": text})
print(response.text)
