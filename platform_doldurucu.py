# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import sqlite3
import argparse
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "katalog.db"
TABLE_NAME = "filmler"
OUTPUT_JSON = "platform_guncellemeleri.json"
PLATFORM_SEPARATOR = ", "
SAVE_EVERY = 10

ALLOWED_PLATFORMS = [
    "Netflix",
    "Amazon Prime Video",
    "Disney Plus",
    "TV+",
    "TOD TV",
    "MUBI",
    "HBO Max",
    "Crunchyroll",
    "BluTV",
    "Exxen",
    "Tabii",
    "GAIN",
    "Shahid VIP",
    "Sun Nxt",
    "KableOne",
    "Bloodstream",
    "Diğer Platform"
]

PLATFORM_ORDER = {name: i for i, name in enumerate(ALLOWED_PLATFORMS)}

PLATFORM_ALIASES = {
    "netflix": "Netflix",
    "amazon prime": "Amazon Prime Video",
    "amazon prime video": "Amazon Prime Video",
    "prime video": "Amazon Prime Video",
    "prime": "Amazon Prime Video",
    "disney+": "Disney Plus",
    "disney plus": "Disney Plus",
    "disneyplus": "Disney Plus",
    "tv+": "TV+",
    "tod": "TOD TV",
    "tod tv": "TOD TV",
    "mubi": "MUBI",
    "hbo max": "HBO Max",
    "max": "HBO Max",
    "crunchyroll": "Crunchyroll",
    "blutv": "BluTV",
    "blu tv": "BluTV",
    "exxen": "Exxen",
    "tabii": "Tabii",
    "tabi": "Tabii",
    "gain": "GAIN",
    "shahid vip": "Shahid VIP",
    "sun nxt": "Sun Nxt",
    "sunnxt": "Sun Nxt",
    "kableone": "KableOne",
    "bloodstream": "Bloodstream",
    "diğer platform": "Diğer Platform",
    "diger platform": "Diğer Platform",
    "other": "Diğer Platform",
    "others": "Diğer Platform"
}

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")

try:
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=API_KEY
    )
    AI_AVAILABLE = bool(API_KEY)
except ImportError:
    AI_AVAILABLE = False


def make_key(value):
    if value is None:
        return None
    return str(value).strip()


def load_existing_results():
    if not os.path.exists(OUTPUT_JSON):
        print(f"ℹ️ JSON dosyası henüz yok: {OUTPUT_JSON}")
        return []

    try:
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                print(f"ℹ️ Mevcut JSON yüklendi: {len(data)} kayıt")
                return data
            print("⚠️ JSON list formatında değil, boş kabul edildi.")
            return []
    except Exception as e:
        print(f"⚠️ JSON okunamadı: {e}")
        return []


def save_results(results):
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def pick_existing_column(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def extract_year(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return text


def resolve_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
    schema_rows = cursor.fetchall()
    conn.close()

    columns = [row[1] for row in schema_rows]

    id_col = pick_existing_column(columns, ["id", "film_id"])
    title_col = pick_existing_column(columns, ["title", "isim", "ad", "name"])
    year_col = pick_existing_column(columns, [
        "vizyon_tarihi",
        "release_year",
        "yil",
        "year",
        "release_date",
        "tarih"
    ])
    genre_col = pick_existing_column(columns, ["genres", "genre", "turler", "türler"])
    platform_col = pick_existing_column(columns, ["platformlar", "streaming_platforms"])

    if not id_col:
        raise ValueError("ID kolonu bulunamadı.")
    if not title_col:
        raise ValueError("Başlık kolonu bulunamadı.")
    if not platform_col:
        raise ValueError("Platform kolonu bulunamadı.")

    return {
        "id_col": id_col,
        "title_col": title_col,
        "year_col": year_col,
        "genre_col": genre_col,
        "platform_col": platform_col
    }


def fetch_missing_records(schema, limit=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    select_cols = [schema["id_col"], schema["title_col"]]
    if schema["year_col"]:
        select_cols.append(schema["year_col"])
    if schema["genre_col"]:
        select_cols.append(schema["genre_col"])

    query = f"""
        SELECT {", ".join(select_cols)}
        FROM {TABLE_NAME}
        WHERE {schema["platform_col"]} IS NULL
           OR TRIM(CAST({schema["platform_col"]} AS TEXT)) = ''
           OR LOWER(TRIM(CAST({schema["platform_col"]} AS TEXT))) IN ('null', 'none', '[]')
        ORDER BY {schema["id_col"]}
    """

    if limit:
        query += f" LIMIT {int(limit)}"

    cursor.execute(query)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def normalize_one_platform(name):
    if not name:
        return None
    key = str(name).strip().lower()
    key = " ".join(key.split())
    return PLATFORM_ALIASES.get(key)


def normalize_platforms(raw_platforms):
    if raw_platforms is None:
        items = []
    elif isinstance(raw_platforms, list):
        items = raw_platforms
    elif isinstance(raw_platforms, str):
        tmp = raw_platforms.replace(";", ",").replace("|", ",").replace("/", ",")
        items = [x.strip() for x in tmp.split(",")]
    else:
        items = []

    cleaned = []
    seen = set()

    for item in items:
        canonical = normalize_one_platform(item)
        if canonical and canonical != "Diğer Platform" and canonical not in seen:
            seen.add(canonical)
            cleaned.append(canonical)

    if not cleaned:
        return ["Diğer Platform"]

    cleaned.sort(key=lambda x: PLATFORM_ORDER.get(x, 999))
    return cleaned


def get_platforms_from_ai(title, year="", genres=""):
    if not AI_AVAILABLE:
        return ["Diğer Platform"]

    system_prompt = (
        "Sen film ve dizi yayın platformları için veri etiketleme yapan dikkatli bir uzmansın.\n"
        "Kurallar:\n"
        "1) Sadece şu platform adlarını kullan:\n"
        f"{ALLOWED_PLATFORMS[:-1]}\n"
        "2) Birden fazla platform varsa hepsini döndür.\n"
        "3) Emin değilsen boş liste döndür.\n"
        "4) Sadece JSON dön.\n"
        '5) Format: {"platformlar": ["Netflix", "Amazon Prime Video"]}'
    )

    user_prompt = f"Film adı: {title}\nYıl: {year}\nTürler: {genres}"

    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "mixtral-8x7b-32768"
    ]

    for model_name in models:
        try:
            res = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            data = json.loads(res.choices[0].message.content)
            raw = data.get("platformlar", [])
            return normalize_platforms(raw)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate_limit" in err:
                print(f"(⚠️ {model_name} limit) ", end="", flush=True)
                continue
            continue

    return ["Diğer Platform"]


def run(limit=None):
    print("=" * 70)
    print("🎬 PLATFORM JSON ÜRETİCİ")
    print("=" * 70)

    schema = resolve_schema()

    print(f"ID kolonu       : {schema['id_col']}")
    print(f"Başlık kolonu   : {schema['title_col']}")
    print(f"Tarih/Yıl kolonu: {schema['year_col']}")
    print(f"Platform kolonu : {schema['platform_col']}")
    print("-" * 70)

    missing_rows = fetch_missing_records(schema, limit=None)
    existing_results = load_existing_results()

    existing_keys = set()
    for item in existing_results:
        key = make_key(item.get("id"))
        if key:
            existing_keys.add(key)

    print(f"DB boş/null platform kaydı : {len(missing_rows)}")
    print(f"JSON içindeki kayıt sayısı : {len(existing_results)}")
    print(f"Eşleşen kayıt anahtarı     : {len(existing_keys)}")
    print("-" * 70)

    pending_rows = []
    for row in missing_rows:
        row_id = make_key(row.get(schema["id_col"]))
        if row_id not in existing_keys:
            pending_rows.append(row)

    if limit:
        pending_rows = pending_rows[:limit]

    print(f"Bu tur işlenecek kayıt     : {len(pending_rows)}")
    print("=" * 70)

    if not pending_rows:
        print("✅ Yeni işlenecek kayıt yok. Kaldığı yerden devam etmiş görünüyor.")
        return

    results = existing_results[:]

    for i, row in enumerate(pending_rows, start=1):
        film_id = row.get(schema["id_col"])
        title = row.get(schema["title_col"], "")
        raw_year = row.get(schema["year_col"], "") if schema["year_col"] else ""
        year = extract_year(raw_year)
        genres = row.get(schema["genre_col"], "") if schema["genre_col"] else ""

        if isinstance(genres, list):
            genres = ", ".join(map(str, genres))

        print(f"[{i}/{len(pending_rows)}] 🎬 {title} ({year}) -> ", end="", flush=True)

        platforms = get_platforms_from_ai(title, year, genres)
        platform_text = PLATFORM_SEPARATOR.join(platforms)

        record = {
            "id": film_id,
            "title": title,
            "vizyon_tarihi": raw_year,
            "year": year,
            "platformlar": platform_text,
            "platformlar_liste": platforms
        }

        results.append(record)
        existing_keys.add(make_key(film_id))

        print(platform_text)

        if i % SAVE_EVERY == 0:
            save_results(results)
            print(f"💾 Ara kayıt yapıldı -> {OUTPUT_JSON}")

        time.sleep(0.4)

    save_results(results)

    print("=" * 70)
    print(f"✅ Tamamlandı -> {OUTPUT_JSON}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="İşlenecek maksimum yeni kayıt sayısı")
    args = parser.parse_args()
    run(limit=args.limit)