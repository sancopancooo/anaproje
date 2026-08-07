# -*- coding: utf-8 -*-
"""
tmdb_platform_doldurucu_v3.py - AKILLI RATE LIMIT KORUMALI
--------------------------------------------------------------
Çalıştırma:
    python tmdb_platform_doldurucu_v3.py
    python tmdb_platform_doldurucu_v3.py --limit 50
--------------------------------------------------------------
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"

DB_PATH = "katalog.db"
TABLE_NAME = "filmler"
OUTPUT_JSON = "platform_guncellemeleri_tmdb.json"

REGION = "TR"
LANGUAGE = "tr-TR"

REQUEST_TIMEOUT = 20
SLEEP_BETWEEN = 0.3
SAVE_EVERY = 20

# 🔑 Rate limit koruması
CONSECUTIVE_EMPTY_LIMIT = 100   # 100 kez üst üste boş gelirse test yap
LONG_WAIT_ON_LIMIT = 15         # Rate limit tespitinde 15 sn bekle
MAX_RETRIES = 3

TEST_MOVIE_TMDB_ID = 13  # Forrest Gump

PLATFORM_SEPARATOR = ", "

ALLOWED_PLATFORMS = [
    "Netflix", "Amazon Prime Video", "Disney Plus", "TV+", "TOD TV",
    "MUBI", "HBO Max", "Crunchyroll", "BluTV", "Exxen", "Tabii",
    "GAIN", "Shahid VIP", "Sun Nxt", "KableOne", "Bloodstream",
    "Diğer Platform"
]

PLATFORM_ORDER = {name: i for i, name in enumerate(ALLOWED_PLATFORMS)}

PROVIDER_ALIASES = {
    "netflix": "Netflix",
    "netflix standard with ads": "Netflix",
    "netflix basic with ads": "Netflix",
    "netflix kids": "Netflix",

    "amazon prime video": "Amazon Prime Video",
    "amazon video": "Amazon Prime Video",
    "prime video": "Amazon Prime Video",
    "amazon prime video with ads": "Amazon Prime Video",

    "disney plus": "Disney Plus",
    "disney+": "Disney Plus",

    "tv+": "TV+",
    "tv +": "TV+",
    "apple tv plus": "TV+",
    "apple tv+": "TV+",
    "apple tv": "TV+",

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

    "gain": "GAIN",

    "shahid vip": "Shahid VIP",
    "shahid": "Shahid VIP",

    "sun nxt": "Sun Nxt",
    "sunnxt": "Sun Nxt",

    "kableone": "KableOne",
    "bloodstream": "Bloodstream"
}


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
            return []
    except Exception:
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
    tmdb_id_col = pick_existing_column(columns, ["tmdb_id"])
    title_col = pick_existing_column(columns, ["isim", "title", "ad", "name"])
    year_col = pick_existing_column(columns, [
        "vizyon_tarihi", "release_date", "yil", "year", "release_year", "tarih"
    ])
    platform_col = pick_existing_column(columns, ["platformlar", "streaming_platforms"])

    if not id_col:
        raise ValueError("ID kolonu bulunamadı.")
    if not title_col:
        raise ValueError("Başlık kolonu bulunamadı.")
    if not platform_col:
        raise ValueError("Platform kolonu bulunamadı.")

    return {
        "id_col": id_col,
        "tmdb_id_col": tmdb_id_col,
        "title_col": title_col,
        "year_col": year_col,
        "platform_col": platform_col
    }


def fetch_missing_records(schema):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    select_cols = [schema["id_col"], schema["title_col"]]
    if schema["tmdb_id_col"]:
        select_cols.append(schema["tmdb_id_col"])
    if schema["year_col"]:
        select_cols.append(schema["year_col"])

    query = f"""
        SELECT {", ".join(select_cols)}
        FROM {TABLE_NAME}
        WHERE {schema["platform_col"]} IS NULL
           OR TRIM(CAST({schema["platform_col"]} AS TEXT)) = ''
           OR LOWER(TRIM(CAST({schema["platform_col"]} AS TEXT))) IN ('null', 'none', '[]')
        ORDER BY {schema["id_col"]}
    """

    cursor.execute(query)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def normalize_provider_name(name):
    if not name:
        return None
    key = str(name).strip().lower()
    key = " ".join(key.split())
    return PROVIDER_ALIASES.get(key)


def safe_request(url, params, max_retries=MAX_RETRIES):
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", LONG_WAIT_ON_LIMIT))
                print(f"\n⚠️ RATE LIMIT! {retry_after} sn bekleniyor...")
                time.sleep(retry_after + 1)
                continue

            if r.status_code == 200:
                return r.json(), True

            if r.status_code in [500, 502, 503, 504]:
                print(f"\n⚠️ Server hatası {r.status_code}, {5*attempt} sn bekle...")
                time.sleep(5 * attempt)
                continue

            return None, False

        except requests.exceptions.Timeout:
            print(f"\n⚠️ Timeout, {3*attempt} sn bekle...")
            time.sleep(3 * attempt)
            continue
        except Exception as e:
            print(f"\n⚠️ Hata: {e}")
            time.sleep(2)
            continue

    return None, False


def check_api_alive():
    test_data, test_ok = safe_request(
        f"{BASE_URL}/movie/{TEST_MOVIE_TMDB_ID}/watch/providers",
        {"api_key": API_KEY}
    )
    if not test_ok or not test_data:
        return False

    test_tr = test_data.get("results", {}).get("TR")
    if not test_tr:
        return False

    if test_tr.get("flatrate"):
        return True

    return False


def tmdb_search_movie(title, year=""):
    if not title:
        return None

    params = {
        "api_key": API_KEY,
        "language": LANGUAGE,
        "query": title,
        "include_adult": "false"
    }
    if year and str(year).isdigit():
        params["year"] = year

    data, success = safe_request(f"{BASE_URL}/search/movie", params)
    if not success or not data:
        return None

    results = data.get("results", [])
    if not results:
        return None

    if year and str(year).isdigit():
        for item in results:
            rd = item.get("release_date") or ""
            if rd.startswith(str(year)):
                return item.get("id")

    return results[0].get("id")


def tmdb_get_watch_providers(tmdb_id):
    if not tmdb_id:
        return [], False

    data, success = safe_request(
        f"{BASE_URL}/movie/{tmdb_id}/watch/providers",
        {"api_key": API_KEY}
    )

    if not success or not data:
        return [], False

    tr_data = data.get("results", {}).get(REGION)

    if not tr_data:
        return [], True

    collected = []
    for key in ["flatrate", "free", "ads"]:
        for provider in tr_data.get(key, []) or []:
            name = provider.get("provider_name", "")
            canonical = normalize_provider_name(name)
            if canonical and canonical not in collected:
                collected.append(canonical)

    return collected, True


def finalize_platforms(platform_list):
    if not platform_list:
        return ["Diğer Platform"]

    unique = []
    seen = set()
    for p in platform_list:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    unique.sort(key=lambda x: PLATFORM_ORDER.get(x, 999))
    return unique


def run(limit=None):
    print("=" * 70)
    print("🎬 TMDB PLATFORM DOLDURUCU v3 (AKILLI RATE LIMIT)")
    print("=" * 70)

    if not os.path.exists(DB_PATH):
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        return

    print("🔍 API sağlık testi...")
    if check_api_alive():
        print("✅ API sağlam, başlıyoruz\n")
    else:
        print("⚠️ API test başarısız, yine de deniyoruz\n")

    schema = resolve_schema()

    print(f"ID kolonu       : {schema['id_col']}")
    print(f"TMDB ID kolonu  : {schema['tmdb_id_col']}")
    print(f"Başlık kolonu   : {schema['title_col']}")
    print(f"Tarih kolonu    : {schema['year_col']}")
    print(f"Platform kolonu : {schema['platform_col']}")
    print("-" * 70)

    missing_rows = fetch_missing_records(schema)
    existing_results = load_existing_results()

    existing_keys = set()
    for item in existing_results:
        key = make_key(item.get("id"))
        if key:
            existing_keys.add(key)

    pending_rows = [
        row for row in missing_rows
        if make_key(row.get(schema["id_col"])) not in existing_keys
    ]

    if limit:
        pending_rows = pending_rows[:int(limit)]

    print(f"DB boş platform kaydı  : {len(missing_rows)}")
    print(f"JSON'da işlenmiş       : {len(existing_keys)}")
    print(f"Bu tur işlenecek       : {len(pending_rows)}")
    print("=" * 70)

    if not pending_rows:
        print("✅ Yeni işlenecek kayıt yok.")
        return

    results = existing_results[:]
    start_time = time.time()

    stat_platform_found = 0
    stat_other_real = 0
    stat_failed = 0
    stat_from_search = 0

    consecutive_no_tr = 0

    for i, row in enumerate(pending_rows, start=1):
        film_id = row.get(schema["id_col"])
        title = row.get(schema["title_col"], "")
        raw_year = row.get(schema["year_col"], "") if schema["year_col"] else ""
        year = extract_year(raw_year)
        tmdb_id = row.get(schema["tmdb_id_col"]) if schema["tmdb_id_col"] else None

        print(f"[{i}/{len(pending_rows)}] 🎬 {title} ({year}) -> ", end="", flush=True)

        if not tmdb_id:
            tmdb_id = tmdb_search_movie(title, year)
            if tmdb_id:
                stat_from_search += 1

        platforms_raw = []
        api_success = False

        if tmdb_id:
            platforms_raw, api_success = tmdb_get_watch_providers(tmdb_id)

        platforms_final = finalize_platforms(platforms_raw)

        if not api_success and tmdb_id:
            stat_failed += 1
            consecutive_no_tr = 0
            print("❌ API HATASI (sonra tekrar denenecek)")
            time.sleep(SLEEP_BETWEEN)
            continue

        if platforms_final == ["Diğer Platform"]:
            stat_other_real += 1
            consecutive_no_tr += 1
        else:
            stat_platform_found += 1
            consecutive_no_tr = 0

        platform_text = PLATFORM_SEPARATOR.join(platforms_final)

        record = {
            "id": film_id,
            "tmdb_id": tmdb_id,
            "title": title,
            "vizyon_tarihi": raw_year,
            "year": year,
            "platformlar": platform_text,
            "platformlar_liste": platforms_final,
            "kaynak": "tmdb_watch_providers_v3"
        }

        results.append(record)
        existing_keys.add(make_key(film_id))

        print(platform_text)

        # 🔑 100 boş gelince akıllı test
        if consecutive_no_tr >= CONSECUTIVE_EMPTY_LIMIT:
            print(f"\n🤔 {consecutive_no_tr} kayıt üst üste boş, API test ediliyor...")
            save_results(results)

            if check_api_alive():
                print(f"✅ API sağlam, filmler gerçekten TR'de yok. Devam.\n")
                consecutive_no_tr = 0
            else:
                print(f"⚠️ RATE LIMIT tespit edildi, {LONG_WAIT_ON_LIMIT} sn bekle...")
                time.sleep(LONG_WAIT_ON_LIMIT)
                if check_api_alive():
                    print(f"✅ API tekrar sağlam, devam.\n")
                else:
                    print(f"⚠️ Hala sorun var, 30 sn daha bekle...")
                    time.sleep(30)
                consecutive_no_tr = 0

        if i % SAVE_EVERY == 0:
            save_results(results)
            print(f"💾 Ara kayıt: {i}/{len(pending_rows)}")

        time.sleep(SLEEP_BETWEEN)

    save_results(results)

    elapsed = round(time.time() - start_time, 1)
    print("=" * 70)
    print(f"✅ Tamamlandı ({elapsed} sn = {elapsed/60:.1f} dakika)")
    print(f"💾 Çıktı: {OUTPUT_JSON}")
    print("-" * 70)
    print("İSTATİSTİK")
    print(f"  Platform bulundu           : {stat_platform_found}")
    print(f"  TR'de yok (Diğer Platform) : {stat_other_real}")
    print(f"  Arama ile TMDB ID bulundu  : {stat_from_search}")
    print(f"  API hatası (tekrar denenecek): {stat_failed}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(limit=args.limit)