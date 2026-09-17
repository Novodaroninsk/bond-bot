import os
import requests
from fredapi import Fred
from openai import OpenAI

# --- Ключи ---
FRED_KEY = os.getenv("FRED_KEY")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")

fred = Fred(api_key=FRED_KEY)

client_deepseek = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

# --- Доходности ---
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
lines.append("💱 Сила валют (спреды)")

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

# --- Экономический календарь (FMP) ---
calendar_text = ""
FMP_KEY = os.getenv("FMP_API_KEY")

if FMP_KEY:
    try:
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        url_fmp = f"https://financialmodelingprep.com/stable/economic-calendar?from={today}&to={tomorrow}&apikey={FMP_KEY}"
        r = requests.get(url_fmp, timeout=15)
        events = r.json()
        print("=== FMP RAW RESPONSE ===")
        print(events)

        # Проверяем, что ответ — список. Если нет — это ошибка API.
        if not isinstance(events, list):
            calendar_text = f"\n⚠️ FMP вернул ошибку: {events}"
            print(calendar_text)
        else:
            COUNTRIES = {"US", "EU", "GB", "JP", "AU"}
            cal_lines = ["", "📅 Экономический календарь (High Impact):"]
            count = 0

            for ev in events:
                if not isinstance(ev, dict):
                    continue
                if ev.get("country") not in COUNTRIES:
                    continue
                impact = str(ev.get("impact", "")).lower()
                if impact not in ("high", "3"):
                    continue
                date = ev.get("date", "?")
                country = ev.get("country", "?")
                event = ev.get("event", "?")
                estimate = ev.get("estimate", "-")
                previous = ev.get("previous", "-")
                cal_lines.append(f"• {date} | {country} | {event}")
                cal_lines.append(f"  прогноз: {estimate}, пред.: {previous}")
                count += 1
                if count >= 5:
                    break

            if count > 0:
                calendar_text = "\n".join(cal_lines)
            else:
                calendar_text = "\n📅 Нет важных событий по нашим валютам в ближайшие 24 часа."
            print(calendar_text)
    except Exception as e:
        calendar_text = f"\n⚠️ Ошибка календаря: {e}"
        print(calendar_text)
else:
    calendar_text = "\n📅 Календарь отключён (нет FMP_API_KEY)."
    print(calendar_text)

# --- Промпт для DeepSeek ---
prompt = f"""Ты — аналитик, работающий по стратегии свинг-трейдинга.
Стратегия: сравниваем доходности облигаций, чтобы понять, куда идут деньги.
Сильная валюта = растущая доходность. Слабая = падающая.

ДАННЫЕ ПО ДОХОДНОСТЯМ:
{data_text}

{calendar_text}

Ключи к интерпретации:
- Δ1д и Δ5д — свежая динамика.
- Δ1м и Δ3м — контекст тренда.
- Свежий тренд: Δ1д, Δ5д, Δ1м растут синхронно, Δ3м небольшой (<1.5).
- Зрелый тренд: Δ3м большой (>2.0), Δ1д тормозит — приоритет откату.
- Если ВСЕ доходности растут одновременно — это глобальный макрофактор.

ВАЖНО про спреды: спред показывает абсолютную разницу доходностей,
но НАПРАВЛЕНИЕ сделки определяется ДИНАМИКОЙ (Δ1д, Δ5д, Δ1м).
Если у валюты A динамика сильнее, чем у B — сделка в сторону A.

ПРАВИЛА ВХОДА:
- Не входить «по рынку». Вход ищется на откате к 20/50 MA,
  на выходе из консолидации (Bollinger Bands) или на 2-й день восстановления.
- Стоп ВСЕГДА 1.5–2×ATR.

ПРАВИЛА ПО КАЛЕНДАРЮ:
- Если в течение ближайших 24 часов есть событие High Impact по валюте из пары —
  предупреди об этом и НЕ рекомендуй вход до его выхода.

Проанализируй:
1. Сильные/слабые валюты с учётом всех таймфреймов?
2. Макро-контекст (все растут / переток между двумя)?
3. По каким парам чистый свежий тренд?
4. По каким парам зрелый тренд (ждём откат)?
5. Есть ли важные события в ближайшие 24 часа, влияющие на сетапы?
6. Финальные сетапы: направление, стоп 1.5–2×ATR, цель, обоснование.

Отвечай кратко, максимум 300 слов. Без противоречий в выводах."""

# --- Запрос к DeepSeek ---
try:
    ds_response = client_deepseek.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=700
    )
    ds_analysis = ds_response.choices[0].message.content
    print("=== DEEPSEEK OK ===")
    print(ds_analysis)
except Exception as e:
    ds_analysis = f"Ошибка DeepSeek: {e}"
    print("=== DEEPSEEK ERROR ===")
    print(repr(e))

# --- Формируем сообщение ---
full_message = data_text + calendar_text + "\n\n🧠 Анализ DeepSeek:\n" + ds_analysis

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
if len(full_message) > 4096:
    full_message = full_message[:4090] + "..."

response = requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": full_message
})
print("=== TELEGRAM RESPONSE ===")
print(response.text)
