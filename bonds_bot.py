import os
import requests
from fredapi import Fred
from openai import OpenAI

# Читаем все ключи из секретов GitHub
FRED_KEY = os.getenv("FRED_KEY")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")

fred = Fred(api_key=FRED_KEY)

# Клиент DeepSeek — полностью совместим с OpenAI SDK
client_deepseek = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

BONDS = {
    "DGS10": ("США 10Y", "USD"),
    "IRLTLT01DEM156N": ("Германия 10Y", "EUR"),
    "IRLTLT01GBM156N": ("Британия 10Y", "GBP"),
    "IRLTLT01JPM156N": ("Япония 10Y", "JPY"),
    "IRLTLT01AUM156N": ("Австралия 10Y", "AUD"),
}

def get_stats(ticker):
    try:
        s = fred.get_series(ticker).dropna()
        last = s.iloc[-1]
        prev1 = s.iloc[-2] if len(s) >= 2 else last
        prev5 = s.iloc[-6] if len(s) >= 6 else last
        return last, last - prev1, last - prev5
    except Exception as e:
        return None, None, None

lines = ["📊 *Доходности облигаций*"]
current = {}

for ticker, (name, code) in BONDS.items():
    last, d1, d5 = get_stats(ticker)
    if last is None:
        lines.append(f"{name}: ошибка")
        continue
    current[code] = last
    a1 = "🟢" if d1 > 0.01 else ("🔴" if d1 < -0.01 else "⚪️")
    a5 = "🟢" if d5 > 0.01 else ("🔴" if d5 < -0.01 else "⚪️")
    lines.append(f"{name}: {last:.2f}%  {a1}Δ1д {d1:+.2f}  {a5}Δ5д {d5:+.2f}")

lines.append("")
lines.append("💱 *Сила валют (спреды)*")

PAIRS = [
    ("USD", "JPY", "USD/JPY"),
    ("AUD", "JPY", "AUD/JPY"),
    ("GBP", "JPY", "GBP/JPY"),
    ("USD", "EUR", "EUR/USD (обр.)"),
]

for a, b, label in PAIRS:
    if a in current and b in current:
        spread = current[a] - current[b]
        lines.append(f"{label}: {spread:+.2f} п.п.")

data_text = "\n".join(lines)
print(data_text)

# --- Промпт для DeepSeek ---
prompt = f"""Ты — аналитик, работающий по стратегии свинг-трейдинга.
Стратегия: сравниваем доходности облигаций, чтобы понять, куда идут деньги.
Сильная валюта = растущая доходность. Слабая = падающая.
Работаем только в направлении потока капитала (Trend-Following и Momentum).
Ищем пары, где одна валюта сильно сильнее другой.

Вот текущие данные:
{data_text}

Проанализируй:
1. Какие валюты сейчас самые сильные и самые слабые?
2. Есть ли свежие, развивающиеся движения (Δ1д и Δ5д в одну сторону)?
3. По каким парам сейчас наиболее интересные сетапы?
4. Для каждой пары укажи: направление (лонг/шорт), примерный стоп по ATR, цель.

Отвечай кратко, по делу, максимум 200 слов."""

# --- Запрос к DeepSeek ---
try:
    ds_response = client_deepseek.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500
    )
    ds_analysis = ds_response.choices[0].message.content
except Exception as e:
    ds_analysis = f"Ошибка DeepSeek: {e}"

# --- Формируем итоговое сообщение ---
full_message = (
    data_text
    + "\n\n"
    + "🧠 *Анализ DeepSeek:*\n"
    + ds_analysis
)

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
if len(full_message) > 4096:
    full_message = full_message[:4090] + "..."

requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": full_message,
    "parse_mode": "Markdown"
})
