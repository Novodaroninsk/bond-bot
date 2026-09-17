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
        prev20 = s.iloc[-21] if len(s) >= 21 else last
        prev60 = s.iloc[-61] if len(s) >= 61 else last
        return last, last - prev1, last - prev5, last - prev20, last - prev60
    except Exception:
        return None, None, None, None, None

lines = ["📊 Доходности облигаций"]
current = {}

for ticker, (name, code) in BONDS.items():
    last, d1, d5, d20, d60 = get_stats(ticker)
    if last is None:
        lines.append(name + ": ошибка")
        continue
    current[code] = last
    a1 = "🟢" if d1 > 0.01 else ("🔴" if d1 < -0.01 else "⚪️")
    a5 = "🟢" if d5 > 0.01 else ("🔴" if d5 < -0.01 else "⚪️")
    a20 = "🟢" if d20 > 0.05 else ("🔴" if d20 < -0.05 else "⚪️")
    a60 = "🟢" if d60 > 0.10 else ("🔴" if d60 < -0.10 else "⚪️")
    lines.append(f"{name}: {last:.2f}%")
    lines.append(f"  1д {a1}{d1:+.2f}  5д {a5}{d5:+.2f}  1м {a20}{d20:+.2f}  3м {a60}{d60:+.2f}")

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

prompt = f"""Ты — аналитик, работающий по стратегии свинг-трейдинга.
Стратегия: сравниваем доходности облигаций, чтобы понять, куда идут деньги.
Сильная валюта = растущая доходность. Слабая = падающая.
Работаем только в направлении потока капитала (Trend-Following и Momentum).

Вот текущие данные:
{data_text}

Ключи к интерпретации:
- Δ1д и Δ5д — свежая динамика (какие деньги заходят прямо сейчас).
- Δ1м и Δ3м — контекст (зрелый тренд или только начинается).
- Если Δ1д, Δ5д, Δ1м в одну сторону — свежий тренд, самое сильное движение.
- Если Δ5д совпадает с Δ1м, а Δ1д расходится — идёт коррекция, не тренд.
- Если Δ3м против Δ5д — возможен разворот потока капитала, но требует подтверждения.

Проанализируй:
1. Какие валюты сейчас самые сильные и самые слабые (с учётом всех таймфреймов)?
2. По каким парам самый свежий развивающийся тренд (Δ1д, Δ5д, Δ1м в одну сторону)?
3. Где тренд зрелый (Δ3м большой, но Δ1д тормозит) — там приоритет откату, а не продолжению?
4. По каким парам интересные сетапы? Укажи: направление, стоп 1.5–2×ATR, цель.

Отвечай кратко, максимум 250 слов."""

# --- Запрос к DeepSeek ---
try:
    ds_response = client_deepseek.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500
    )
    ds_analysis = ds_response.choices[0].message.content
    print("=== DEEPSEEK OK ===")
    print(ds_analysis)
except Exception as e:
    ds_analysis = f"Ошибка DeepSeek: {e}"
    print("=== DEEPSEEK ERROR ===")
    print(e)

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

response = requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": full_message
})
print("=== TELEGRAM RESPONSE ===")
print(response.text)
