import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
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
    """Пытается получить данные. При ошибке — пробует альтернативный тикер (для США: GS10)."""
    fallbacks = {"DGS10": "GS10"}  # резервный тикер для US 10Y
    tickers_to_try = [ticker]
    if ticker in fallbacks:
        tickers_to_try.append(fallbacks[ticker])

    for t in tickers_to_try:
        try:
            s = fred.get_series(t).dropna()
            last = s.iloc[-1]
            prev1 = s.iloc[-2] if len(s) >= 2 else last
            prev5 = s.iloc[-6] if len(s) >= 6 else last
            prev20 = s.iloc[-21] if len(s) >= 21 else last
            prev60 = s.iloc[-61] if len(s) >= 61 else last
            return last, last - prev1, last - prev5, last - prev20, last - prev60
        except Exception:
            continue
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
    ("EUR", "JPY", "EUR/JPY"),
    ("USD", "EUR", "EUR/USD (обр.)"),
    ("USD", "GBP", "GBP/USD (обр.)"),
    ("USD", "AUD", "AUD/USD (обр.)"),
    ("EUR", "GBP", "EUR/GBP"),
    ("EUR", "AUD", "EUR/AUD"),
    ("GBP", "AUD", "GBP/AUD"),
]

for a, b, label in PAIRS:
    if a in current and b in current:
        spread = current[a] - current[b]
        lines.append(f"{label}: {spread:+.2f} п.п.")

data_text = "\n".join(lines)
print(data_text)

# --- Экономический календарь (ForexFactory XML) ---
calendar_text = ""
try:
    url_ff = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    r = requests.get(url_ff, timeout=15)
    print("=== FF STATUS ===")
    print(r.status_code)

    root = ET.fromstring(r.content)
    COUNTRIES = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD"}
    now = datetime.now()
    in_24h = now + timedelta(hours=24)

    cal_lines = ["", "📅 Экономический календарь (High Impact, 24ч):"]
    count = 0

    for event in root.findall("event"):
        country = event.findtext("country", "").strip().upper()
        impact = event.findtext("impact", "").strip().lower()
        if country not in COUNTRIES:
            continue
        if impact != "high":
            continue

        title = event.findtext("title", "?")
        date_str = event.findtext("date", "")
        time_str = event.findtext("time", "")
        forecast = event.findtext("forecast", "-") or "-"
        previous = event.findtext("previous", "-") or "-"

        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
        except Exception:
            dt = None

        if dt and now <= dt <= in_24h:
            cal_lines.append(f"• {dt.strftime('%d.%m %H:%M')} | {country} | {title}")
            cal_lines.append(f"  прогноз: {forecast}, пред.: {previous}")
            count += 1
            if count >= 8:
                break

    if count > 0:
        calendar_text = "\n".join(cal_lines)
    else:
        calendar_text = "\n📅 Нет High Impact событий по нашим валютам в ближайшие 24 часа."
    print(calendar_text)
except Exception as e:
    calendar_text = f"\n⚠️ Ошибка календаря: {e}"
    print(calendar_text)

# --- Правила стратегии (для промпта) ---
strategy_rules = """
СТРАТЕГИЯ: свинг-трейдинг, следуем за потоком капитала.

РИСК-МЕНЕДЖМЕНТ (не нарушать):
- Стоп ВСЕГДА 1.5–2×ATR.
- Цель: 0.7×дневной ATR или ближайший уровень.
- Стоп двигается только в сторону уменьшения риска.

ФУНДАМЕНТАЛЬНАЯ ЛОГИКА:
- Доходность растёт -> валюта усиливается.
- Доходность падает -> валюта слабеет.
- Направление сделки определяется ДИНАМИКОЙ (Δ1д, Δ5д, Δ1м), НЕ абсолютным спредом.
- Если у валюты A динамика сильнее, чем у B — сделка в сторону A. Даже если A «зрелый и перегретый» — это значит «ждать откат для входа в A», а НЕ «шортить A».
- Если ВСЕ доходности растут одновременно — это глобальный макрофактор, сигналы слабее.
- Carry-trade: при высоком аппетите к риску деньги идут из JPY в AUD/NZD/GBP.

ТРИ СИСТЕМЫ:
1. TREND-FOLLOWING: сильный тренд (импульсы 4+ дней), вход на 2-м дне восстановления после коррекции, к 20/50 MA. Стоп 1.5–2×ATR. Цель 0.7×дневной ATR.
2. MOMENTUM: сильное движение + консолидация 2-3 дня, вход на пробое Bollinger до нового максимума с зазором. Стоп 1–1.5×ATR. Цель — следующий экстремум.
3. COUNTER-TREND: три условия одновременно — новый экстремум, технический характер движения (3-4 дня), кульминационное ускорение. Вход после слабости (ложный пробой, откат от Bollinger). Стоп 1.5–2×ATR.

ПРАВИЛА ВХОДА:
- НЕ входить «по рынку».
- Вход на откате к 20/50 MA или на выходе из консолидации (Bollinger Bands).
- Если нет зазора до максимума — пропускать.
- Зрелый тренд (Δ3м > 2.0) — только на откате, не догонять.

ПРАВИЛА КАЛЕНДАРЯ:
- Наивысший приоритет: ставки ЦБ, пресс-конференции глав ЦБ.
- Высокий: Core CPI, Non-Farm Payrolls (NFP), Unemployment Rate.
- Средний: GDP, ISM PMI, Retail Sales.
- За 24 часа до High Impact по валюте — НЕ рекомендовать входы.
- После выхода события ждать закрытия часовой свечи.

ЧЕГО НЕ ДЕЛАТЬ:
- Не давать противоречивых сетапов.
- Не рекомендовать сделки без чёткого обоснования.
- Не предлагать вход против динамики (против потока капитала).
РАЗРЕШЁННЫЕ ПАРЫ:
- Можно анализировать любые комбинации из 5 валют (USD, EUR, GBP, JPY, AUD).
- НО: спреды рассчитаны только для пар из блока "Сила валют". Если предлагаешь пару вне списка — обоснуй её самостоятельно.
- Важно: у тебя НЕТ данных о цене, ATR и графиках. Ты работаешь ТОЛЬКО с доходностями. Если предлагаешь сделку, укажи, что точка входа и ATR должны быть рассчитаны трейдером на графике.
"""

# --- Промпт для DeepSeek ---
prompt = f"""Ты — аналитик, работающий по стратегии свинг-трейдинга.
Сильная валюта = растущая доходность. Слабая = падающая.
Работаем только в направлении потока капитала.

ДАННЫЕ ПО ДОХОДНОСТЯМ:
{data_text}

{calendar_text}

{strategy_rules}

Ключи к интерпретации:
- Δ1д и Δ5д — свежая динамика.
- Δ1м и Δ3м — контекст тренда.
- Свежий тренд: Δ1д, Δ5д, Δ1м растут синхронно, Δ3м небольшой (<1.5).
- Зрелый тренд: Δ3м большой (>2.0), Δ1д тормозит — приоритет откату.
ОСОБОЕ ПРАВИЛО ПРО JPY:
Если доходность JPY растёт быстрее остальных (Δ5д > +0.3, Δ1м > +1.0),
это означает СВОРАЧИВАНИЕ carry-trade. В такой ситуации JPY УСИЛИВАЕТСЯ,
а не является "валютой фондирования". НЕ называй JPY слабой и НЕ рекомендуй
лонги по парам XXX/JPY только потому, что у них положительный спред.

Проанализируй:
1. Сильные/слабые валюты с учётом всех таймфреймов?
2. Макро-контекст (все растут / переток между двумя)?
3. По каким парам чистый свежий тренд?
4. По каким парам зрелый тренд (ждём откат)?
5. Есть ли важные события в ближайшие 24 часа, влияющие на сетапы?
6. Финальные сетапы: направление, стоп 1.5–2×ATR, цель, обоснование.

Отвечай лаконично, максимум 250 слов. Без противоречий в выводах."""

# --- Запрос к DeepSeek ---
try:
    ds_response = client_deepseek.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1100
    )
    ds_analysis = ds_response.choices[0].message.content
    print("=== DEEPSEEK OK ===")
    print(ds_analysis)
except Exception as e:
    ds_analysis = f"Ошибка DeepSeek: {e}"
    print("=== DEEPSEEK ERROR ===")
    print(repr(e))

# --- Отправка в Telegram (2 сообщения) ---
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

# Сообщение 1: данные + календарь
msg1 = data_text + calendar_text
response1 = requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": msg1
})
print("=== TELEGRAM RESPONSE 1 (DATA) ===")
print(response1.text)

# Сообщение 2: анализ DeepSeek
msg2 = "🧠 Анализ DeepSeek:\n\n" + ds_analysis
if len(msg2) > 4096:
    msg2 = msg2[:4090] + "... (обрезано)"

response2 = requests.post(url, data={
    "chat_id": CHAT_ID,
    "text": msg2
})
print("=== TELEGRAM RESPONSE 2 (ANALYSIS) ===")
print(response2.text)

# --- Запись в Google Sheets через Apps Script ---
try:
    apps_script_url = os.getenv("APPS_SCRIPT_URL")

    if apps_script_url:
        payload = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "bonds": data_text,
            "calendar": calendar_text,
            "analysis": ds_analysis
        }
        resp = requests.post(apps_script_url, json=payload, timeout=15)
        print("=== SHEETS RESPONSE ===")
        print(resp.text)
    else:
        print("=== SHEETS SKIPPED (нет APPS_SCRIPT_URL) ===")
except Exception as e:
    print("=== SHEETS ERROR ===")
    print(repr(e))
